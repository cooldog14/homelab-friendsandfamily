# stacks

Docker Compose stacks run on chill-01.

make deploy syncs this folder to /opt/stacks.
`defaults.env` holds shared non-secret defaults; Makefile loads it for compose.
Stack .env files and state folders stay on the host.

## stacks

- apps: Filebrowser Quantum, public family files, public upload drop
- photos: Immich
- docs: Paperless, Stirling PDF, Kavita
- comms: Mumble, Neko, Screego
- games: Minecraft (Paper)
- media: Jellyfin, qBittorrent, Prowlarr, Radarr, Sonarr, Bazarr, Jellyseerr, Navidrome, Octo-Fiesta, Feishin, Suwayomi, slskd, wrtag
- observability: Gotify, Dockge, Beszel
- edge: private Caddy and homepage

## storage exposure

- Private Quantum (`files.h.malice.biz`) mounts `/mnt/data` and exposes
  bulk media under `/srv/pool`; keep it on Tailscale.
- Public family files (`files.malice.biz`) mounts only `/mnt/data/family`.
- Public upload (`upload.malice.biz`) mounts only
  `/mnt/data/media/music/inbox/user`.
- Immich writes photos to `/mnt/data/photos`.
- Kavita reads books from `/mnt/data/media/books`.
- Filebrowser auth enables passwords and passkeys from
  `apps/config/filebrowser/config.yaml`.

## private routes

These routes work on Tailscale only.

- home.h.malice.biz
- dockge.h.malice.biz
- files.h.malice.biz
- gotify.h.malice.biz
- beszel.h.malice.biz
- immich.h.malice.biz
- qbittorrent.h.malice.biz
- prowlarr.h.malice.biz
- radarr.h.malice.biz
- sonarr.h.malice.biz
- bazarr.h.malice.biz
- slskd.h.malice.biz
- wrtag.h.malice.biz
- suwayomi.h.malice.biz
