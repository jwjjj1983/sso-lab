data "google_project" "this" {}

locals {
  # One image, three services. Each service's URL is deterministic
  # (https://SERVICE-PROJECT_NUMBER.REGION.run.app), so every service can be told
  # every other service's URL up front.
  actors = ["idp", "app-a", "app-b"]
  urls = {
    for actor in local.actors :
    actor => "https://sso-lab-${actor}-${data.google_project.this.number}.${var.region}.run.app"
  }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# --- Container registry ------------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  repository_id = "sso-lab"
  location      = var.region
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Firestore: lab sessions and traces, deleted automatically by TTL ---------------------

resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

resource "google_firestore_field" "sessions_ttl" {
  database   = google_firestore_database.default.name
  collection = "labSessions"
  field      = "expires_at"
  ttl_config {}
}

resource "google_firestore_field" "events_ttl" {
  database   = google_firestore_database.default.name
  collection = "events" # collection group: labSessions/*/events
  field      = "expires_at"
  ttl_config {}
}

# --- Runtime identity ---------------------------------------------------------------------

resource "google_service_account" "runtime" {
  account_id   = "sso-lab-run"
  display_name = "SSO Lab Cloud Run runtime"
}

resource "google_project_iam_member" "runtime_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = google_service_account.runtime.member
}

# --- Cloud Run services -------------------------------------------------------------------

resource "google_cloud_run_v2_service" "actor" {
  for_each = toset(local.actors)

  name                = "sso-lab-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "3600s" # long-lived SSE trace streams
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.initial_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "SSO_LAB_ROLE"
        value = each.key
      }
      env {
        name  = "SSO_LAB_IDP_URL"
        value = local.urls["idp"]
      }
      env {
        name  = "SSO_LAB_APP_A_URL"
        value = local.urls["app-a"]
      }
      env {
        name  = "SSO_LAB_APP_B_URL"
        value = local.urls["app-b"]
      }
      env {
        name  = "SSO_LAB_STORE"
        value = "firestore"
      }
      env {
        name  = "SSO_LAB_GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "SSO_LAB_TRUST_PROXY"
        value = "true"
      }
    }
  }

  lifecycle {
    # CI deploys new images with `gcloud run deploy`; Terraform owns everything else.
    ignore_changes = [
      template[0].containers[0].image,
      template[0].revision,
      template[0].labels,
      client,
      client_version,
    ]
  }

  depends_on = [google_project_service.apis, google_project_iam_member.runtime_firestore]
}

# A public demo: anyone may call the services.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = google_cloud_run_v2_service.actor

  name     = each.value.name
  location = each.value.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
