variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "network" {
  type    = string
  default = "default"
}

# Padrão: só IAP.
variable "ssh_source_ranges" {
  type    = list(string)
  default = ["35.235.240.0/20"]
}
