# media

Media runs on chill-01.

## data

`../defaults.env` sets the shared stack defaults: DATA_LOCATION, WG_IP,
and TIMEZONE. DATA_LOCATION is the mirror disk for music, documents, and
app-scoped data. Bulk video lives on the 4TB disk, mounted at /mnt/pool.
Jellyfin HLS/transcode cache lives on the scratch SSD at /mnt/fast/jellyfin-cache.

- movies: /pool/movies (jellyfin ro, arr apps rw) — change library and
  root-folder paths to /pool/* in the app UIs, not /data/...
- tv: /pool/tv (same)
- video downloads: /pool/downloads (point qBittorrent save paths here)
- music inbox: /mnt/data/media/music/inbox
- music final library: /mnt/data/media/music/clean
- manga: /mnt/data/apps/suwayomi
- uploads: /mnt/data/media/music/inbox/user through Filebrowser Upload
- slskd complete: /mnt/data/media/music/inbox/slskd/complete
- slskd incomplete: /mnt/data/media/music/inbox/slskd/incomplete

## network

qbittorrent, prowlarr, flaresolverr and slskd ride the gluetun service
(custom WireGuard to the VPS), so P2P never egresses via the home IP.
Gluetun publishes their ports on WG_IP from `../defaults.env`; the apps reach each other by
service name. FIREWALL_OUTBOUND_SUBNETS covers 172.16.0.0/12 because
compose bridge subnets are assigned dynamically.

## secrets

Use `../defaults.env` plus this stack's `.env` on chill-01.
Copy `.env.example` to `.env` and fill the secrets there.
Never commit .env.

## notes

WireGuard is not part of this stack.
Suwayomi is private at suwayomi.h.malice.biz and uses native `ui_login`
credentials from `.env`.
