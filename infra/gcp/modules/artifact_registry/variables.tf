variable "repository_id" {
  type = string
}

variable "region" {
  type = string
}

variable "keep_count" {
  type    = number
  default = 5
}

variable "readers" {
  type    = map(string)
  default = {}
}

variable "writers" {
  type    = map(string)
  default = {}
}
