output "url" {
  value = "https://${local.domain}"
}

output "ip" {
  value = module.network.address
}

output "secret_id" {
  value = module.secrets.secret_id
}

output "ssh" {
  value = "gcloud compute ssh ${module.compute.name} --zone ${var.zone} --project ${var.project_id} --tunnel-through-iap"
}

output "github_variables" {
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_ZONE         = var.zone
    GCP_VM_NAME      = module.compute.name
    GCP_REGISTRY     = module.registry.url
    GCP_WIF_PROVIDER = module.github_wif.provider_name
    GCP_DEPLOY_SA    = module.github_wif.service_account_email
    APP_URL          = "https://${local.domain}"
  }
}
