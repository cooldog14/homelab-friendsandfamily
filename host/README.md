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

VPS config is pulled into the restic backup.
A failed VPS pull alerts but does not fail the home backup.

## checks

public-check.sh checks public sites and TCP forwards through the VPS.
It reads HTTP hosts from /opt/homelab-public-sites, synced by make deploy and make vps.
UDP forwards are documented but not smoke-tested.
backup-watchdog.sh runs daily and alerts when backups are older than 48h.
disk-usage.sh publishes disk usage for the private homepage.
proxmox-backup.sh runs on the Proxmox host and snapshots VM 101.

## secrets

homelab.env lives in /etc.
Keep it mode 0600.
Never commit it.
