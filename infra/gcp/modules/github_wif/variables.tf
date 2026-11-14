variable "pool_id" {
  type    = string
  default = "github"
}

# owner/repo
variable "github_repository" {
  type = string
}

variable "allowed_refs" {
  type    = list(string)
  default = ["refs/heads/master"]
}

variable "service_account_id" {
  type    = string
  default = "github-deployer"
}

variable "project_roles" {
  type = list(string)
  default = [
    "roles/compute.viewer",
    "roles/compute.osAdminLogin",
    "roles/iap.tunnelResourceAccessor",
  ]
}

# SAs (id completo) que o deployer pode usar.
variable "act_as" {
  type    = map(string)
  default = {}
}
