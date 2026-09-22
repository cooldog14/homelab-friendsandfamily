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
| `/mnt/data` 2TB mirror | `/mnt/data/photos`, `/mnt/data/family`, `/mnt/data/apps/<app>`, `/mnt/data/media/music`, `/mnt/data/media/books` | Immich, private Quantum, public family Filebrowser, music upload, Paperless, Stirling, Suwayomi, Navidrome/slskd |
| `/mnt/pool` 4TB HDD | `/mnt/pool/media/movies`, `/mnt/pool/media/tv`, `/mnt/pool/downloads` | Jellyfin read-only media, qBittorrent, Radarr, Sonarr; re-downloadable, excluded from backup |
| `/mnt/backup` 1TB HDD (`sda`) | future `/mnt/backup/restic` | local restic copy of important data for 3-2-1 backup; not exposed to family apps. Cleared 2026-09-21 (~553G stale mirror/scratch removed); `restic init` still owed |
| `/mnt/vault` 466G (`sdb`, ex-`/mnt/archive`) | `/mnt/vault/dump`, `/mnt/vault/backup-old-vm-lxc` | Proxmox vzdump target (`data` store, weekly `weekly-vault` job, keep-last 8); holds flagged pre-migration keeps, not apps |

Family storage: Immich writes photos to `/mnt/data/photos`; public `files.malice.biz` exposes only `/mnt/data/family`; public upload is music-only at `/mnt/data/media/music/inbox/user`; private Quantum starts at `/mnt/data`, exposes `/srv/pool`, and has passkeys enabled. Keep private Quantum on Tailscale.

## deploy

- make deploy updates VM
- make storage-cleanup migrates old storage paths into the app/media layout
- make vps updates the VPS
- make host bootstraps VM 
- make edge-reload restarts private Caddy
- make check validates compose and shell files
