# Virtual machine plan

OpenTofu describes VM 101 and its GPU mapping. The VM was imported. The
provider cannot read back every setting, so some fields are ignored in main.tf.
Use this configuration only to plan. Never run tofu apply.

## Credentials

A dedicated Proxmox user and token, never the root password:

```sh
ssh <hypervisor> 'pveum user add tofu@pve --comment "OpenTofu homelab"'
ssh <hypervisor> 'pveum acl modify / --users tofu@pve --roles PVEAuditor'
ssh <hypervisor> 'pveum user token add tofu@pve homelab --privsep 0'
```

Store the values outside the repository, mode 0600:

```sh
# ~/.config/homelab/tofu.env
PROXMOX_VE_ENDPOINT=https://<hypervisor-fqdn>:8006/
PROXMOX_VE_API_TOKEN=tofu@pve!homelab=<secret>
PROXMOX_VE_INSECURE=true
```

The insecure setting accepts the Proxmox self-signed certificate. Use it
only over the private admin network.

Give the user only PVEAuditor at the root, which includes Mapping.Audit.
Do not grant VM management or mapping changes. Use existing admin access for
intentional changes. The [November 26 review](../docs/history/2026-11-26-observability-and-mounts.md#maintenance-2026-11-26-continuation-gate-review)
records the read-only grants and a no-change plan. Check privileges directly;
never test them by attempting a destructive action.

## Workflow

```sh
set -a; . ~/.config/homelab/tofu.env; set +a

tofu -chdir=tofu init
tofu -chdir=tofu fmt -check
tofu -chdir=tofu validate
tofu -chdir=tofu plan -detailed-exitcode
```

make tofu-check runs the offline checks in CI and needs no credentials.

## Import (one-off, already done)

```sh
tofu -chdir=tofu import proxmox_virtual_environment_vm.chill_01 <node>/101
```

## Plan-only policy

With the detailed exit code, 0 means no changes, 2 means changes, and 1
means an error. If core VM settings differ, decide which values are right
and correct Git or the VM on purpose. Leave fields the provider cannot read
on the ignore list.

The token must stay read-only. A destroy guard or the earlier GPU mapping
setup does not authorize an apply.

The provider is pinned to the 0.121 series. Keep the old PCI mapping resource
name until a provider upgrade. Its deprecation warning is expected.

## State

Keep the state file local and untracked. Commit the lock file so CI and the
workstation use the same provider version.
