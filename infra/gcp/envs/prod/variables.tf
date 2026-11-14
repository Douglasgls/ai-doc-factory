variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "name" {
  type = string
}

variable "machine_type" {
  type = string
}

variable "disk_size_gb" {
  type = number
}

variable "repo_url" {
  type = string
}

# owner/repo
variable "github_repository" {
  type = string
}

variable "deploy_branch" {
  type = string
}

# Vazio: <ip>.sslip.io.
variable "domain" {
  type = string
}

variable "acme_email" {
  type = string
}

variable "ssh_source_ranges" {
  type = list(string)
}

variable "enable_snapshots" {
  type = bool
}
