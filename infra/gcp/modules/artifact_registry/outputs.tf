output "host" {
  value = "${var.region}-docker.pkg.dev"
}

output "url" {
  value = "${var.region}-docker.pkg.dev/${data.google_client_config.this.project}/${google_artifact_registry_repository.this.repository_id}"
}
