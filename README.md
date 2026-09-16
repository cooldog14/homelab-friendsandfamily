# arr

Media stack for LXC 203 on normandie.

## public routes

- jellyfin.malice.biz -> 127.0.0.1:8096
- requests.malice.biz -> 127.0.0.1:5055
- player.malice.biz -> 127.0.0.1:9180
- fiesta.malice.biz -> 127.0.0.1:5274
- upload.malice.biz -> 127.0.0.1:5000

These routes are defined in Caddyfile.

## compose services

- jellyfin
- gluetun
- qbittorrent
- prowlarr
- flaresolverr
- radarr
- sonarr
- bazarr
- jellyseerr
- navidrome
- wrtag
- octo-fiesta
- feishin
- dufs
- slskd
- caddy

## deploy

Enter the LXC.

    ssh root@100.90.216.64 "pct exec 203 -- bash"

Run Compose from the arr directory.

    cd /opt/arr
    docker compose pull --ignore-buildable
    docker compose up -d --build

## data

DATA_LOCATION defaults to /mnt/data.

- movies: /mnt/data/media/movies
- tv: /mnt/data/media/tv
- music: /mnt/data/media/music
- uploads: /mnt/data/downloads/uploads
- slskd complete: /mnt/data/downloads/slskd/complete
- slskd incomplete: /mnt/data/downloads/slskd/incomplete

Containers mount the shared data tree as /data where possible.

## local state

These paths are container state and stay out of git.

- .env
- jellyfin-config
- jellyfin-cache
- radarr
- sonarr
- prowlarr
- bazarr
- jellyseerr
- qbittorrent
- gluetun
- navidrome
- octo-fiesta
- slskd
- wrtag

## env

Copy .env.example to .env.
Fill the secrets there.
Do not commit .env.

## music ingest

scripts/ingest-music.sh imports stable uploads into the music library.

Upload path:

    /mnt/data/downloads/uploads

Env file:

    /etc/arr-music-ingest.env

Required values:

    SUBSONIC_ADMIN_USERNAME='navidrome-admin'
    SUBSONIC_ADMIN_PASSWORD='navidrome-password'
    GOTIFY_URL='https://gotify.malice.biz/message?token=APP_TOKEN'
    IMPORT_MIN_AGE_MINUTES='2'

Install cron for the UID 1000 user.

    user=$(getent passwd 1000 | cut -d: -f1)
    sudo crontab -u "$user" -e

Cron line:

    */5 * * * * set -a; . /etc/arr-music-ingest.env; set +a; flock -n /tmp/arr-music-ingest.lock /opt/arr/scripts/ingest-music.sh

Self-check:

    /opt/arr/scripts/ingest-music.sh --self-check

## notes

Gluetun provides networking for qbittorrent, prowlarr, flaresolverr, and slskd.
slskd builds from Dockerfile.slskd.
Caddy uses host networking and Caddyfile.
dufs serves the upload directory.
DUFS_ALLOW_DELETE stays false.
