# todo

## next (updated 2026-10-21)

### P0 — access, secrets, and recovery

- sdc TAKEOVER ACTIVE (2026-10-16, reboot-proofed 2026-10-19): `/mnt/data`
  is a bind of `/mnt/pool/takeover-primary/r1/mnt/data` (sole fstab entry;
  see RUNBOOK incidents 2026-10-14/19). sdc confirmed DEAD (INQUIRY failed).
  Decide on-site: keep pool layout vs new 2TB disk + reverse-restore.
  Verify fresh backup snapshots, then prune Oct 14/15 partials.
- IPv4 RELAY TEMPORARY (2026-10-19): chill-01 default via malice
  (`/etc/netplan/99-homelab-relay.yaml`) + host MASQUERADE, because router
  ARP for .28 is stuck on ghost MAC `6e:44:04:45:5b:3d`. On-site: reboot
  router/clear ARP, verify direct .1 ping, remove relay files. See RUNBOOK.

- Guard `bootstrap.sh` `ensure_virtiofs` against `/mnt/data` takeover bind:
  `ensure_virtiofs pve1-primary /mnt/data` currently checks only for tag
  `pve1-primary` in `/etc/fstab`, so running `make host` will re-append dead
  `pve1-primary /mnt/data` and `mount -a` over the takeover bind. Check target
  mountpoint (`grep -Eq "[[:space:]]$target[[:space:]]" /etc/fstab`) too.
- Clean up dead `sdc` on `malice` (still mounted `emergency_ro` at
  `/mnt/primary` and ro-bound to `/mnt/bulk/media/music`, `virtiofs0:
  pve1-primary` still on VM 101, `smartd` logging ATA `0xE5` `DID_BAD_TARGET`
  errors every 30m, and `/etc/fstab` `pass=2` will fsck-stall on host reboot):
  unmount `/mnt/bulk/media/music` + `/mnt/primary`, comment both in
  `malice:/etc/fstab`, `qm set 101 --delete virtiofs0`, and offline kernel
  device (`echo 1 > /sys/block/sdc/device/delete`).
- Restore live VPS BBR — DONE 2026-10-21 via `make vps`
  (`net.ipv4.tcp_congestion_control=bbr`, `fq` qdisc live; verified new
  sockets negotiate bbr). requests/mg/jellyfin slowness was cubic + ~2-4%
  client-leg loss, not the backend.
- Lock down unauthenticated/admin services exposed on `wg0` (`10.44.0.2`) and
  VPS forward path:
  - `slskd` (`10.44.0.2:5030`, `authentication: disabled: true`, rw `/mnt/data`),
    `wrtag` (`10.44.0.2:7373`, `WRTAG_WEB_AUTH: "disabled"`, rw `/mnt/data`),
    and `flaresolverr` (`10.44.0.2:8191`, no auth) are reachable from the VPS
    and any peer routed to `10.44.0.0/24`.
  - Remove `10.44.0.2:8191:8191` publish from `gluetun` (`prowlarr` shares
    `service:gluetun` netns and uses `localhost:8191`).
  - Move private-only admin ports (`8085, 8070, 8090, 8701, 9696, 5030, 7878,
    8989, 6767, 7373`) off `10.44.0.2` (bind `127.0.0.1` + proxy via
    `host.docker.internal`, or shared internal edge network), and restrict
    `beszel-agent` (`*:45876` host net) to `LISTEN=127.0.0.1:45876` / Docker
    gateway.
  - On `vps-ingress`, retire remaining `wg0` (`10.30.0.1/24` `:51820`) peers
    (`malice` `.3`, external `.2` `109.0.200.185`, `.5`–`.7`; keep only
    `gluetun` `.4` if still used for P2P egress) and remove unconditional
    `ip daddr 10.44.0.0/24 accept` + `iifname "wg0" ip daddr 10.44.0.0/24
    accept` from `/etc/nftables.conf` `chain forward`.
- Rotate app passwords/tokens without printing them. Do `.env`-backed
  secrets first (stack `.env`, `host/homelab.env`, deploy/restart), then
  app-internal users/API keys, then the Screego users file. Record rotation
  dates only, never values.
- Tailnet is intentional and clean (owner confirmed 2026-10-31): offline
  phones/laptops stay registered on purpose. Do not revoke devices without
  asking. Use `HOST=chill-01`; `deploy@10.44.0.2` is not the people/admin
  path.
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
  `from 10.44.0.1` (v4+v6). Tailscale stays broad; tailnet ACLs are the gate.- Add cheap hardening to public/privileged containers first:
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

- FIXED 2026-10-31: `shellcheck` added to `bootstrap.sh` + Makefile falls back
  to the container image, so `make check` passes everywhere; public check now
  every 15 min; `notify@.service` logs delivery failures; prune keeps images of
  stopped containers; backup's VPS pull is atomic; Stirling is private-only
  (`stirling.h.malice.biz`), public vhost removed.
- Storage 2026-11-02 (SUPERSEDES the Oct-31 pve1-primary move): sdc retired
  (kernel-offlined, pull pending); guest 101 `/mnt/data` re-cut to the
  takeover bind `/mnt/pool/takeover-primary/r1/mnt/data` (fstab, reboot-tested
  Nov 2). Takeover is the live tree; see RUNBOOK maintenance 2026-11-02.
- Open: the Livebox still maps `192.168.1.28` to a dead phone MAC
  (`da:f6:59:14:fb:40`) even after deleting that device record and rebooting;
  `.28` sits inside the DHCP pool (`.10-.150`), so do not put a lab host back
  there. One more router reboot may clear it. chill-01 moved to
  `192.168.1.200` (outside the pool, so no DHCP reservation needed), the relay
  was removed, and Jellyfin rebinds to `192.168.1.200:8096` (update TV
  bookmarks). See RUNBOOK incident 2026-11-02.
- Open: secrets rotation (needs your values), malice host upgrade + kernel
  reboot, container hardening beyond what is documented.
- Bind Minecraft RCON to localhost (`RCON_HOST: 127.0.0.1` / `rcon.ip=127.0.0.1`
  in `stacks/games/docker-compose.yml`) instead of `0.0.0.0:25575` on the
  container bridge.
- DONE 2026-11-02: `mem_limit: 1536m` on qbittorrent, `swappiness=10` on
  malice, sata→scsi both guests (`virtio-scsi-single`, boot-tested).
- Evaluate moving latency-sensitive app state (`/mnt/data/apps/minecraft`,
  `/mnt/data/apps/suwayomi`) off the 4TB spinning pool HDD (`sdd`) to
  `/mnt/fast` (458G SSD, 99% free) or a replacement primary SSD/disk to avoid
  torrent/media HDD IOPS contention.

### P2 — policy and drift control

- Consider digest pinning only for public or privileged containers if Renovate
  tag updates are not enough.
- Removed `stirling.malice.biz` from `vps/sites/chill.caddy` 2026-10-21;
  Stirling `:8091` kept private-only (`stirling.h.malice.biz`).
- Stagger `Unattended-Upgrade::Automatic-Reboot-Time` between `vps-ingress`
  (`vps/bootstrap.sh`) and `chill-01` (`bootstrap.sh`) so both ends of the
  WireGuard tunnel do not reboot simultaneously at `03:00` (and collide with
  `Sun 03:30` `vzdump`).
- Review `debian-01` (VM 103: 4 vCPU, 8G RAM, 16G+64G `local-lvm` disks) role
  and right-size or stop if idle.
