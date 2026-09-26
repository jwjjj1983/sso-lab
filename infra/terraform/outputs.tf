output "urls" {
  description = "Public URL of each actor. The playground is app-a."
  value       = local.urls
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

# The three values below go into GitHub repo variables (see infra/README.md).
output "github_vars" {
  value = {
    GCP_PROJECT_ID = var.project_id
    GCP_REGION     = var.region
    WIF_PROVIDER   = google_iam_workload_identity_pool_provider.github.name
    DEPLOYER_SA    = google_service_account.deployer.email
  }
}
