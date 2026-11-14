terraform {
  required_version = ">= 1.5"

  # Bucket via -backend-config (ver README).
  backend "gcs" {
    prefix = "ai-doc-factory/prod"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # Cota faturada no próprio projeto, exigido por algumas APIs com credencial de usuário.
  user_project_override = true
  billing_project       = var.project_id
}
