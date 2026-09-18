# media

Media runs on chill-01.

## data

DATA_LOCATION defaults to /mnt/data.

- movies: /mnt/data/media/movies
- tv: /mnt/data/media/tv
- music: /mnt/data/media/music
- manga: managed by Suwayomi state
- uploads: /mnt/data/downloads/uploads through Filebrowser Quantum
- slskd complete: /mnt/data/downloads/slskd/complete
- slskd incomplete: /mnt/data/downloads/slskd/incomplete

## secrets

Copy .env.example to .env on chill-01.
Fill the secrets there.
Never commit .env.

## notes

WireGuard is not part of this stack.
Suwayomi is private at suwayomi.h.malice.biz.
