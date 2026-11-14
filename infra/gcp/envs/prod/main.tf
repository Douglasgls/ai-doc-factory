locals {
  apis = [
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "iap.googleapis.com",
    "oslogin.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
  domain = var.domain != "" ? var.domain : "${replace(module.network.address, ".", "-")}.sslip.io"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "vm" {
  account_id   = "${var.name}-vm"
  display_name = "VM ${var.name}"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "vm" {
  for_each = toset(["roles/logging.logWriter", "roles/monitoring.metricWriter"])
  project  = var.project_id
  role     = each.value
  member   = google_service_account.vm.member
}

module "network" {
  source            = "../../modules/network"
  name              = var.name
  region            = var.region
  ssh_source_ranges = var.ssh_source_ranges
  depends_on        = [google_project_service.apis]
}

module "secrets" {
  source     = "../../modules/secrets"
  secret_id  = "${var.name}-env"
  accessors  = { vm = google_service_account.vm.member }
  depends_on = [google_project_service.apis]
}

module "github_wif" {
  source            = "../../modules/github_wif"
  github_repository = var.github_repository
  allowed_refs      = ["refs/heads/${var.deploy_branch}"]
  act_as            = { vm = google_service_account.vm.name }
  depends_on        = [google_project_service.apis]
}

module "registry" {
  source        = "../../modules/artifact_registry"
  repository_id = var.name
  region        = var.region
  readers       = { vm = google_service_account.vm.member }
  writers       = { deployer = module.github_wif.member }
  depends_on    = [google_project_service.apis]
}

module "compute" {
  source                = "../../modules/compute"
  name                  = var.name
  region                = var.region
  zone                  = var.zone
  machine_type          = var.machine_type
  disk_size_gb          = var.disk_size_gb
  network               = module.network.network
  network_tag           = module.network.tag
  address               = module.network.address
  service_account_email = google_service_account.vm.email
  repo_url              = var.repo_url
  secret_id             = module.secrets.secret_id
  domain                = local.domain
  acme_email            = var.acme_email
  registry_host         = module.registry.host
  registry_url          = module.registry.url
  enable_snapshots      = var.enable_snapshots
  depends_on            = [module.secrets, module.registry, google_project_iam_member.vm]
}
