output "address" {
  value = google_compute_address.this.address
}

output "network" {
  value = var.network
}

output "tag" {
  value = var.name
}
