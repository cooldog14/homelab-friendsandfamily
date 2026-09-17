# media

Media runs on chill-01.

## data

DATA_LOCATION defaults to /mnt/data.

- movies: /mnt/data/media/movies
- tv: /mnt/data/media/tv
- music: /mnt/data/media/music
- uploads: /mnt/data/downloads/uploads through Filebrowser Quantum
- slskd complete: /mnt/data/downloads/slskd/complete
- slskd incomplete: /mnt/data/downloads/slskd/incomplete

## secrets

Copy .env.example to .env on chill-01.
Fill the secrets there.
Never commit .env.

## music ingest

ingest-music.sh imports stable uploads into the music library.
It reads /etc/media-music-ingest.env.
It can self-check with the --self-check flag.

## notes

WireGuard is not part of this stack.
