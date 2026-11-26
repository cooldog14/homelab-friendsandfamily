# Runbook

Break one thing at a time, use a quiet window, and never test by deleting data.
Follow the safety and access rules in [AGENTS.md](AGENTS.md).

## Recovery expectations

Best effort, not HA. Recovery after host, VM or disk loss is manual; full-platform
RTO is unmeasured. Nightly backups cover `/opt`, `/mnt/fast/dumps`, `/mnt/data`,
`/etc` and `/root/.ssh`, excluding downloads, movies, TV and raw music staging.
RPO depends on the latest successful snapshot, not merely the timer schedule.
Use `host/recovery-proof.sh APP_ENV MALICE_ENV` on a machine other than chill-01.
The two trusted shell escrow records must be owned by the invoking user, mode
0600, outside this checkout; create password-manager records and sealed offline
copies. Each must explicitly set `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_DEFAULT_REGION`.
Install Bash, restic, Python 3, sqlite3, tar and od first. The helper restores only
selected application dumps, VPS configs and hypervisor configs into a private
temporary directory, verifies bytes and named artifacts, then removes its own
directory. Record snapshot IDs and pass/fail, never credentials or contents.
Do not use `make restore-test` for independent recovery: it requires chill-01
and restores protected tunnel material into a fixed directory.

Structural integrity is not application recovery. Separately restore the same
snapshot's SQL/Bolt artifacts to a private disposable workspace. Use the current
Compose-pinned Immich/Paperless PostgreSQL images, no published ports or
production networks, and `psql -X -v ON_ERROR_STOP=1` for isolated imports.
Verify schema/data counts without publishing records. Run disposable Filebrowser
instances against copies of all three Bolt artifacts. Record those results
separately; platform RTO remains unmeasured.

Restore order: review hypervisor configuration → rebuild VM 101 and storage
mounts from git → application databases/state → Compose → private/public edge
→ alerts. Never overwrite a running PVE cluster database with a restored copy.
Guest retention is three snapshots per repository; hypervisor retention is
7 daily / 4 weekly / 6 monthly.

## Deployment regression

Revert only the affected source/config on the integrated branch, commit, then
run the affected target (`make deploy`, `make host`, `make vps` or
`make hypervisor`). `make deploy` reconciles all stacks from committed `HEAD`;
never use another checkout to bypass dirty or unresolved owner changes.
Restore application state only after a confirmed data-changing migration.
Record bad/good commits, affected services, and any state restoration.

## Mount narrowing rollout

Deploy only after owner stack changes are integrated, the private-probe
contract and `make check` pass, and the dashboard keys are privately
provisioned. Before each batch, compare the candidate with the effective
deployed config, confirm no other pending mount batch is included, and verify
live mount paths. Stop on unexpected drift. Never move media on disk.

Each activation commit changes only one mount batch. The Jellyfin/Bazarr
change (`46b5858`) is first. The
[review follow-up](docs/history/2026-09-11-operations.md#maintenance-2026-11-26-review-fixes)
lists the later holds. Reverse only the hold whose prerequisites have passed.
Deploy with `make deploy`, inspect the changed services, and verify the workflow
before activating another batch. If a batch fails, reverse just its activation
commit and redeploy; do not restore databases for a mount rollback.

1. **Jellyfin/Bazarr:** verify every Jellyfin library path is under
   `/data/media/music`, `/pool/movies`, or `/pool/tv` and Bazarr paths/mappings
   fit the pool binds. Verify playback and subtitle access.
2. **qBittorrent/Arr:** verify live save paths fit `/data/downloads` or
   `/pool/downloads`, every movie/series path fits the matching pool root, and
   there are no incompatible remote mappings. Verify a disposable import.
3. **slskd:** check the read-only share and writable inbox, then verify download
   and tagging with disposable input.
4. **Music Manager/wrtag:** wait for the owner's base commit and the coordinated
   identity/rename change. Verify the takeover media source exists and matches
   `/mnt/data/media` by device and inode before directory creation. Verify
   rename and rollback with disposable input.
5. **Filebrowser:** verify allowlisted bind sources and existing ownership.
   Test intended access, password/passkey login, and moves across the new
   binds with disposable files. Keep forwarded-header trust disabled while
   container peers can reach Filebrowser without Caddy.

## Malice boot and disk maintenance

Require independent recovery proof, VM 100 verified at 4 GiB, tested console
access, and an on-site operator. Do not change fstab, the kernel pin, or drives
when any prerequisite is missing.

Check Secure Boot and match `BootCurrent` to the ESP by partition GUID.
Confirm the ESP filesystem UUID, that the pin selects `7.0.14-26-pve`, and
that `7.0.14-29-pve` is installed. Stop on mismatch. Only then persist
`UUID=14B4-0FF6 /boot/efi vfat umask=0077 0 2`, mount without formatting,
and use `proxmox-boot-tool kernel unpin`. Confirm GRUB defaults to the installed
`7.0.14-29-pve` before rebooting. Keep the signed shim/GRUB and
`7.0.14-26-pve`; do not run `grub-install` or initialize systemd-boot. On
failure select `7.0.14-26-pve` at the console and restore the pin. Verify the
kernel, guest autostart, virtiofs, iGPU, and apps before touching disks.

Confirm the retired disk is serial `ata-ST2000DX002-2DV164_Z4Z9F91S` and
has no mounts, storage/guest references, or open files. Stop the guests
gracefully and power off before removing only that disk. Label and shelf it
unwiped. Preserve the local restic and vault disks. After boot verify both
backup mounts, guest autostart, backups, apps, and alerts.

## Public service down

Check `homelab-public-check` logs and compare `vps/sites/*.caddy` with the live
VPS configuration before changing applications. If many vhosts fail together,
check shared layers first: the `/mnt/data` takeover bind, WireGuard handshakes
on both ends, and `docker ps` for mass exits. Do not restart stacks one by one.
For an isolated application failure, inspect its logs and restart its Compose
service. Record detection and recovery times.

## Private edge

Fix the git-owned `stacks/edge/Caddyfile`, validate the configuration before
restart, deploy the committed change, then run `make edge-reload`.
Caddy reads the bind-mounted configuration at startup; unchanged Compose files
do not trigger a restart. Check the actual route afterward.
Use exact host matchers, never `map` for routing; unknown hosts must return 404.

## VPS Caddy

Fix the git-owned site file and run `make vps`; validation must block a bad
configuration before reload. See the [VPS contract](vps/README.md).

## WireGuard

Keep console/fallback access before interrupting a tunnel. Inspect handshakes
with `wg show` on each end. The backend interfaces are VPS `chill0` and
chill-01 `wg0`; restart only the affected `wg-quick@<interface>` unit.
If handshakes stay stale, check the underlay first: chill-01 must reach the VPS
endpoint `194.58.47.21` directly. A broken gateway route or stale router ARP
can kill the tunnel without WireGuard errors. Never edit `/etc/wireguard`.

## Stale backup or failed alerts

Inspect the backup unit's journal and latest successful snapshot. Repair the
cause and run the backup; never refresh a success marker without a real success.
`homelab-backup-watchdog` alerts after 48 hours. Retention keeps three snapshots
per repository and refuses unexpected backup path sets; do not bypass that guard.

Check Prometheus → Alertmanager → bridge → Gotify, plus `notify@` delivery.
After host deployment/reboot, verify backup/check timers and run
`homelab-pipeline-check` and `homelab-alert-check`. The external WAN Worker and
Healthchecks cover loss of chill-01/Gotify; a green public application alone
does not prove notification delivery.

## History

Record dated incidents, maintenance and drill results in
[operations history](docs/history/2026-09-11-operations.md), not in the procedures
above. Historical commands and status are not current instructions.
Completed work and prior verification are in the
[2026-11-25 backlog snapshot](docs/history/2026-11-25-backlog.md).
