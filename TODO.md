# todo

## next (updated 2026-10-21)

### P0 — access, secrets, and recovery

- DISK SWAP phase 1 (week of 2026-10-26, PLANNED): pull sdc (ata-3,
  ST2000DX002 Z4Z9F91S) + sda (ata-1, WD10TPVT WD-WX71C62N3636); keep sdb
  so the weekly-vault vzdump target stays live. sdc fully superseded
  (verified 2026-10-26: takeover tree newer on every live path; 116
  sdc-only files = jars/logs/cache/old tachibk, ~153M, to salvage to
  /mnt/pool/.diskmove). Remote prep: `cp -a` /mnt/backup/restic+dump to
  /mnt/pool/.diskmove/backup, verify (`restic snapshots` + byte match).
  On-site: shutdown VMs, drop NFS export, unmount sdc binds +
  /mnt/primary + /mnt/backup, bind staging over /mnt/backup, fstab edits,
  `qm set 101 --delete virtiofs0`, poweroff, pull, boot, verify
  mounts/VMs/public-check + one manual `homelab-backup`. sd letters will
  shift — harmless (UUIDs/paths everywhere). Shelf old drives un-wiped.
  Phase 2: new disks -> /mnt/primary + /mnt/backup, copy staging back,
  decide takeover-vs-reverse-restore, re-add NFS export.
- sdc TAKEOVER ACTIVE (2026-10-16, reboot-proofed 2026-10-19): `/mnt/data`
  is a bind of `/mnt/pool/takeover-primary/r1/mnt/data` (sole fstab entry;
  see RUNBOOK incidents 2026-10-14/19). sdc REVIVED-UNTRUSTED (verified
  2026-11-02): mounted `rw` at `/mnt/primary`, NFS-exported rw to
  debian-01, `virtiofs0: pve1-primary` still on VM 101; SMART PASSED with
  zero errors since the Oct 23 `ICRC ABRT`/`critical medium error` burst —
  quiet is not trustworthy. Decide on-site: keep pool layout vs new 2TB
  disk + reverse-restore. (Oct 14/15 partials already pruned via retention.)
- IPv4 RELAY TEMPORARY (2026-10-19): chill-01 default via malice
  (`/etc/netplan/99-homelab-relay.yaml`) + host MASQUERADE, because router
  ARP for .28 is stuck on ghost MAC `6e:44:04:45:5b:3d`. On-site: reboot
  router/clear ARP, verify direct .1 ping, remove relay files. See RUNBOOK.

- Guard `bootstrap.sh` `ensure_virtiofs` against `/mnt/data` takeover bind:
  `ensure_virtiofs pve1-primary /mnt/data` currently checks only for tag
  `pve1-primary` in `/etc/fstab`, so running `make host` will re-append dead
  `pve1-primary /mnt/data` and `mount -a` over the takeover bind. Check target
  mountpoint (`grep -Eq "[[:space:]]$target[[:space:]]" /etc/fstab`) too.
- Clean up revived-untrusted `sdc` on `malice` (mounted `rw` at
  `/mnt/primary` and ro-bound to `/mnt/bulk/media/music`, NFS-exported rw
  to debian-01, `virtiofs0: pve1-primary` still on VM 101; last errors
  Oct 23 `ICRC ABRT` + `critical medium error`, silent since; `/etc/fstab`
  `pass=2` keeps fsck-risk on host reboot despite `nofail`):
  copy what debian-01 needs from the takeover tree + repoint its NFS,
  drop the export, then unmount `/mnt/bulk/media/music` + `/mnt/primary`,
  comment both in `malice:/etc/fstab`, `qm set 101 --delete virtiofs0`,
  and offline kernel device (`echo 1 > /sys/block/sdc/device/delete`).
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
- Staggered `Automatic-Reboot-Time` 2026-10-21: `vps-ingress` `01:30`,
  `chill-01` `04:30` (git; live on next `make vps` / `make host`).
- `debian-01` (VM 103) 2026-10-21: user-managed personal homelab,
  document-and-keep, no action.

## audit 2026-10-25 (read-only; evidence: audit-{repo,chill,malice,vps,external,upgrades}.md)

Repo state at audit: HEAD 5 commits ahead of origin, all undeployed
(`4af8d7c`..`17963ae`); all 37 containers run exact git pins. Deploy order:
fix P0 #4's footgun first, then push + `make deploy` / `make host` / `make vps`
in a quiet window. Watch for restart loops from new `cap_drop: [ALL]` (neko
supervisord, mumble, jellyseerr, gotify, beszel); add back SETUID/SETGID/CHOWN
if needed. (`REPO-4`, `CHILL-4`)

### P0 — fix now

- Public Neko browser reaches Cockpit + every admin port. Any Neko user can
  open `https://10.44.0.2:9090` (200, Cockpit + web terminal) and
  `:5030/:7373/:8191` (200, no auth). Worse: qBittorrent is auth-free to ALL
  `172.16/12`, so Neko users get full qbit control (run-program-on-complete =
  RCE in a container with rw `/mnt/data`) — and so does every tailnet device
  via `qbittorrent.h`. `DOCKER-USER` is empty, so UFW cannot stop it.
  (`CHILL-2`, `REPO-2`, `EXT-6`)
  - Drop qbit `AuthSubnetWhitelist`, give Sonarr/Radarr real creds (stop qbit
    first — it rewrites the conf).
  - Pin `edge_default` subnet in compose; narrow `bootstrap.sh` 9090 rule to
    it (the 172.16/12→9090 rule is load-bearing for cockpit.h — do not just
    delete it).
  - `DOCKER-USER` drop: comms bridge → 10.44/172.17/RFC1918, managed by
    `bootstrap.sh`. Verify by re-running the nsenter curl matrix → timeouts.
- Fallen disk `sdc` REVIVED-UNTRUSTED (Oct 23 power cycle; re-verified
  2026-11-02): mounted **rw** at `/mnt/primary`, NFS-exported rw to
  debian-01, `virtiofs0` still on VM 101. Last errors Oct 23 (`critical
  medium error` + `ICRC ABRT`); silent since, SMART PASSED — quiet is not
  trustworthy, still pull per the disk-swap plan. (`PVE-1`)
  - Copy what debian-01 needs from the takeover tree, repoint its NFS there,
    drop the export. Then the existing fstab/virtiofs0/device-delete cleanup.
    TODO/RUNBOOK wording rewritten 2026-11-02.
- "Retired" `wg0` 10.30 tunnel is FULLY LIVE both ends (fresh handshakes):
  VPS routes `192.168.1.0/24` → malice, malice FORWARD ACCEPT + blanket
  `oifname vmbr0 masquerade`, malice admin ports (`8006/22/2049/111/3128`) on
  `*`. VPS can reach the whole home LAN masqueraded as `.2`. Contradicts
  AGENTS.md. (`PVE-2`, `VPS-5`)
  - `disable --now wg-quick@wg0` on malice; delete nft `nat` table + stale
    iptables rules; on VPS remove peers `.2,.3,.5,.6,.7` + LAN routes.
  - KEEP `.4`/6881 — gluetun P2P egress is live (219 GiB transferred).
- slskd/wrtag/FlareSolverr still OPEN live (`:5030/:7373/:8191` → 200
  unauthenticated from host AND VPS). Fix is in unpushed `65da8a6` but
  undeployed — with a footgun: it enables slskd auth without
  `SLSKD_USERNAME/PASSWORD`, so deploying = well-known `slskd`/`slskd` login.
  (`CHILL-1`, `REPO-1`)
  - Set `SLSKD_USERNAME/PASSWORD` (+`SLSKD_JWT_KEY`) and the wrtag web
    password in live `.env` FIRST, then push + `make deploy`.
  - Verify `:5030/api/v0/application` → 401, `:8191` gone, Prowlarr still
    solves via `localhost:8191`.

### P1 — important

- `make vps` never ran after the Oct 21 commit: `stirling.malice.biz` STILL
  PUBLIC (104 req/24h, 91×401, version + 900 KB OpenAPI doc exposed) and VPS
  reboot still 03:00, not 01:30. TODO P2 claims both done — wrong.
  (`VPS-2`, `EXT-1`) Run `make vps`; verify stirling TLS fails + reboot 01:30.
- VPS sshd on public `:4522`: password + root login allowed, root has a
  password. Only rate-limit + obscurity protect it. Unexplained user `cool`
  with key `elon@cachyos-x8664` (added May, never used — owner to confirm).
  (`VPS-4`, `EXT-2`)
  - `sshd_config.d`: `PasswordAuthentication no`, `PermitRootLogin
    prohibit-password`, `AllowUsers`; codify in `vps/bootstrap.sh`; `passwd -l
    root` after verifying key + provider console. Remove/confirm `cool` key.
- Credentials persisted in VPS `access.log`: Jellyfin `api_key=` 1318/24h,
  Navidrome `p=` 59/24h, `X-Emby-Authorization` token header 191k retained. A
  LIVE-ONLY goaccess job renders them into world-readable HTML (unserved).
  (`VPS-3/11`, `REPO-7`)
  - Caddy `format filter` redaction (uri query `p/t/s/api_key/ApiKey/token`
    + `X-Emby-*`/`X-Password`/`X-Api-Key` headers) in all 3 log blocks +
    `make vps`; retire/gate traffic report (`--no-query-string`); rotate
    Navidrome/Jellyfin creds; delete old `access-*.log.gz` + `traffic.html`.
- Arr auth is decoration: Radarr/Sonarr/Prowlarr `DisabledForLocalAddresses`
  serve `apiKey` to any 10.x/172.x source (VPS, containers); Bazarr auth
  `null`; Bazarr 1.5.6 has 2 CRITICAL auth-bypass CVEs (a 3rd critical waits
  for 1.6.3 stable). (`CHILL-3`, `UPG-6`)
  - `AuthenticationRequired=Enabled` in all three (state-only, record in
    RUNBOOK) + Bazarr forms auth; upgrade Bazarr → 1.6.2 now; then move
    6767/7878/8989/9696/8701 off 10.44.0.2.
- Beszel monitoring DARK since Oct 23: hub→agent `:45876` blocked by UFW
  (6539 BLOCKs; v4 rule likely deleted positionally Oct 19, never in git).
  Host metrics + >85% disk alert dead. NB: TODO's `LISTEN=127.0.0.1` fix
  would ALSO break it (hub connects via 172.17.0.1). (`CHILL-5`, `REPO-25`)
  - Codify in `bootstrap.sh`: `allow from <observability subnet> to 172.17.0.1
    port 45876`; agent `LISTEN=172.17.0.1:45876`; delete stale v6 bridge
    rule; test-alert the disk rule. Never positional `ufw delete N`.
- Unclean crash/power-loss Oct 23 ~20:49 UTC (host + both guests, no shutdown
  sequence), 6 "crash" boot endings since Sep 20, no UPS. Takeover bind + all
  37 containers survived — good proof, but unrecorded. (`PVE-4`, `CHILL-6`)
  - RUNBOOK incident entry; on-site: power strip/PSU + BIOS "power on after
    AC loss"; budget small UPS + `nut-client`.
- Backups half-proven: no scheduled `restic check`; one failed `pg_dump`
  aborts the WHOLE run (`set -e`); Jellyfin/Navidrome/*arr/Jellyseerr/wrtag/
  slskd/Mumble/Suwayomi/Minecraft copied raw while running (only 2 PG + 3
  SQLite dumped); restore drill overdue (last Sep 29); retention forks per
  path-group (48 cloud vs 12 local). (`REPO-8/9`, `CHILL-11/12`)
  - Weekly `restic check --read-data-subset=5%` timer both repos; pg_dump
    alert-and-continue (exit non-zero at end); extend sqlite `.backup` loop +
    Suwayomi stop-copy + MC `save-off/save-all flush`; `forget`
    nightly/`prune` weekly; `restic forget --group-by host` + clean legacy
    groups (KEEP Sep 27 `8513e3b4`/`c8ae4cbd` per RUNBOOK); `make
    restore-test` extended to local repo; exclude live PG data dirs +
    `state/immich/model-cache` from restic.
- `Automatic-Reboot-Time 04:30` (git, undeployed) lands inside the 04:15+30m
  backup window. (`REPO-6`, `CHILL-9`) Move reboot to `02:30` (VPS stays
  01:30) BEFORE `make host`.
- No boot guard: Docker starts without `RequiresMountsFor`; takeover bind is
  `nofail`. The Oct 18 failure mode (apps + skeleton dirs on root disk) can
  recur silently. (`CHILL-8`, `REPO-17`)
  - Git-owned `docker.service.d` drop-in `RequiresMountsFor=/mnt/data /mnt/pool
    /mnt/fast` + `ExecStartPre` takeover-source assert, via `bootstrap.sh`;
    same assert at top of `make deploy`.
- Public check runs DAILY, ON the monitored host, alerting via Gotify ON the
  same host — the Oct 18–19 outage sat 36h. (`REPO-10`)
  - 5–15 min cadence + external probe (VPS timer or free uptime pinger) +
    heartbeat/dead-man on backup + check; add negative test for retired
    names (e.g. `stirling.malice.biz` must not 2xx/401).
- Nothing leaves malice: `/etc/aliases.db` missing, root `.forward` →
  duck.com:25 (blocked), no PVE notification target; vzdump mail queued.
  vzdump/smartd/apt failures alert nobody. (`PVE-6`)
  - `newaliases`; PVE Gotify webhook target + matcher ≥warning; flush stale
    queue once verified.
- Transit loss (RUNBOOK 2026-10-22) STILL reproduces: ~27% SYN retransmits,
  485 KB in 7–40s public vs 0.4s tailnet. (`EXT-5`)
  - Test from 2nd vantage (4G + cloud VM), ticket provider
    (`moula-world-llc`/`nl104.servers.guru`) with evidence; keep tailnet `*.h`
    as documented bypass; consider edge-VPS move if it persists.
- VPS `forward` accepts ANYTHING → 10.44.0.0/24 (any interface, masqueraded
  as .1) + dead wg-easy/`br-*` rules; CrowdSec hooked on `input` ONLY so DNAT
  ports bypass bans; firewall is 337 KB live-only with frozen Sep-18 ban
  snapshot + inline stub + stale `25565→10.30.0.3` shadowed only by hook
  order. (`VPS-6/7/9/10`, `REPO-11`)
  - Git-own it: `vps/firewall.nft` (`inet homelab_filter`, explicit DNAT-only
    forwards, icmp/v6 essentials) installed by bootstrap; bouncer forward
    hook (separate base chain or bouncer ≥0.0.28); delete stub/duplicates/
    dead rules; remove `.bak`s; reboot-test. Never flush.
- chill-01 root → VPS ROOT ssh key unrestricted (`/root/.ssh/vps-backup`);
  stray copy of the chill0 PRIVATE key at `/root/chill0-priv` on the VPS.
  Host compromise = VPS root. (`CHILL-20`, `VPS-4/17`)
  - `restrict,from=,command=` wrapper for the backup key (or pull-only user +
    sudoers `cat`); extend the pull to `/etc/caddy/sites`,
    `/etc/nftables.d`, `/etc/crowdsec` (excluding credential yamls);
    `shred -u /root/chill0-priv`.
- sdd 4TB is now the ONLY copy of all primary data + media. Young and
  healthy — but zero long self-tests ever, no smartd schedule. (`PVE-5`)
  - Long self-test off-hours + smartd schedule
    `(S/../.././02|L/../../7/03)`; decide the layout TODO (new 2TB vs pool)
    with urgency — photos/family share a torrent spindle.

### Upgrades with security content (P1, by exposure)

- Immich server+ML `v3.2.0 → v3.3.5`: high authenticated SVG→ImageMagick RCE
  + unauth ML path-injection. No DB image change (same digest). (`UPG-1`)
- Filebrowser ×3 `1.5.6 → 2.0.2-stable`: MFA-takeover, upload-share bypass
  (hits `upload.`), read-only-overwrite. BREAKING: DB + config migration;
  behind Caddy set `trustProxyHeaders`; old `/share/` links break. Interim:
  `1.5.8` fixes only 2/4. (`UPG-2`)
- Jellyfin `10.11 → 12.3` (pin full version): 6 advisories incl. CRITICAL
  path-traversal, fixed only in 12.0; floating tag stuck since June. No
  rollback, full rescan required, no 3rd-party plugins installed, legacy-auth
  removal may break old TV clients. Back up the 4.3G config first. (`UPG-3`)
- Jellyseerr `2.7.3 → Seerr v3.5.1`: project renamed; high
  path-traversal→RCE on public `requests`. Image
  `ghcr.io/seerr-team/seerr`, needs `init: true` + `chown -R 1000:1000
  state/jellyseerr`. Do with Jellyfin. (`UPG-4`)
- Neko `3.1.5 → 3.2.0`: high cross-user XSS. (`UPG-5`)
- Immich Postgres 14 → 17/18, plan before EOL **2026-11-12**: dump+restore
  window. Verify no `vectors` extension (`\dx`) before picking an image;
  prefer waiting for Immich's official bump if it lands. Not breakage on EOL
  day — plan only. (`UPG-12`)

### P2 — hygiene, drift, hardening

- chill-01: Docker 29.8.2→29.9.2 + containerd 2.4.2 + Tailscale 1.104.2;
  extend unattended-upgrades origins (Docker/Tailscale/`trixie-updates`) or
  document manual cadence; `live-restore: true`; LLMNR off; X11Forwarding
  off. (`UPG-15/17`, `CHILL-10/17`, `REPO-21`)
- Relay cleanup: HOST SIDE DONE 2026-11-02 (malice `arr-routing` emptied,
  all post-up rules deleted live, relay `.28` lines never loaded). Guest
  `99-homelab-relay.yaml` removal still open (`CHILL-7`). (`PVE-3`)
- malice: ALL DONE 2026-11-02 (see RUNBOOK maintenance 2026-11-02) —
  sdc fully retired (NFS dropped, debian-01 automount stopped +
  mountpoint removed, fstab commented, `virtiofs0` deleted from 101,
  device offlined; reappears each boot until physically pulled);
  guest 101 cut to takeover bind (fstab rewritten, generator-verified,
  reboot-tested); nft `ip nat` flushed; stale `.48/.79/.118` + `10.30`
  iptables + tailnet DNAT deleted; `arr-routing` emptied;
  `iptables-restore.service` disabled; nfs/rpcbind(+socket) + HA lrm/crm
  disabled; `PermitRootLogin prohibit-password`; 6.17.2 purged; orphan
  snapshot config removed; failing crons deleted; `hermes` fully
  removed; `firewall=1` dropped; OpenTofu tokens +90d expiry (unused
  90d — delete if idle); `swappiness=10`; sdd self-test + smartd
  schedule; `newaliases`; `malice-restic-backup` git-owned + deployed
  with working `OnFailure` (tailnet Gotify, POST 200);
  `/etc/homelab.env` on malice (0600, `gotify.h` URL); non-final dumps
  + ISO + skeletons removed; takeover music ro-bound over pool/bulk;
  sata→scsi both guests (`virtio-scsi-single`, iothread, boot-tested);
  `full-upgrade` → pve-manager 9.2.25 / kernel 7.0.14-26 / qemu 9.2.14
  + clean reboot (75s, public-check green after warmup); TOTP enrolled
  for root@pam 2026-11-02 (verified `tfa.cfg` live).
  STILL OPEN: physical pull of sdc+sda on-site; PVE Gotify notification
  target (mail path still duck.com:25).
  (`PVE-7/8/9/10/11/12/14/15/16/17/18/19`)
- VPS: feed Caddy access.log to CrowdSec (`acquis.d/caddy.yaml` + caddy
  collection; drop dead nginx/apache/syslog acquis); upgrade CrowdSec
  1.4.6→1.8.x + bouncer ≥0.0.28 via packagecloud; fix whitelist (stale
  `109.0.x.x` home IP); disable idle Docker; `vps/bootstrap.sh` must add the
  Cloudsmith Caddy repo (rebuild otherwise gets Caddy **2.6.2**), validate
  Caddy in staging before replacing live sites, cover CrowdSec; add
  `trixie-updates`+Caddy to unattended origins; decide HTTP/3 (allow udp/443
  or disable `h3` — currently advertises and black-holes); document
  IPv4-only or add icmpv6; `apt autoremove` old kernels; delete `.bak`
  clutter + stale certs. (`VPS-8/12/13/14/15/16/17`, `UPG-18`, `EXT-7`)
- Compose/Caddy: shared internal `edge` network + proxy-by-name, then
  unpublish all admin ports from 10.44.0.2 (incl. **Stirling 8091**, missing
  from the old TODO list); pin floating tags (`jellyfin`, `gotenberg:8.38.1`,
  `beszel:0.21.1` both, `postgres:16.15-alpine`, `redis:7.4.11-alpine`);
  Gotify `2.5.0→3.1.1` (breaking v3), Paperless `3.1.3→3.3.4`, edge Caddy
  `2.11.4→2.11.7` (compose AND Makefile), routine P3 batch (*arr, qbit,
  gluetun 3.41.3, flaresolverr 3.5.2 — one advisory UNFIXABLE upstream, slskd,
  wrtag, suwayomi, tika, mumble, MC image; Stirling 3.x after reading notes);
  narrow rw `/mnt/data` to needed subtrees; fix jellyfin UFW comment (wrong —
  published ports bypass UFW); gluetun dependents → `service_healthy`.
  (`REPO-3/8/15/16/23`, `UPG-7/8/9/10/11/13/14`)
- Renovate: NEVER RAN (repo is on Codeberg, zero PRs/issues ever;
  `config:recommended` alone won't track floating tags or Makefile refs).
  Either run self-hosted Renovate (`RENOVATE_PLATFORM=gitea`) with
  dashboard+grouping+customManagers, or delete the file and stop assuming
  updates. (`UPG-19`, `REPO-15`)
- SSH aliases / Makefile: `HOST ?= chill-01` points at a DENIED alias;
  working path is `chill-deploy` (LAN via malice). Set `HOST ?=
  chill-deploy` or fix the alias; fix README/AGENTS/TODO "over Tailscale"
  wording; make `deploy vps host` depend on `check`; strengthen `check`
  (host_ip allowlist via compose JSON, pin `caddy:2.11.7`, `nft -c`).
  (`REPO-13/14`)
- Docs to rewrite: AGENTS (add `games` stack; access matrix — LAN works,
  Tailscale @100.92.173.71 denied from workstation; storage takeover row;
  backup excludes; VPS alias); RUNBOOK (Oct 23 incident; excludes;
  `flush_interval -1` is INVERTED — it disables buffering, use
  `response_buffers`; snapshot map; `/tmp/*.bak` refs gone with tmpfs);
  edge/comms compose comments; `vps/README` (51820/6881, 8088). Record
  `malice-restic-backup`. (`REPO-18`, `PVE-11/13/20`, `CHILL-19`, `VPS-13`)
- Tailnet: identify/remove `fedora`, reconnect/remove `pixel-8` (35d),
  disable key expiry for chill-01/malice (die Mar 2027). (`EXT-12`, `CHILL-16`)
- DECIDE: P2P egress rides the VPS PUBLIC IP (gluetun .4) — a DMCA/abuse
  complaint can suspend the account hosting the entire edge. Accept, move P2P
  egress, or separate VPS. (new)
- Small: MC whitelist in git (`ENABLE_WHITELIST`, default MOTD invites
  griefers) + `RCON_HOST` is a no-op (accept unpublished-only or
  `ENABLE_RCON: false`); HSTS+baseline headers snippet; null MX + CAA +
  DNSSEC; remove dead `transfers.global` from `slskd.yml` (0.26 ignores it —
  tune via API), rotate Prowlarr key (leaks into Sonarr logs); clear stale
  `dockge.db` + old jellyfin-cache dir; Sonarr/Prowlarr indexer noise (eztvx
  451, category 400s). (`EXT-4/8/9/11`, `REPO-5`, `CHILL-13/14/15/18`)

### Reconciliation — old "next" items above that are now stale

- `ensure_virtiofs` guard: DONE in git (`bootstrap.sh:42-50`) — remove item.
- wrtag/8191/qbit `mem_limit`: COMMITTED, not deployed — reword to "deploy".
- Reboot stagger + stirling removal: COMMITTED, not deployed — reword.
- Prune Oct 14/15/18/19 snapshots: already gone via retention — remove.
- IPv4 relay: inert, cleanup only (see P2 above) — rewrite.
- sdc emergency_ro / 0xE5-every-30m / "confirmed DEAD": REWRITTEN 2026-11-02
  (revived-untrusted, rw, NFS+virtiofs live, errors last Oct 23).
- macbook/hermes-01 tailnet lines: not in tailnet; `towa` is the workstation
  — replace with fedora/pixel-8/key-expiry actions.
- slskd self-check / cockpit-blocked-from-VPS / VAAPI flip / Jellyfin cache
  path: VERIFIED done — remove.
- Renovate assumption ("if Renovate tag updates are not enough"): never ran
  — see P2 Renovate item.
- `6881→.4` "stale": LIVE, do not delete — correct the VPS nftables item.
- Beszel `LISTEN=127.0.0.1`: would break the hub — use `172.17.0.1`.
- UFW allowlist approach: cannot filter Docker-published ports — needs
  `DOCKER-USER`/loopback binds; add 8091 to the port list.
- swappiness rationale: misreads virtiofsd RSS (shared guest RAM) — fix text.
