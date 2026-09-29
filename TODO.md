# todo

## next (updated 2026-09-29)

### P0 — access and secrets

- Rotate app passwords/tokens without printing them. Do `.env`-backed
  secrets first (stack `.env`, `host/homelab.env`, deploy/restart), then
  app-internal users/API keys, then the Screego users file.
- Finish tailnet cleanup only if those devices still matter: move
  macbook/towa/hermes-01 to UndauntedGeiger and revoke old auth keys. Use
  `HOST=chill-01`; `deploy@10.44.0.2` is not the people/admin path.
- Retire legacy edge leftovers after primary access is proven: old
  `wg0`/10.30 rules, Mumble DNAT verification, and stale fallback refs.

### P1 — backup and monitoring

- Run one `make restore-test` drill to a temp path.
- When `chill-01` is reachable, deploy the repo and verify Dockge is gone,
  `/opt/homelab-public-sites` is no longer needed by public-check, and slskd's
  default image can run `/app/scripts/autotag.sh --self-check`; remove any
  leftover `homelab-disk-usage` unit/script if still present; verify
  `cockpit.h.malice.biz` works and Cockpit is blocked from the VPS/WireGuard
  side.
- After 2026-09-30, verify `homelab-backup-watchdog`, latest cloud +
  local snapshots, `homelab-docker-prune.timer`, and the Beszel >85%
  disk Gotify alert.
- Verify Jellyfin HLS/cache on `/mnt/fast/jellyfin-cache` during the
  next real playback; delete old empty cache dirs only after confirming
  no active references.

### P2 — apps and family-facing services

- Run Minecraft Chunky pregen (`chunky radius 2500`, `chunky start`) the
  night before launch day, not during backups.
- Watch photos: uploads should land on `/mnt/data`; revisit only if the
  Immich library or VM `/data` volume grows.
- Monitor post-boot WebUI login noise from suwayomi/wrtag/qBittorrent;
  act only if it recurs while services are in use.

### P3 — repo hygiene

- Add minimal GitOps/systemd deploy or drift check only if `make deploy`
  stops being enough.
