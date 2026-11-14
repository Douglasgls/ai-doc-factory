variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-medium"
}

variable "image" {
  type    = string
  default = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
}

variable "disk_size_gb" {
  type    = number
  default = 30
}

variable "network" {
  type = string
}

variable "network_tag" {
  type = string
}

variable "address" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "repo_url" {
  type = string
}

variable "secret_id" {
  type = string
}

variable "domain" {
  type = string
}

variable "acme_email" {
  type    = string
  default = ""
}

variable "registry_host" {
  type = string
}

variable "registry_url" {
  type = string
}

variable "enable_snapshots" {
  type    = bool
  default = true
}

variable "snapshot_retention_days" {
  type    = number
  default = 7
}
