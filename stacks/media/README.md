# media

Practical notes for the media stack on chill-01 VM 101.
Routes live in Caddy files; services live in `docker-compose.yml`.

## data

`DATA_LOCATION` defaults to `/mnt/data`.

- movies: `/mnt/data/media/movies`
- tv: `/mnt/data/media/tv`
- music: `/mnt/data/media/music`
- uploads: `/mnt/data/downloads/uploads`
- slskd complete: `/mnt/data/downloads/slskd/complete`
- slskd incomplete: `/mnt/data/downloads/slskd/incomplete`

Containers mount the shared data tree as `/data` where possible.

## state and secrets

Copy `.env.example` to `.env` on chill-01 and fill the secrets there.
Container state lives under `state/`; deploy excludes it.

## slskd config

`config/slskd/slskd.yml` and `config/slskd/autotag.sh` are tracked in git.

slskd's YAML beats env vars, so `directories`, `shares`, and
`remote_configuration` in `slskd.yml` must stay in sync with the compose env
(`SLSKD_*_DIR`, `SLSKD_SHARED_DIR`, `SLSKD_REMOTE_*`).

## music ingest

`scripts/ingest-music.sh` imports stable uploads into the music library.

Env file:

    /etc/media-music-ingest.env

Required values:

    SUBSONIC_ADMIN_USERNAME='navidrome-admin'
    SUBSONIC_ADMIN_PASSWORD='navidrome-password'
    GOTIFY_URL='https://gotify.malice.biz/message?token=APP_TOKEN'
    IMPORT_MIN_AGE_MINUTES='2'

Cron line for the UID 1000 user:

    */5 * * * * set -a; . /etc/media-music-ingest.env; set +a; flock -n /tmp/media-music-ingest.lock /opt/stacks/media/scripts/ingest-music.sh

Self-check:

    /opt/stacks/media/scripts/ingest-music.sh --self-check

## notes

WireGuard is not part of this stack. The only WireGuard left is VPS to chill-01.
DUFS serves the upload directory. `DUFS_ALLOW_DELETE` stays false.
