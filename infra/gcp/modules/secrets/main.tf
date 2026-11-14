# Só o contêiner; a versão é adicionada via gcloud para não ir ao tfstate.
resource "google_secret_manager_secret" "this" {
  secret_id = var.secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "accessors" {
  for_each  = var.accessors
  secret_id = google_secret_manager_secret.this.id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}
