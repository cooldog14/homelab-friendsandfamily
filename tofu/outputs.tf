output "vm_id" {
  value = proxmox_virtual_environment_vm.chill_01.vm_id
}

output "igpu_mapping" {
  value = proxmox_virtual_environment_hardware_mapping_pci.igpu.name
}
