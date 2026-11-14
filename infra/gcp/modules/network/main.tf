resource "google_compute_address" "this" {
  name   = "${var.name}-ip"
  region = var.region
}

resource "google_compute_firewall" "web" {
  name          = "${var.name}-web"
  network       = var.network
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.name]

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

resource "google_compute_firewall" "ssh" {
  name          = "${var.name}-ssh"
  network       = var.network
  source_ranges = var.ssh_source_ranges
  target_tags   = [var.name]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
