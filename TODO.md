# todo

## next (updated 2026-09-29)

### P0 — access, secrets, and recovery

- Rotate app passwords/tokens without printing them. Do `.env`-backed
  secrets first (stack `.env`, `host/homelab.env`, deploy/restart), then
  app-internal users/API keys, then the Screego users file. Record rotation
  dates only, never values.
- Audit macbook/towa/hermes-01; move wanted devices to UndauntedGeiger and
  revoke old auth keys. Use `HOST=chill-01`; `deploy@10.44.0.2` is not the
  people/admin path.
- Filebrowser admin passwords rotated 2026-09-28 (quantum, family, upload,
  LOGIN_OK).
- Run one `make restore-test` drill to a temp path, record the result in
  `RUNBOOK.md`, and repeat quarterly.
- Add app/ingress HTTP healthchecks after live endpoint confirmation: private
  Caddy, Immich, Paperless, Jellyfin, Gotify, and Beszel.

### P1 — hardening, validation, and monitoring

- When `chill-01` is reachable, deploy the repo and verify slskd's default
  image can run `/app/scripts/autotag.sh --self-check`; verify
  `cockpit.h.malice.biz` works and Cockpit is blocked from the VPS/WireGuard
  side.
- Verify `homelab-backup-watchdog`, latest cloud + local snapshots,
  `homelab-docker-prune.timer`, and the Beszel >85% disk Gotify alert.
- Verify Jellyfin HLS/cache on `/mnt/fast/jellyfin-cache`; delete old empty
  cache dirs only after confirming no active references.
- Tighten `chill-01` UFW from broad active `wg0`/`10.44` allow to exact
  inbound ports needed from the VPS. Keep Tailscale broad only if tailnet ACLs
  enforce identity.
- Add cheap hardening to public/privileged containers first:
  `no-new-privileges`, explicit non-root `user` where supported, `cap_drop:
  [ALL]`, and read-only mounts where they do not break stateful apps.
- Compare live VPS input/forward rules against `vps/README.md` and fix drift.

### P2 — policy and drift control

- Consider digest pinning only for public or privileged containers if Renovate
  tag updates are not enough.
