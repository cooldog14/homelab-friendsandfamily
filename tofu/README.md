# OpenTofu: Proxmox VM 101

Codifies the single application VM and its GPU passthrough mapping. The VM is
**imported and never applied**: it is the only application host, and the
provider cannot round-trip every field (see `lifecycle.ignore_changes` in
`main.tf`).

## Credentials

A dedicated Proxmox user and token, never the root password:

```sh
ssh <hypervisor> 'pveum user add tofu@pve --comment "OpenTofu homelab"'
ssh <hypervisor> 'pveum acl modify / --users tofu@pve --roles PVEAuditor'
ssh <hypervisor> 'pveum acl modify /vms/101 --users tofu@pve --roles PVEVMAdmin'
ssh <hypervisor> 'pveum acl modify /storage/local-lvm --users tofu@pve --roles Datastore.AllocateSpace'
ssh <hypervisor> 'pveum role add TofuMapping -privs "Mapping.Audit Mapping.Modify"'
ssh <hypervisor> 'pveum acl modify /mapping --users tofu@pve --roles TofuMapping'
ssh <hypervisor> 'pveum user token add tofu@pve homelab --privsep 0'
```

Store the values outside the repository, mode 0600:

```sh
# ~/.config/homelab/tofu.env
PROXMOX_VE_ENDPOINT=https://<hypervisor-fqdn>:8006/
PROXMOX_VE_API_TOKEN=tofu@pve!homelab=<secret>
PROXMOX_VE_INSECURE=true
```

`PROXMOX_VE_INSECURE=true` accepts the hypervisor's self-signed certificate:
the endpoint is reached over the private admin network, not the internet.

## Workflow

```sh
set -a; . ~/.config/homelab/tofu.env; set +a

tofu -chdir=tofu init
tofu -chdir=tofu fmt -check
tofu -chdir=tofu validate
tofu -chdir=tofu plan            # read-only, the normal command
```

`make tofu-check` runs the offline subset (fmt + init -backend=false + validate)
and is what CI runs; it needs no credentials.

## Import (one-off, already done)

```sh
tofu -chdir=tofu import proxmox_virtual_environment_vm.chill_01 <node>/101
```

## Plan-only policy

`tofu plan` must exit 0 (`-detailed-exitcode`). If it reports drift:

- Core fields (`cpu`, `memory`, `disk`, `network_device`,
  `initialization.ip_config`): fix the HCL to match reality, or fix reality on
  purpose.
- Fields the provider cannot read back on an imported VM (`smbios`, `vga`,
  cloud-init `user_account`, provider-only flags) are ignored by
  `lifecycle.ignore_changes` and stay documentation-only.

**Never run `tofu apply` against this VM.** `prevent_destroy` blocks the worst
case; it does not make an apply safe. The only scoped apply ever run is the PCI
mapping, which is a cluster object:

```sh
tofu -chdir=tofu apply -target=proxmox_virtual_environment_hardware_mapping_pci.igpu
```

The resource is spelled with the `proxmox_virtual_environment_` prefix on
purpose: `proxmox_hardware_mapping_pci` is the v1 name, and this repository is
pinned to provider `~> 0.121.0`. The deprecation warning is expected.

## State

`tofu.tfstate` stays local and untracked (`.gitignore`). The lock file
`.terraform.lock.hcl` **is** committed so CI and the workstation resolve the
same provider build.
