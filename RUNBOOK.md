# Runbook

Use a quiet window. Break one thing at a time and never test by deleting data.
Follow the [safety and access rules](AGENTS.md).

## Commands

Run these from the repository root. Use Python 3.12 to set up Ansible on a
new workstation:

```sh
make ansible-bootstrap
```

- make host sets up the application VM.
- make vps sets up the public server.
- make hypervisor sets up monitoring and backup timers on the Proxmox host.
- make check validates stack files, routes, scripts, and alert rules. It needs Docker.
- make deploy runs the checks, then deploys all stacks from the current commit.
  It refuses local changes under stacks, reapplies container isolation, and
  records the deployed commit.
- make edge-reload restarts private Caddy.
- make ansible-check checks playbook syntax.
- make tofu-check validates the VM plan offline. make tofu-plan compares it
  with Proxmox without applying changes.
- make restore-test restores a sample on chill-01. It is not independent recovery.

## Recovery expectations

Recovery after losing a host, VM, or disk is manual. The time to rebuild the
whole lab has not been measured. Check the last successful snapshot before
estimating how much data could be lost.

Nightly app backups cover /opt, /mnt/fast/dumps, /mnt/data, /etc, and /root/.ssh.
They exclude downloads, movies, TV, and raw music staging. Each app backup
repository keeps three snapshots. Hypervisor retention is 7 daily, 4 weekly,
and 6 monthly.

Run the independent proof on a machine other than chill-01. Install Bash,
restic, Python 3, sqlite3, tar, and od first.

```sh
host/recovery-proof.sh APP_ENV MALICE_ENV
```

Pass the paths to two trusted shell files from the escrow records. Keep the
records in a password manager and sealed offline copies. The files must be
owned by the user running the script, have mode 0600, and live outside this
checkout. Each sets RESTIC_REPOSITORY, RESTIC_PASSWORD, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION.

The script restores and checks selected app dumps and server configuration in a
private temporary directory, then removes that directory. Record snapshot IDs
and results, not contents or credentials. Do not substitute make restore-test:
it needs chill-01 and restores protected configuration to a fixed path.

Test the same snapshots in disposable apps. Use the pinned Immich and
Paperless PostgreSQL images with no published ports or production networks.
Import the dumps with psql using the flags below. Verify schema and row counts
without publishing records. Open copies of all three Bolt databases in
disposable Filebrowser instances. Record these results separately.

```sh
psql -X -v ON_ERROR_STOP=1
```

For a rebuild, review the hypervisor configuration first. Rebuild VM 101 and
its mounts from Git. Restore databases and app state, start the stacks, restore
public and private access, and check alerts. Never overwrite a running Proxmox
cluster database with a restored copy.

## Deployment regression

Revert only the affected configuration on the integrated branch. Commit the
revert and run the matching command. Never deploy from another checkout to
get around unfinished or uncommitted owner changes.

Restore app data only if a confirmed migration changed it. Record which
commits and services were involved and whether any app data was restored.

## Mount narrowing rollout

Before deploying, integrate the owner's stack changes, resolve private probe
mismatches, pass make check, and set dashboard keys privately. Compare the
candidate with the deployed config. Confirm it includes just one mount batch
and verify the live paths. Stop if the current setup differs unexpectedly.
Never move media on disk.

Start with Jellyfin and Bazarr (commit 46b5858). The
[November 26 record](docs/history/2026-11-26-observability-and-mounts.md#maintenance-2026-11-26-review-fixes)
lists the commits that hold back the other batches. Reverse a hold only after
the previous batch and the next batch's checks pass.

1. Jellyfin and Bazarr. Check that every Jellyfin library path is under
   /data/media/music, /pool/movies, or /pool/tv. Check that Bazarr paths and
   mappings fit its pool mounts. Test playback and subtitles.
2. qBittorrent and Arr. Check downloads use /data/downloads or /pool/downloads.
   Check movie paths under /pool/movies and series paths under /pool/tv.
   Check for incompatible remote mappings and test a disposable import.
3. slskd. Check that the share is read-only and the inbox is writable. Test a
   download and tagging with disposable input.
4. Music Manager and wrtag. Wait for the owner's base commit and the
   coordinated change. Before creating directories, check that the takeover
   media source exists and matches /mnt/data/media by device and inode. Test
   rename and rollback with disposable input.
5. Filebrowser. Check the allowed bind sources and their existing ownership.
   Test file access, password and passkey login, and moves with disposable
   files. Keep forwarded-header trust off while peers can reach Filebrowser
   without Caddy.

Run make deploy for each batch, inspect the changed services, and verify the
workflow before moving on. On failure, reverse only that batch and redeploy.
Do not restore a database to roll back a mount change.

## Malice boot and disk maintenance

Require independent recovery proof, a verified 4 GiB setup for VM 100,
tested console access, and someone on site. Do not change fstab, the kernel
pin, or the drives if any of those are missing.

Check Secure Boot and match BootCurrent to the EFI partition by its
partition GUID. Confirm the filesystem UUID below, that the pin
selects 7.0.14-26-pve, and that 7.0.14-29-pve is installed. Stop if anything
differs. Only then add this entry to fstab and mount without formatting:

```text
UUID=14B4-0FF6 /boot/efi vfat umask=0077 0 2
```

Run proxmox-boot-tool kernel unpin and confirm that GRUB defaults to
7.0.14-29-pve before rebooting. Keep the signed shim, GRUB, and 7.0.14-26-pve as
fallback. Do not run grub-install or initialize systemd-boot. If the new
kernel fails, select the fallback at the console and restore the pin. Verify
the kernel, guest autostart, virtiofs mounts, GPU passthrough, and apps before
touching disks.

Check that the retired disk's serial is ata-ST2000DX002-2DV164_Z4Z9F91S
and that it has no mounts, storage or guest references, or open files. Stop
the guests gracefully and power off. Remove only that disk, label it, and
keep it unwiped. Leave both backup disks in place. After boot, check their
mounts, guest autostart, backups, apps, and alerts.

## Public service down

Check the homelab-public-check logs and compare the Caddy site files in
vps/sites with the live VPS configuration. When several sites fail together,
check the /mnt/data mount and both WireGuard handshakes. Use docker ps --all
to see whether containers stopped. Do not restart stacks one by one.

If only one app is down, inspect its logs before restarting the service.
Record when the issue was detected and when service returned.

## Private edge

Validate the change to stacks/edge/Caddyfile and deploy it. make deploy
restarts Caddy if the file changed. If an explicit restart is needed, use
make edge-reload. Compose up alone does not reread the file when the service
definition is unchanged. Use exact host matchers, not a map. Test the route
and check that unlisted names return 404.

## VPS Caddy

Change the site file in Git and run make vps. Validation must pass before
Caddy reloads. See the [VPS guide](vps/README.md).

## WireGuard

Keep a tested fallback before interrupting a tunnel. Check both ends with wg show.
The backend link uses chill0 on the VPS and wg0 on chill-01. Restart only
the affected wg-quick unit.

If handshakes stay stale, check whether chill-01 can reach 194.58.47.21
directly. A broken gateway route or stale router address entry can break
the tunnel without a WireGuard error. Never edit /etc/wireguard.

## Stale backup or failed alerts

Check the backup unit's journal and the last successful snapshot. Fix the
cause and run the backup. Never advance the success marker by hand.
The watchdog alerts after 48 hours. Do not bypass the snapshot path guard.

Check each step between Prometheus and Gotify, including Alertmanager and the
bridge. Check the direct systemd notification path too. After a host deploy or
reboot, check backup and check timers. Run homelab-pipeline-check and
homelab-alert-check. A working public site does not prove that alerts work.

## Notification drills

Get approval and confirm you can read the receipts first. Set up a temporary
systemd oneshot that runs /bin/false, with OnFailure=notify@%n.service. Add a
companion timer set beyond the drill and an entry in the job collector.
Wait for HomelabJobFailed and check for a separate receipt from the direct
path and the bridge. Remove only the drill wiring, clear the failed state,
restore the collector, and confirm the alert clears. Do not stop a real app
or exporter.

Separately, confirm the independent Healthchecks recipient, 5-minute period,
and 15-minute grace with authorized access. Check for a failure receipt, a
recovery receipt, and the next scheduled Worker success. Use a separate
equivalent check if the cron would hide the failure. Do not disable the
production check. A successful HTTP response is not a receipt.

## History

Record incidents, maintenance, and drill results in the
[operations history](docs/history/README.md). Use the date of the event.
Keep old commands and checkboxes there, not in the [open work list](TODO.md).
