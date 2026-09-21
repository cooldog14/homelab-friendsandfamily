# homelab

VM 101 runs the apps.
The VPS is the public edge.
Tailscale is private admin access.
WireGuard is only VPS to VM.

## layout

- host: VM bootstrap, backups, host timers
- stacks: Docker Compose apps
- vps: public Caddy, nftables, WireGuard endpoint

## storage map

| Disk/mount | Saves here | Services |
|---|---|---|
| VM 101 root SSD | `/opt/stacks/*/state`, Docker images, app configs/DBs | Compose state, not bulk files |
| `/mnt/fast` 500GB SSD | `/mnt/fast/jellyfin-cache`, `/mnt/fast/scratch`, `/mnt/fast/imports`, `/mnt/fast/dumps` | Disposable scratch/cache: Jellyfin HLS/transcodes, temp imports/conversions, backup dumps; not exposed in Filebrowser |
| `/mnt/data` 2TB mirror | `/mnt/data/photos`, `/mnt/data/downloads/uploads`, documents, clean music, app data | Immich, Filebrowser Quantum, public upload, Paperless, Navidrome/slskd |
| `/mnt/pool` 4TB HDD | `/mnt/pool/media/movies`, `/mnt/pool/media/tv`, `/mnt/pool/downloads` | Jellyfin read-only media, qBittorrent, Radarr, Sonarr; re-downloadable, excluded from backup |
| `/mnt/backup` 1TB HDD (`sda`) | future `/mnt/backup/restic` | local restic copy of important data for 3-2-1 backup; not exposed to family apps. Cleared 2026-09-21 (~553G stale mirror/scratch removed); `restic init` still owed |
| `/mnt/vault` 466G (`sdb`, ex-`/mnt/archive`) | `/mnt/vault/dump`, `/mnt/vault/backup-old-vm-lxc` | Proxmox vzdump target (`data` store, weekly `weekly-vault` job, keep-last 8); holds flagged pre-migration keeps, not apps |

Family storage: Immich writes photos to `/mnt/data/photos`; Filebrowser Quantum starts at `/mnt/data`, exposes `/srv/pool`, and has passkeys enabled. Keep Quantum private/Tailscale; use the public upload app only for drop-box style sharing.

## deploy

- make deploy updates VM
- make vps updates the VPS
- make host bootstraps VM 
- make edge-reload restarts private Caddy
- make check validates compose and shell files
