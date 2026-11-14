variable "secret_id" {
  type = string
}

# Chaves estáticas; valores podem ser desconhecidos no plan.
variable "accessors" {
  type    = map(string)
  default = {}
}
