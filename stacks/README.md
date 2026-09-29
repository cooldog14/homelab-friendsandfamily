# stacks

Docker Compose stacks for chill-01. `make deploy` syncs this folder to
`/opt/stacks`; live `.env` files and `state/` stay on the host.

## map

- apps: Filebrowser Quantum, family files, upload drop
- photos: Immich
- docs: Paperless, Stirling PDF, Kavita
- comms: Mumble, Neko, Screego
- games: Minecraft Paper
- media: Jellyfin, qBittorrent, Prowlarr, Radarr, Sonarr, Bazarr, Jellyseerr,
  Navidrome, Octo-Fiesta, Feishin, Suwayomi, slskd, wrtag
- observability: Gotify, Beszel
- edge: private Caddy for `*.h.malice.biz`

Public HTTP routes live in `vps/sites/*.caddy`; private tailnet routes live in
`edge/Caddyfile`. Bulk video is `/mnt/pool`; important app/photo/music data is
`/mnt/data`; scratch/cache is `/mnt/fast`.
