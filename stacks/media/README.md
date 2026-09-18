# media

Media runs on chill-01.

## data

DATA_LOCATION defaults to /mnt/data (mirror disk: music, documents,
slskd dirs). Bulk video lives on the 4TB disk, mounted at /mnt/pool.

- movies: /pool/movies (jellyfin ro, arr apps rw) — change library and
  root-folder paths to /pool/* in the app UIs, not /data/...
- tv: /pool/tv (same)
- video downloads: /pool/downloads (point qBittorrent save paths here)
- music: /mnt/data/media/music
- manga: managed by Suwayomi state
- uploads: /mnt/data/downloads/uploads through Filebrowser Quantum
- slskd complete: /mnt/data/downloads/slskd/complete
- slskd incomplete: /mnt/data/downloads/slskd/incomplete

## network

qbittorrent, prowlarr, flaresolverr and slskd ride the gluetun service
(custom WireGuard to the VPS), so P2P never egresses via the home IP.
Gluetun publishes their ports on WG_IP; the apps reach each other by
service name. FIREWALL_OUTBOUND_SUBNETS covers 172.16.0.0/12 because
compose bridge subnets are assigned dynamically.

## secrets

Copy .env.example to .env on chill-01.
Fill the secrets there.
Never commit .env.

## notes

WireGuard is not part of this stack.
Suwayomi is private at suwayomi.h.malice.biz.
