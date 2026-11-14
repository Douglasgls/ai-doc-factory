resource "google_iam_workload_identity_pool" "this" {
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.this.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref in [${join(", ", [for r in var.allowed_refs : "'${r}'"])}]"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = var.service_account_id
  display_name = "Deploy via GitHub Actions"
}

resource "google_service_account_iam_member" "wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.this.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(var.project_roles)
  project  = google_service_account.deployer.project
  role     = each.value
  member   = google_service_account.deployer.member
}

# SSH com OS Login em VM que roda com outra SA.
resource "google_service_account_iam_member" "act_as" {
  for_each           = var.act_as
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
