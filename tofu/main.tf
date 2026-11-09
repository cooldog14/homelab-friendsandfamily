# The live VM 101 predates this code. It is imported, never applied: see the
# lifecycle block and tofu/README.md. Everything here documents the state the
# hypervisor actually runs, so a drift appears in `tofu plan`.
resource "proxmox_virtual_environment_hardware_mapping_pci" "igpu" {
  name = "igpu"
  map = [{
    node         = "malice"
    path         = "0000:00:02.0"
    id           = "8086:3e92"
    subsystem_id = "1043:8694"
    iommu_group  = 0
  }]
}

resource "proxmox_virtual_environment_vm" "chill_01" {
  name                = "chill-01"
  node_name           = "malice"
  vm_id               = 101
  on_boot             = true
  started             = true
  stop_on_destroy     = true
  scsi_hardware       = "virtio-scsi-single"
  boot_order          = ["scsi0"]
  reboot_after_update = false

  agent {
    enabled = true
    type    = "virtio"
  }

  cpu {
    cores = 4
    type  = "host"
  }

  memory {
    dedicated = 16384
  }

  operating_system {
    type = "l26"
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 80
    discard      = "on"
    iothread     = true
    ssd          = true
  }

  network_device {
    bridge      = "vmbr0"
    model       = "virtio"
    mac_address = "BC:24:11:F3:94:93"
  }

  initialization {
    datastore_id = "local-lvm"
    interface    = "ide2"
    dns {
      servers = ["1.1.1.1", "9.9.9.9"]
    }
    ip_config {
      ipv4 {
        address = "192.168.1.200/24"
        gateway = "192.168.1.1"
      }
    }
    user_account {
      username = "root"
      keys     = var.ssh_public_key == "" ? [] : [var.ssh_public_key]
    }
  }

  serial_device {
    device = "socket"
  }

  vga {
    type = "std"
  }

  smbios {
    uuid = "078b56db-f529-4c1b-9f6f-cb342f09f764"
  }

  hostpci {
    device  = "hostpci0"
    mapping = proxmox_virtual_environment_hardware_mapping_pci.igpu.name
  }

  virtiofs {
    mapping = "pve1-fast"
  }

  virtiofs {
    mapping = "pve1-vault"
  }

  virtiofs {
    mapping = "pve1-pool"
  }

  virtiofs {
    mapping = "pve1-backup"
  }

  lifecycle {
    # This VM is the only application host: destroying it is never a plan.
    prevent_destroy = true
    ignore_changes = [
      # hostpci.id cannot be managed by a scoped API token, and the provider
      # reindexes virtiofs from 0 while the live VM uses virtiofs1..4. The code
      # documents intent; no apply may rewrite these blocks on production.
      hostpci,
      virtiofs,
      # Provider-only behaviour flags, not VM configuration: the imported state
      # carries the provider defaults and there is no apply path to reconcile.
      reboot_after_update,
      stop_on_destroy,
      # The provider does not read smbios1/vga back on an imported VM, so these
      # stay documentation of what the hypervisor runs. The UUID above is the
      # VM identity and must never be rewritten by an apply.
      smbios,
      vga,
      # Cloud-init keys are host-local (never in git): the injected key is the
      # provisioning key, not managed state. ip_config stays tracked.
      initialization[0].user_account,
    ]
  }
}
