resource "google_compute_instance" "this" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = [var.network_tag]

  # Troca de machine_type para e religa a VM.
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = var.image
      size  = var.disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = var.network
    access_config {
      nat_ip = var.address
    }
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  # startup-script em metadata: alteração aplica sem recriar a VM.
  metadata = {
    enable-oslogin = "TRUE"
    startup-script = templatefile("${path.module}/templates/startup.sh.tftpl", {
      repo_url      = var.repo_url
      secret_id     = var.secret_id
      domain        = var.domain
      acme_email    = var.acme_email
      registry_host = var.registry_host
      registry_url  = var.registry_url
    })
  }

  lifecycle {
    ignore_changes = [boot_disk[0].initialize_params[0].image]
  }
}

resource "google_compute_resource_policy" "snapshots" {
  count  = var.enable_snapshots ? 1 : 0
  name   = "${var.name}-snapshots"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "06:00"
      }
    }
    retention_policy {
      max_retention_days    = var.snapshot_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "snapshots" {
  count = var.enable_snapshots ? 1 : 0
  name  = google_compute_resource_policy.snapshots[0].name
  disk  = google_compute_instance.this.name
  zone  = var.zone
}
