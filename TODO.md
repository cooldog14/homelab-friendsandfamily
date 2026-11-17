# todo

## active queue — last reviewed 2026-11-18

Historical detail is retained separately:

- [2026-10-25 audit](docs/history/2026-10-audit.md)
- [pre-audit backlog](docs/history/2026-pre-audit-backlog.md)

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
- [ ] Add private app health instrumentation where Docker has none (Caddy,
  Jellyseerr, Navidrome, Radarr/Sonarr/Bazarr) and monitor the private edge.
- [ ] Narrow the eight broad `/mnt/data` mounts; add Filebrowser proxy-header
  handling behind Caddy.
- [ ] Remove the stale IPv6 UFW rule for retired Beszel port `45876` and the
  duplicate LAN SSH/media rules.
- [ ] Fix HTTP/3: Caddy advertises `h3`, but the VPS firewall does not allow
  UDP/443. Either allow `udp 443` or disable h3.
- [ ] Add HSTS/baseline headers, CAA, DNSSEC and an explicit null MX; document
  IPv4-only public service.
- [ ] Remove VPS `.bak` clutter safely, autoremove the old `6.12.116` kernel,
  and remove idle Docker (no containers; one unused `wg-easy` image).
- [ ] Clean remaining host images/cache and pin floating tags
  (`postgres:16.15-alpine`, `redis:7.4.11-alpine`, `gotenberg:8.37.0`).
  Live cleanup is ~260 MB build cache on `chill-01` plus ~185 MB old DB
  backups; VPS root is 18%, not the old 76% claim.
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

### verified healthy / closed — 2026-11-17

- 42/42 containers up, health checks green, no failed systemd units, no active
  Prometheus alerts, and no observed container restarts.
- 3 VMs running; public edge 13 HTTP + 4 TCP green; all 16 private vhosts return
  200/302/401.
- Isolation: 89 `DOCKER-USER` rules restored after reboot; private admin ports
  no longer bind `10.44.0.2`.
- VPS and `chill-01` rebooted cleanly; persisted firewall/NAT, WireGuard,
  gluetun egress, and the Worker heartbeat recovered.
- Backups: last success 2026-11-17 04:26 UTC; 21 SQLite dumps, three Bolt
  snapshots, Suwayomi archive; expanded restore drill passed (40 paths, 1.63
  GiB; cold 6m45s, warm 1m22s).
- External alert failure/recovery accepted; PVE Gotify target tested; Worker
  scheduled runs verified.
- Closed/stale historical items: broad WireGuard exposure, admin-port exposure,
  Neko lateral movement, boot guard, backup dump atomicity, reboot/backup
  overlap, public-check independence, PVE notification absence, sdc NFS/virtiofs
  state, failed relay, Beszel, old slskd/wrtag auth, current Prowlarr/Sonarr
  log key leakage, and stale Filebrowser log key leakage.
