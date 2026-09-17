# stacks

Docker Compose stacks run on chill-01.

make deploy syncs this folder to /opt/stacks.
Stack .env files and state folders stay on the host.

## stacks

- apps: Filebrowser Quantum, public upload drop
- photos: Immich
- docs: Paperless, Stirling PDF, Kavita
- comms: Mumble, Neko, Screego
- media: Jellyfin, qBittorrent, Prowlarr, Radarr, Sonarr, Bazarr, Jellyseerr, Navidrome, Octo-Fiesta, Feishin, Suwayomi, slskd, wrtag
- observability: Gotify, Dockge, Beszel
- edge: private Caddy and homepage

## private routes

These routes work on Tailscale only.

- home.h.malice.biz
- dockge.h.malice.biz
- files.h.malice.biz
- gotify.h.malice.biz
- beszel.h.malice.biz
- qbittorrent.h.malice.biz
- prowlarr.h.malice.biz
- radarr.h.malice.biz
- sonarr.h.malice.biz
- bazarr.h.malice.biz
- slskd.h.malice.biz
- wrtag.h.malice.biz
- suwayomi.h.malice.biz
