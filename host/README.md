# host

These files install on chill-01.

bootstrap.sh prepares Debian.
It installs Docker, Tailscale, WireGuard, restic, timers, and host scripts.
It removes Cockpit.

Tailscale is for people.
WireGuard is for the VPS link only.

## backup

backup.sh runs nightly through systemd.
It dumps live databases first.
It backs up config, stack state, photos, and secrets.
It skips downloads, movies, and TV.
DB dumps stage in `/mnt/fast/dumps` before restic snapshots them.
It writes the same important-data set to Hetzner S3 and the local repo
(`/mnt/backup/restic` on sda; OPEN as of 2026-09-21: chill-01 cannot see
/mnt/backup yet — repo wiring, i.e. a new virtiofs share or host-side
restic, belongs to the backups phase; `restic init` still owed).

VPS config is pulled into the restic backup.
A failed VPS pull alerts but does not fail the home backup.

## checks

public-check.sh checks public sites and TCP forwards through the VPS.
It reads HTTP hosts from /opt/homelab-public-sites, synced by make deploy and make vps.
UDP forwards are documented but not smoke-tested.
backup-watchdog.sh runs daily and alerts when backups are older than 48h.
Beszel handles disk health and alerts.
Use a native Proxmox scheduled backup job for VM snapshots.
Live since 2026-09-21: `weekly-vault` job (all guests, snapshot mode,
zstd, Sundays 03:30, keep-last 8) writes to the `data` store on
/mnt/vault; proof snapshot of alpine-102 ok.

## secrets

homelab.env lives in /etc.
Keep it mode 0600.
Never commit it.
