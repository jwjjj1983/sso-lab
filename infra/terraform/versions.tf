terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }

  # Created once by hand, see infra/README.md.
  backend "gcs" {
    bucket = "sso-lab-demo-tfstate"
    prefix = "terraform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
