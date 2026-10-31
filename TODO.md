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

- ~~When `chill-01` is reachable, deploy the repo and verify slskd's default
  image can run `/app/scripts/autotag.sh --self-check`; verify
  `cockpit.h.malice.biz` works and Cockpit is blocked from the VPS/WireGuard
  side.~~ Verified 2026-10-30: `autotag self-check ok`, `cockpit.h.malice.biz`
  returns 200 over Tailscale, UFW denies 9090 on `wg0`. Also confirmed
  Jellyfin transcodes on `renderD128` via VAAPI.
- FIXED 2026-10-30: Beszel had zero alert rules and had been blind since the
  10-23 reboot (UFW allowed `45876` only over IPv6). Added the
  `172.16.0.0/12 -> 45876` rule (live + `bootstrap.sh`), created the Gotify
  app `beszel`, set the webhook and `meta.appURL`, and added `Disk >85% for
  5m`. Delivery proven by a real Gotify message before the threshold was
  raised.
- malice has 27 pending package upgrades including kernel `7.0.14-26` and
  `pve-manager 9.2.24`; needs a window (vzdump first, then reboot), no
  `/var/run/reboot-required` yet.
- Verify `homelab-backup-watchdog`, latest cloud + local snapshots,
  `homelab-docker-prune.timer`, and the Beszel >85% disk Gotify alert.
  - Done 2026-10-30: timers active, cloud snapshot 2026-10-30 04:17Z, local
    04:18Z, public-check green, 0 OOM kills in 7d (mem limits holding).
  - Done 2026-10-30: the Beszel disk alert now exists and delivers to Gotify
    (test fire landed as Gotify message id 3).
- Verify Jellyfin HLS/cache on `/mnt/fast/jellyfin-cache`; delete old empty
  cache dirs only after confirming no active references.
- ~~Tighten `chill-01` UFW from broad active `wg0`/`10.44` allow to exact
  inbound ports needed from the VPS.~~ Done 2026-10-30: `wg0` now allows only
  `from 10.44.0.1` (v4+v6). Tailscale stays broad; tailnet ACLs are the gate.
- Add cheap hardening to public/privileged containers first:
  `no-new-privileges`, explicit non-root `user` where supported, `cap_drop:
  [ALL]`, and read-only mounts where they do not break stateful apps.
- ~~Compare live VPS input/forward rules against `vps/README.md` and fix
  drift.~~ Done 2026-10-30: dead `25565 -> 10.30.0.3` and duplicate `6881`
  rules removed, P2P `6881`/`50300` moved into git `vps/nftables.conf`, VPS
  `wg0` peers trimmed to gluetun + three dead `10.30.0.5-7` entries.
  - Done 2026-10-30: deleted the dead `10.30.0.5/6/7` peers and the duplicate
    `eth0` DNATs in `inet firewall` (homelab_nat owns all DNAT now).
  - Open: the 2 TB `/mnt/primary` disk (sdc) threw unreadable-sector errors on
    2026-10-23 at boot. Long SMART scan started 2026-10-30; action depends on
    the result.

### P2 — policy and drift control

- Consider digest pinning only for public or privileged containers if Renovate
  tag updates are not enough.
