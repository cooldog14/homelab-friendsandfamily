variable "ssh_public_key" {
  type        = string
  description = "Public key to inject via cloud-init at create time. Empty by default so validate/plan work without host-local files."
  default     = ""
}
