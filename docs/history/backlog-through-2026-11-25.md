# Backlog archive through 2026-11-25

This compilation includes earlier work and dated verification (including the
November 18 baseline). The heading date is the archival cutoff, not an audit
window. Checkboxes, boot/disk instructions, and protocol results are historical;
use [TODO](../../TODO.md) and the [runbook](../../RUNBOOK.md) for current work.

See the [history index](README.md) for dated entries.

Historical detail is retained separately:

- [2026-10-25 audit](2026-10-audit.md)
- [pre-audit backlog](2026-pre-audit-backlog.md)

### 2026-11-25 — alert-path hardening (deployed)

Detail: [notification-path hardening](2026-11-25-notification-hardening.md#maintenance-2026-11-25-harden-the-whole-notification-path).
Commits `12fa7f6`..`09ed30b` + `3a46e12` are pushed.

- [x] **Deploy the alert-path commits.** Done 2026-11-25. Order used:
  `make vps` → `make hypervisor` → `host/deploy.sh chill-01` → `make host` →
  start `homelab-pipeline-check`/`homelab-alert-check` once → `wrangler deploy`.
  `host/deploy.sh` (what `make deploy` runs) was invoked directly because the
  workstation has no Docker daemon for the `check` prerequisite; all checks
  were run locally or on the live hosts. VPS-first ordering avoids a
  `homelab-public-check` failure against the not-yet-published vhost.
  **Verified:** 29 Prometheus rules loaded, 2 inhibit rules,
  `DISPATCH_ERRORS=true`, `pipeline-health` healthy on `10.44.0.2:8098`,
  all four `homelab_alert_path_healthy` components at 1,
  `https://health.malice.biz` returns `{"ok": true}` from the internet,
  14 public + 16 private + 4 TCP probes green, `homelab-public-check` exit 0
  (14 HTTP + 4 TCP), `homelab-alert-check` POST 200, zero firing alerts,
  zero failed units on all three hosts, `wrangler tail` logs
  `all 14 public targets healthy` / `heartbeat 200 ok`, malice backup-stats
  reports 15 snapshots on its own repo with no bogus `local` series,
  `.deployed-commit` = `3a46e12`.
- [ ] **Confirm the Healthchecks notification channel.** The check's delivery
  channel (email/push/etc.) and the 5m/15m grace are external config, not in
  git. Verify a real `/fail` produces a notification and a recovery ping
  clears it.
- [ ] **Re-test one real failure path.** Audit A1 only proved a synthetic
  `notify@audit-test.service` POST. Break a harmless path (e.g. a planned VPS
  restart that fails `homelab-public-check`) and confirm both chains deliver:
  `notify@` → Gotify and `HomelabJobFailed` → bridge → Gotify.

### P0 — safety and security

- [ ] **Complete the disk retirement (blocked: needs on-site access).** Nothing
  was moved this round by design: `/mnt/pool/.diskmove` still does not exist,
  `sda` is still mounted at `/mnt/backup`, and `sdc` stays offlined. Stage local
  restic and VM dumps before any physical pull, then pull `sdc` + `sda` and keep
  `sdb` (`/mnt/vault`). **Verify:** `/mnt/pool/.diskmove` byte-verified, mounts
  rebuilt, dumps and local restic readable, public checks green after reboot.
- [x] **Deploy the WAN prober.** Cloudflare Worker `homelab-wan-heartbeat` runs
  on a five-minute cron and stores the Healthchecks URL as a write-only secret.
  Three consecutive scheduled runs logged `all 13 public targets healthy` /
  `heartbeat 200 ok`. The old VPS heartbeat and GitHub workflow are removed.
  Raw TCP DNAT remains covered by `homelab-public-check.timer` on `chill-01`.
- [x] **Restore CrowdSec HTTP enforcement.** Caddy 2.11.9 and CrowdSec 1.8.2
  come from their own repositories; the nftables bouncer has input+forward
  hooks and acquires the Caddy access log. A real scanner was banned in the
  first scan after the restart.

### P1 — recovery, exposure and maintenance

- [x] **Immich on PostgreSQL 18 / v3.4.1.** PG 14.19 → 18.4, vchord 0.4.3 →
  1.1.1, pgvector 0.8.1 → 0.8.5; asset/album/user counts unchanged. The old
  cluster was removed after backup and restore validation; no `14.bak` remains.
  Cosmetic `immich-admin schema-check` warning is documented.
- [x] **Normalise backup retention.** Both repositories keep exactly three
  current-path snapshots, enforced by `host/restic-retention.py`. VM images stay
  local: rebuild from git plus offsite application data.
- [x] **Apply the container-hardening baseline.** All 42 services have
  `no-new-privileges` and `cap_drop: [ALL]` except the documented privileged
  cAdvisor; capabilities are added back only where an image proves it needs
  them. No arbitrary `user:` or `read_only:` was forced.
- [x] **Clear the update backlog and add update automation.** Host and VPS
  packages are current; Dependabot replaces Renovate for the pinned stacks.
- [x] **Codify the VPS Caddy package source.** Cloudsmith Caddy and packagecloud
  CrowdSec repositories are in `vps_edge`.
- [x] **Hypervisor maintenance and capacity alerting.** A fresh vzdump of all
  three guests completed and notified Gotify; `full-upgrade` cleared the package
  queue. `HypervisorMemoryLow` and `HypervisorSwapIn` are loaded.
- [ ] **Refresh the hypervisor's EFI boot menu (needs console access).**
  `7.0.14-29-pve` is installed and GRUB lists it first, but the host boots
  `7.0.14-26-pve` because the ESP (`sde2`) is not mounted at `/boot/efi`.
  Mount it, add the fstab entry (`vfat umask=0077`), run `grub-install` and
  `update-grub`, then reboot with the provider console ready. **Verify:**
  `uname -r` reports `7.0.14-29-pve` and all guests autostart.
- [ ] **Address the power-loss risk (accepted, hardware absent).** No UPS or NUT
  units exist. Mitigation is alerting only: memory/swap alerts, host-down rule
  and nightly vzdump. Revisit when a UPS is bought.
- [ ] **VPS root-key and secret-rotation risk (accepted policy).** Two
  unrestricted root authorized keys, `/root/chill0-priv`, and timestamped
  WireGuard private-key copies remain. Closed only if this stays explicit
  policy.
- [ ] **Minecraft stays public without a whitelist (accepted).** `white-list`
  remains false and RCON enabled; revisit if the player base grows.
- [x] **Retire the broken PVE mail path.** The matcher targets `gotify`; the
  stale queue is drained and a fresh vzdump notified through Gotify.

### P2 — drift and hygiene

- [x] **Pin the Ansible control node.** `make ansible-bootstrap` creates a
  gitignored `.venv` on Python 3.12 with ansible-core 2.20.7; the Make targets
  use it automatically. Full VPS playbook reports `changed=0`. Revisit when
  ansible-core supports Python 3.14; hosts keep Debian Python 3.13.
- [x] **Schedule SMART tests and route alerts.** Ansible manages
  `/etc/smartd.conf`; all five disks run short tests daily and staggered long
  tests. Initial short tests completed without error on `sda`, `sdb`, `sdd`,
  `sde` and `sdf`; the Gotify notifier test returned 0.
- [x] **Monitor the private edge.** `blackbox-private` probes all 16
  `*.h.malice.biz` vhosts; `PrivateEndpointDown` and
  `TLSCertExpiringSoonPrivate` page through Alertmanager/Gotify. The
  dashboard reads the same series instead of making its own TLS probes.
- [ ] Add app-level health instrumentation where Docker has none (Caddy
  admin, Jellyseerr, Navidrome, Radarr/Sonarr/Bazarr).
- [ ] Alert on arr queue rot: Sonarr/Radarr items stuck in
  `importBlocked`/`importPending` for more than 24h, and executable
  payloads under `/mnt/data/downloads`. The 2026-11-18 incident showed
  fake `.exe`/archive releases and incomplete packs can sit in the queue
  for weeks without an alert.
- [ ] Narrow the eight broad `/mnt/data` mounts; add Filebrowser proxy-header
  handling behind Caddy.
- [x] **Clean the stale UFW rules.** Removed the retired Beszel `45876` IPv6
  rule and the duplicate no-proto LAN SSH/media rules; the canonical proto rules
  remain. Jellyfin's LAN bind was already blocked by `DOCKER-USER`, so add the
  narrow established-only return exception for TCP/8096; LAN test returns 302.
- [x] **Enable HTTP/3.** Allow UDP/443 in `vps/firewall.nft`; an external curl
  negotiates `http_version=3` and returns 200/302.
- [ ] Add HSTS/baseline headers, CAA, DNSSEC and an explicit null MX; document
  IPv4-only public service.
- [x] **Clean the VPS.** Removed `6.12.116`, archived older nftables/Caddy/SSH
  backups under `/root/archive/2026-11-18`, and purged idle Docker plus the
  unused `wg-easy` image. Root usage is now 14%; Caddy/CrowdSec/WireGuard stay
  active.
- [x] **Pin the floating image tags.** Paperless Postgres 16.15-alpine, both
  Redis services 7.4.11-alpine, Gotenberg 8.37.0; deployed and healthy.
- [ ] Prune `chill-01`’s ~260 MB build cache and the old DB `.bak` files
  (~185 MB) after confirming the latest restic snapshot.
- [ ] Disable Tailscale key expiry for `chill-01` and `malice` if they should
  remain infrastructure nodes beyond March 2027.
- [ ] Fix current doc drift: `AGENTS.md` sde usage, `vps/README` missing
  `vps/firewall.nft`, edge bootstrap comments, and photos/games “mirror disk”
  comments. Historical RUNBOOK bootstrap references are expected history.
- [ ] Repeat the restore drill quarterly and keep the result in the runbook.

### decisions

- [ ] Accept, move, or separate the P2P exit currently using the VPS public IP;
  an abuse complaint could suspend the whole edge.
- [ ] Decide whether full VM images need offsite retention or whether
  rebuild-from-git plus offsite app data is the accepted recovery model.
- [ ] Keep the current offline tailnet devices registered unless explicitly
  revoked.

### verified healthy / closed — 2026-11-18

- 43/43 containers up, health checks green, no failed systemd units, no active
  Prometheus alerts, and no observed container restarts.
- 3 VMs running; public edge 13 HTTP + 4 TCP green; all 16 private vhosts return
  200/302/401; HTTP/3 returns 200/302.
- Isolation: `DOCKER-USER` rules restored after reboot; private admin ports no
  longer bind `10.44.0.2`; Jellyfin LAN playback returns 302.
- SMART: `smartd` active on `malice`; all five disks passed an initial short
  self-test; alerts route through the Gotify `ALERT_URL`.
- VPS and `chill-01` rebooted cleanly; persisted firewall/NAT, WireGuard,
  gluetun egress, and the Worker heartbeat recovered.
- Backups: last success 2026-11-17 04:26 UTC; 21 SQLite dumps, three Bolt
  snapshots, Suwayomi archive; expanded restore drill passed (40 paths, 1.63
  GiB; cold 6m45s, warm 1m22s).
- External alert failure/recovery accepted; PVE Gotify target tested; Worker
  scheduled runs verified.
- Media pipeline: Prowlarr 3.0.2, Sonarr 4.0.20 and Radarr 7.0.3 deployed;
  EZTV pinned to `eztv.yt` behind FlareSolverr; all three app health checks
  are clean.
- Closed/stale historical items: broad WireGuard exposure, admin-port exposure,
  Neko lateral movement, boot guard, backup dump atomicity, reboot/backup
  overlap, public-check independence, PVE notification absence, sdc NFS/virtiofs
  state, failed relay, Beszel, old slskd/wrtag auth, current Prowlarr/Sonarr
  log key leakage, and stale Filebrowser log key leakage.
