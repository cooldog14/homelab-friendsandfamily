# runbook

Break one thing at a time.
Use a quiet window.
Do not test by deleting data.

## service expectations

- Availability: best effort, not HA. There is one hypervisor, one app VM, and
  one VPS edge.
- RPO: latest successful nightly `homelab-backup` snapshot for `/opt`,
  `/mnt/data`, `/etc`, `/root/.ssh`, and fresh DB dumps. Downloads, movies, TV,
  and raw music staging are excluded by design.
- RTO: manual restore after host, VM, or disk loss. Record the real time after
  each `make restore-test` drill; do not invent an SLA before a measured drill.

## deploy rollback

- Detect: service regression after `make deploy`, `make host`, or `make vps`.
- Repair: redeploy the previous good commit first:
  `git checkout <good-commit>` then run only the affected deploy target.
- Repair: restore app state only for a confirmed data-changing migration; do
  not roll back databases just because a container image is bad.
- Record: bad commit, good commit, affected stack, and whether state restore was
  needed.

## public service down

- Drill: stop one harmless public service.
- Detect: `homelab-public-check` fails; Gotify alerts; systemd logs show failure.
- Repair: restart the stack with Docker Compose. If MANY vhosts fail at
  once, check shared layers first: `mount | grep /mnt/data` (takeover
  bind present?), `wg show` handshake fresh on both ends, `docker ps`
  for mass exits — don't restart stacks one by one (proven 2026-10-19).
- Record: detection time and repair time.

## private caddy bad config

- Drill: test a bad edge Caddy config.
- Detect: Caddy validation fails before restart.
- Repair: restore the valid config.
- Record: whether validation blocked the outage.

## backup stale

- Drill: simulate an old backup marker.
- Detect: `homelab-backup-watchdog` alerts Gotify.
- Repair: run backup; restore the marker only after a real success.
- Record: alert path and delay.

## WireGuard link

- Drill: only with console access, stop the tunnel briefly.
- Detect: public HTTP fails; `ssh vps-ingress 'sudo wg show chill0'` shows the issue.
- Repair: `sudo systemctl restart wg-quick@chill0` on the broken side.
  If handshake stays stale, verify UNDERLAY first: guest must reach
  the VPS endpoint IP directly (`ping 194.58.47.21`) — a dead gateway
  route or stale router ARP kills the tunnel with zero WG errors
  (proven 2026-10-19: host relay restored it).
- Record: user impact and recovery command.

## VPS Caddy bad config

- Drill: test a bad site file.
- Detect: Caddy validation blocks reload.
- Repair: fix the git-owned site file and run `make vps`.
- Record: what validation caught.

## lesson 2026-09-16: private Caddy needs restart, not reload

- Impact: `make edge-reload` with `caddy reload` silently kept the old config;
  edits looked like "my edit did nothing" with no error.
- Detect: `caddy validate` passes but serving behavior is unchanged after reload.
- Repair: `Makefile` `edge-reload` validates then
  `docker compose -p edge restart caddy` (bind-mounted Caddyfile is only
  re-read on restart). Validate first for a loud failure instead.
- Prevent: never use `caddy reload` for the private edge; restart is the only
  proven path.

## lesson 2026-09-16: edge uses exact host matchers, not map

- Impact: `map` silently dropped its `default` line; unset `{svcport}` made
  `!= ""` true, so unknown hostnames proxied to `:0` (502) instead of 404.
- Detect: unknown `*.h.malice.biz` name returns 502 to `:0` rather than the
  `unknown private service` 404.
- Repair: two names = two `@host` matchers + `handle` blocks; keep the 404
  `handle` last. Verified 2026-09-16.
- Prevent: never reintroduce `map` for routing; extend with exact matchers only.

## lesson 2026-09-17: gluetun outbound subnets must cover all docker bridges

- Impact: narrow `FIREWALL_OUTBOUND_SUBNETS` silently dropped arr-app to
  qbittorrent/prowlarr traffic after compose re-creation.
- Detect: P2P apps unreachable from arr apps only after re-creation; media got
  `172.21.0.0/16` here, arr had `172.18` — Docker assigns bridge subnets
  dynamically.
- Repair: `FIREWALL_OUTBOUND_SUBNETS: "172.16.0.0/12"` covers every compose
  bridge. Local docker networks bypass the VPN through gluetun by design.
- Prevent: never narrow this to a single `/16`; re-creation moves subnets.

## maintenance 2026-09-19: jellyfin LAN-only bind for direct TV playback

- Change: `stacks/media/docker-compose.yml` adds `${LAN_IP:-192.168.1.28}:8096:8096`
  alongside `${WG_IP:-10.44.0.2}:8096:8096`. Specific-IP binds only, never
  `0.0.0.0`. WG/tunnel and public vhost paths unchanged.
- Change: `bootstrap.sh` adds `ufw allow in on eth0 from 192.168.1.0/24 to any
  port 8096`. Scoped to the home subnet; nothing internet-facing changes.
- Verify: TV plays direct over LAN with no VPS hairpin; `make check` wide-bind
  lint stays green.
- Prevent: never bind `8096` to `0.0.0.0`; keep the UFW scope tight to LAN.

## incident 2026-09-20: jellyfin disk full, then green glitch

- Impact: playback stalled from root-disk ENOSPC; later PGS subtitle burn-in
  showed green frames. No data loss.
- Detect: `docker logs` shows ffmpeg `No space left on device` / ENOSPC;
  `df -h` shows root full; `du -sh` finds HLS cache and Docker image use.
- Repair: free safe space only: builder prune + orphan-image removal. Never
  remove running images or the active HLS session.
- Prevent: check disk before blaming the database; isolate filter/client bugs
  with client-side subtitle toggles. VAAPI overlay avoids the UHD 630 QSV
  subtitle burn-in corruption.

## lesson 2026-09-21: host-side deletes on virtiofs shares don't free space

- Detect: compare `df -h` vs `du -sh`; free inodes with held blocks means
  unlinked open files or guest caches. List holders with
  `lsof -n | grep '(deleted)' | grep -v memfd`.
- Repair: from malice, release clean guest caches:
  `qm guest exec <VMID> -- bash -c "sync; echo 2 > /proc/sys/vm/drop_caches"`
- Repair: re-check `df` twice, 10-30s apart. If space stays held, find guest
  holders with `lsof`/`fuser` and stop that workload. Last resort: full VM
  stop/start.
- Prevent: delete shared-tree data from the guest side when possible, and stop
  consumers before host-side `rm`.

## storage migration guardrails

- Check: current disk roles live in `AGENTS.md`; do not duplicate them here.
- Plan: keep store IDs, virtiofs tags, and guest mountpoints stable unless a
  deploy changes them.
- Repair: path changes need a full stop/start for guests using the share.
- Prevent: delete old mountpoint skeletons after unmounting to avoid silent
  root-disk writes.
- Verify: before deleting stale mirrors, compare sorted file lists:
  `find . -type f | sort` and `comm -23`; spot-check overlaps with md5.
- Verify: move keeps with `cp -a`, verify with md5 + `diff -r`, then delete
  sources.
- Repair: for guest disks, use `pct destroy` or
  `pct set <id> -delete unused<N>`; never `rm` a live rootfs.
- Repair: expect `df` to lag `du` after shared-tree deletes; use the virtiofs
  cache release above.
- Repair: wire dump storage with `pvesm set <store> --content ...`; Proxmox
  manages `<path>/dump/`.
- Verify: proof-run a stopped small guest, then create the schedule with
  `pvesh create /cluster/backup`.
- Prevent: qBittorrent can keep `.fastresume` paths and sizes from retired
  storage. Quarantine stale `.torrent`/`.fastresume` first; do not delete media
  to satisfy torrent state.
- Prevent: prove Jellyfin cache location with real playback after deploy before
  deleting old cache directories. Only remove empty old paths with no active
  references.

## lesson 2026-09-28: local restic and cloud-first backup cutover

- Failure: `homelab-backup` skipped offsite backup when `/mnt/backup` was in
  `RequiresMountsFor` before the guest had that mount.
- Detect: failed timer with no useful script output, or stale `last-ok` marker.
- Repair: cloud backup runs first; local `/mnt/backup` is checked after offsite
  completes.
- Repair: once `pve1-backup -> /mnt/backup` is mounted, restore the mount
  requirement, initialize `/mnt/backup/restic`, and run the local backup.
- Verify: use `make restore-test` for proof; stale `last-ok` means no proven
  success.
- Troubleshoot: manual restic churn from a missing latest parent: stop it,
  clear the stale lock, rerun with the known parent snapshot.
- Troubleshoot: S3 503s/hangs with a fresh verified cloud snapshot: stop
  poking and let the timer retry.
- Prevent: full VM stop/start for virtiofs can regenerate cloud-init SSH host
  keys; verify the new fingerprint through `qm guest exec` before trusting SSH.

## lesson 2026-09-28: app credentials are not all env vars

- Detect: app auth may live in the app DB/key, not `.env`; changing `.env` does
  not always change live credentials.
- Repair: if a secret contains `$`, prefer app-supported `*_PASSWORD_FILE` with
  a host-only `0600` file.
- Repair: Filebrowser resets via `filebrowser set` (upserts in place); only
  `admin` exists in all three DBs.
- Troubleshoot: this Filebrowser fork takes username as query param plus
  URL-encoded password in `X-Password` header; JSON body always 401s.

## lesson 2026-09-28: public app rollout checks

- Detect: native auth must work off-tailnet before a private app becomes public.
- Check: from a non-tailnet browser/session, verify login, logout, expected
  anonymous behavior, upload/write paths if exposed, and no admin UI bypass.
- Repair: add only the exact public Caddy host, run `make check`, run
  `make vps`, and verify `homelab-public-check`.

## maintenance 2026-09-28: ship minecraft Paper 26.2 on games stack

- Change: new `stacks/games` stack (Paper 26.2 on java25 image — java21
  boot-looped since 26.1+ needs Java 25). World + config on
  `/mnt/data/apps/minecraft` (mirror disk, restic-backed, no DB dumps).
  Added to `Makefile` `STACKS` + deploy data dirs.
- Change: raw TCP `25565`, never HTTP — Caddy never sees it. Container binds
  `${WG_IP}` only; VPS DNATs `eth0:25565/tcp` to `10.44.0.2:25565` in
  `vps/nftables.conf` (same pattern as Mumble `64738`). Clients use
  `mc.malice.biz:25565`.
- Change: `Makefile` `HOST` defaults to `chill-01` (Tailscale admin path, never
  the WG tunnel); fixed `./.env.example` sourcing in `check` (dash searches
  `PATH` without `./`). RCON password lives in `/opt/stacks/games/.env`
  (never git); admin via `docker exec -i games-mc-1 rcon-cli`.
- Verify: `make check` green, `make deploy` ships games, TCP `25565`
  open end-to-end. Owed: Chunky pre-gen (`chunky radius 2500` + `chunky start`)
  the night before launch day — pins CPU, not while backups run.
- Prevent: never bind `25565` to `0.0.0.0`; keep world on restic-backed storage.

## drill 2026-09-29: restore-test ok

- Proof: snapshot 6cd039f7 (2026-09-29 04:16 UTC) restored to a temp path;
  immich/paperless dumps, kavita/gotify/beszel DBs (integrity ok),
  homelab.env, wg0.conf, VPS Caddy/nftables, and /mnt/data/photos all present.
- Repeat quarterly.

## maintenance 2026-09-29: LAN password SSH stays open, key-only elsewhere

- Change: `bootstrap.sh` writes `/etc/ssh/sshd_config.d/homelab.conf` with
  `PasswordAuthentication no` + `PermitRootLogin no`, plus
  `Match Address 192.168.1.0/24` -> `PasswordAuthentication yes`.
- Change: UFW keeps `allow in on eth0 from 192.168.1.0/24 to any port 22`;
  no global `allow 22/tcp`. Tailscale stays the people/admin path.
- Verify: `systemctl reload ssh`; `sshd -T | grep -i passwordauth` shows
  no outside the match, yes inside; LAN login works without a key, outside
  LAN still key-only.
- Prevent: never re-add global `allow 22/tcp` or `0.0.0.0:22`. The LAN
  exception is the only documented exception, here and in `bootstrap.sh`.

## maintenance 2026-09-30: navidrome WG-only bind, caddy check images pinned

- Repair: drop `127.0.0.1:4533:4533` from `stacks/media/docker-compose.yml`;
  Navidrome stays `10.44.0.2:4533:4533` (WG-only, served public via
  `nvdr.malice.biz` in `vps/sites/media.caddy`). Reverts the live-imported
  localhost bind from the day before.
- Repair: drop spurious `FIREWALL_VPN_INPUT_PORTS` from
  `stacks/media/.env.example`; the gluetun value stays hardcoded in compose
  (`6881,50300`), not env-driven.
- Repair: `Makefile` `check` inlines `caddy:2` and
  `ghcr.io/caddybuilds/caddy-cloudflare:2.11.4-alpine`; removes
  `CADDY_IMAGE` / `CADDY_CF_IMAGE` overrides so lint always validates
  against the shipped images.
- Verify: `make check` green, `make deploy` recreates navidrome only,
  `homelab-public-check` green for `nvdr.malice.biz`.

## maintenance 2026-09-30: destroy stale guests, big-only mem limits, virtiofs rename

- Destroy: `qm destroy 102` + `pct destroy 200` after final
  `vzdump 102 200 --storage data` (`vzdump-qemu-102-2026_09_30*`,
  `vzdump-lxc-200-2026_09_30*`, 588M + 738M). `qm list/pct list` clean,
  `/mnt/fast` 8.9G -> 5.7G (sparse, so small actual reclaim).
- Mem limits (big hogs only, per live `docker stats` 12Gi used / 234Mi free):
  `mc 5g`, `jellyfin 3g`, `suwayomi 1536m`, `stirling 2g`, `paperless 1536m`,
  `immich-server 2g`, `immich-ml 3g`, `neko 3g` + `cpus 2.0` on mc/jellyfin/
  stirling/ml/neko. Tiny services (mumble, redis, filebrowser, etc.) left
  unconstrained by choice. `make check` ok (except missing shellcheck bin),
  `make deploy` recreated 8, `docker inspect` confirms, `public-check` green
  after warmup (paperless/stirling 502 + mc TCP fail for ~2min post-reboot).
- Rename: `pve1-mirror -> pve1-primary` (/mnt/primary), `pve1-archive ->
  pve1-vault` (/mnt/vault). Kept `pve1-pool/fast/backup` (already accurate).
  Added new mappings alongside old, updated guest `/etc/fstab` + `qm set 101
  --virtiofs0/2` (went to [PENDING]), `qm stop/start 101` to apply, verified
  `mount | grep virtiofs` shows new tags on all 5, `make host + deploy` green,
  removed old mappings. Backups in `/tmp/*.bak-20260930` on malice + guest
  `/tmp/fstab.bak-20260930`.
- Verify next: Beszel OOM kills over 7d, `homelab-backup` tonight still green
  with new tags, quarterly `restore-test`.
- Destroy 2026-09-30: LXC 204 `hermes-01` (2vCPU/2G/20G `fast` + unused
  `local-lvm` vol). Persona/config/scripts copied to
  `/mnt/primary/users/francis/hermes/hermes-state` (88M, secrets excluded:
  no `.env`, `auth.json`, DBs, `sessions/`, `pairing/`, `.ssh/`), container
  was `nousresearch/hermes-agent:latest` (`hermes gateway run`). Final
  `vzdump-lxc-204-2026_09_30*` 2.4G ok (73s stop), then `pct stop + destroy
  --purge`. `/mnt/fast` 5.7G -> 119M. No LXCs remain. TODO: remove stale
  `hermes-01` tailnet device + auth key per tailnet hygiene.

## lesson 2026-09-30: player login blocked by double CORS origin on fiesta

- Impact: player showed a network error for every account while nvdr logins
  worked. Auth succeeded server-side; the browser rejected the response.
- Detect: console shows CORS header Access-Control-Allow-Origin does not match
  https://player.malice.biz, * on fiesta getUser.view. Octo-Fiesta sends * on
  200 responses and nothing on 401s; VPS Caddy added the locked origin on top.
- Repair: strip the backend header in the fiesta Caddy block with header_down
  on Access-Control-Allow-Origin, keep only the player origin, then run make
  check and make vps. Verify with an authenticated ping and getUser through
  the public hostname with an Origin header: HTTP 200 and exactly one ACAO.
- Prevent: unauthenticated curl probes only hit the 401 path and curl never
  enforces CORS, so they cannot catch this. Verify CORS changes with an
  authenticated request plus Origin header.
- Note: fiesta is API-only with no login page; web login lives on player.
  Legacy auth sends the password as a p query param that VPS access.log
  records, so rotate a Navidrome password after pasting such a URL anywhere.

## lesson 2026-10-13: jellyfin stalls were client-side policer loss, not the homelab

- Impact: remote playback on a ~30 Mbit/s capped link stalled; Jellyfin
  Auto started at ~140 Mbit/s, saturated the policer, and loss collapsed
  cubic (cwnd 2-3, 10% retrans, <1 Mbit/s goodput). Transcode itself was
  fine (VAAPI 16x); VPS<->chill tunnel clean (16.7ms, 0% loss).
- Detect: `ss -ti` server-side shows retrans/cwnd/delivery_rate per
  connection; Caddy access.log HLS segment durations p90 >> p50 with
  VideoBitrate=139M... collapsing to 2.8M -> 0.6M in minutes.
- Repair: client locks quality to <=4 Mbit/s instead of Auto. VPS runs
  BBR+fq (`vps/bootstrap.sh` sysctl) so policer loss no longer collapses
  the window. P2P upload caps considered but not applied: slskd 0.26
  ignores the legacy `transfers.global` schema (API shows only
  upload/download/groups, `speedLimit: 2147483647`), and qBittorrent
  limits are state-only config, set GlobalUpLimit in the WebUI.
- Prevent: suspect last-mile policer when idle ping is clean but
  under-load ping shows loss and only one client IP is slow in the logs.

## incident 2026-10-14: requests failed; stale arr paths + qbit subnet drift

- Impact: Jellyseerr request "The Celebrity Traitors (2025)" (req 77) was
  auto-approved but failed to reach Sonarr. No downloads flowed; no data loss.
- Cause 1: library moved to the 4TB pool disk (6202ca2, 2026-09-17) but
  Jellyseerr still sent `rootFolderPath /data/media/tv`, which no longer
  exists. Sonarr rejected the add with HTTP 400
  (RootFolderPath: Root folder does not exist). All 20 existing series and
  36 movies still pointed at dead `/data/media/...` paths, so Sonarr/Radarr
  reported the whole library missing over new root content.
- Cause 2: qBittorrent `WebUI\AuthSubnetWhitelist` was pinned to
  `172.18.0.0/16` but compose recreated the bridge on `172.21.0.0/16`, so
  Sonarr/Radarr auth failed, qbit banned their IPs, and the queue sat in
  `downloadClientUnavailable` even after grabs succeeded.
- Detect: Jellyseerr log `[Sonarr API] ... status code 400`; Sonarr health
  "Missing root folder"; queue items `downloadClientUnavailable`; Sonarr log
  `Your IP address has been banned after too many failed authentication
  attempts`; compare `docker network inspect media_default` subnet vs qbit
  whitelist.
- Repair: Jellyseerr settings API PUT `/settings/sonarr|radarr/<id>` with
  `activeDirectory /pool/tv|/pool/movies` (strip read-only `id` from the
  body); qbit conf `AuthSubnetWhitelist=172.16.0.0/12` (stop qbit first, it
  rewrites the file), restart to clear the in-memory IP ban; add the series
  via Sonarr API with `rootFolderPath /pool/tv` profileId 4 (HD-1080p);
  `POST /api/v1/request/77/retry`; bulk-move stale entries with
  `/series|movie/editor` + `moveFiles: false`, then RescanSeries/RescanMovie.
- Prevent: app root-folder paths are state-only (not in git compose); after
  any library/mount move, update Jellyseerr activeDirectory + Sonarr/Radarr
  root folders + existing item paths before approving requests. Pin nothing
  to a compose bridge /16: use `172.16.0.0/12` for container trust.
- Follow-ups: fix remaining Jellyseerr request rows with stale rootFolder
  values; confirm Deadwood/Great North/Sealab + 8 Radarr titles truly absent
  vs renamed on pool; consider scheduled rescan to reconcile file drift.

## incident 2026-10-14: sdc failing, /mnt/primary emergency_ro, mg + mc down

- Impact: `mg.malice.biz` 502s (Suwayomi down), Minecraft TCP 25565 dead,
  all `/mnt/data`-backed apps read-only. Photos dir empty on mirror (no
  loss). No other public vhost affected.
- Cause: sdc ST2000DX002 2TB (`/dev/sdc1` -> `/mnt/primary` -> guest
  `/mnt/data`) READ I/O errors since Oct 14 02:03 UTC; journal aborted,
  ext4 remounted `emergency_ro`. Drive later stops answering SMART
  IDENTIFY. 777 cumulative sdc errors by Oct 16; unreadable files span
  minecraft (183/214), suwayomi DB, logs, and music covers.
- Detect: `homelab-public-check` FAIL 502 mg + FAIL tcp 25565; container
  logs show `Read-only file system`; host `dmesg` shows `I/O error, dev
  sdc` + `Remounting filesystem read-only`; `mount | grep primary` shows
  `emergency_ro`.
- Triage (remote-safe, proven 2026-10-16): `restic check` clean on both
  repos; local `af186f72` + cloud `4ee5c22f` (Oct 13 04:46, pre-failure)
  contain suwayomi `database.mv.db`, full minecraft tree, music `clean`.
  Spot-restores to `/mnt/fast/rescue-oct13` verified (DB 6.7M,
  minecraft 236M, 30M FLAC). SQLite dumps integrity ok (kavita/gotify/
  beszel, Oct 15); pg dumps fresh (Oct 15) since DBs live on VM root.
  Exposure window Oct 13 04:46 -> Oct 14 02:03 holds only logs/caches/
  world clock .dat files (31 of 38 delta files unreadable, all low
  value); no new user uploads or photos in the window.
- Remote rules until on-site (SUPERSEDED 2026-10-19 by reboot + full
  restore; kept for history): NO reboot, NO fsck/remount-rw, NO hardware
  reseat (risks total loss without console). Rescues via `ionice -c3`
  reads only. Suspend `homelab-backup.timer` if alert noise matters; do
  NOT prune: post-failure cloud snaps (Oct 14/15) are partial but
  harmless alongside intact Oct 13.
- Repair (needs on-site, SUPERSEDED: takeover done remotely Oct 16, made
  reboot-safe Oct 19): new 2TB+ disk, swap, restore `/mnt/primary`
  from Oct 13 restic + Oct 15 DB dumps, fsck-verify, restart
  suwayomi/mc + `homelab-public-check` green, re-enable backup timer.
  Alternative if a cable/port swap revives sdc: full `ddrescue` image
  before any fsck. Keep failed sdc untouched until restore is verified.
- Takeover (remote, executed 2026-10-16, all services green; made
  REBOOT-SAFE 2026-10-19, see next incident): restored Oct 13 local
  `af186f72` `/mnt/data` (302.6 GiB) to
  `/mnt/pool/takeover-primary/r1/mnt/data` on the healthy 4TB pool disk
  (1.4T used / 2.2T free after), then `mount --rbind` over `/mnt/data`.
  Original fstab had TWO `/mnt/data` lines (virtiofs + bind) — the bind
  was live-only and silently dropped on the Oct 18 reboot. 2026-10-19
  fix: deleted the `pve1-primary` line so the bind is the ONLY entry;
  reboot-tested. Fstab backups at `/tmp/fstab.bak-takeover-20261016`
  (original) + `/tmp/fstab.bak-20261019-rebind` (pre-fix).
  Phase 1 first: suwayomi+minecraft sub-binds brought `mg` 200 + MC
  healthy in minutes; then full-tree bind + `docker restart` of all 37
  containers (compose `up -d` alone does NOT pick up the new bind:
  containers hold old-mount fds until recreated/restarted).
  `homelab-public-check` fully green (14 vhosts + 4 TCP). Backup
  re-run against the new tree (dumps ok, no I/O errors); `restic check`
  clean both repos before cutover.
- Loss surface REVISED (2026-10-16): restic-excluded `media/downloads`
  (63G) + `music/messy` (65G) were presumed lost (19k rsync I/O errors,
  ~2M rescued from disk) — but pre-exclusion cloud snapshot `8513e3b4`
  (Sep 27 04:30, hours before exclusion commit d73747b) still held all
  9,515 live files. Restored 186 GiB to the takeover tree; verified 0
  missing, 1 zero-byte stub (empty upstream MP3 placeholder). NOTHING
  LOST: `clean` 236G, `users` 86G, all app dirs (Oct 13) + messy/
  downloads (Sep 27) all byte-verified on pool. `downloads/` (empty
  live) and `paperless/consume/` (empty live) recreated as skeleton
  dirs owned 1000:1000.
- Policy fix (same day, VERIFIED 2026-10-19): `messy` +
  `media/downloads` re-included in `host/backup.sh` (static archives,
  dedup makes them near-free). Deployed to chill-01. Oct 17 snapshot
  `c8ae4cbd` confirmed to contain `messy/` paths — the Sep 27
  `8513e3b4` source is no longer the sole copy. Safe to prune per
  normal retention once a post-Oct-19 full snapshot lands.
- On-site follow-up (SUPERSEDED 2026-11-02, kept for history — sdc revived
  rw; see status note below): sdc confirmed DEAD 2026-10-19 (INQUIRY
  failed, 875+ cumulative errors, still erroring; keep untouched in slot).
  Options: (a) leave takeover as the layout and re-point backups/docs
  to pool (pool has headroom: 2.0T free), retiring the primary slot;
  (b) new 2TB disk, reverse-restore pool->primary, remove fstab bind
  line. `ddrescue` of sdc now pointless (all data recovered from
  restic + verified on pool). Post-Oct-19 snapshots supersede Oct 13
  for user data; keep `8513e3b4` until messy/downloads confirmed in a
  fresh full snapshot.
- Snapshot map (cloud, verified 2026-10-19): `4ee5c22f` Oct 13 =
  last full pre-failure; `a385fafc`/`411178ac` Oct 14/15 = partial
  (dead-disk reads); `c8ae4cbd` Oct 17 = full takeover tree + messy
  re-included; `57fe39d9`/`3d7c79e3` Oct 18/19 = `/mnt/data` EMPTY
  (bind dropped, dead sdc unreadable) — prune candidates once fresh
  full snapshots land.
- Status 2026-11-02 (revived-untrusted): Oct 23 power cycle brought sdc
  back `rw` at `/mnt/primary`, NFS-exported rw to debian-01,
  `virtiofs0: pve1-primary` still on VM 101. Last errors Oct 23 (`ICRC
  ABRT` + `critical medium error`, 53 journal hits); silent on all 6
  newer boots, SMART PASSED (0 realloc/pending/uncorrect). Quiet is not
  trustworthy: repoint debian-01 NFS to the takeover tree first, then
  pull per the TODO disk-swap plan.

## incident 2026-10-19: auto-reboot dropped takeover bind; router ARP blackhole killed IPv4

- Impact: 5 vhosts 502 (photos, paperless, stirling, upload, mg), fiesta
  500, MC TCP dead for ~36h (Oct 18 03:00 -> Oct 19 ~15:00 UTC). Then a
  second total outage (all 14 vhosts 502) for ~10 min during repair when
  the WG tunnel dropped (IPv4 egress dead). `homelab-backup` failing
  (exit 3, `/mnt/data` I/O error). gluetun unhealthy (no upstream).
  No data loss.
- Cause 1 (storage): unattended kernel 6.12.113 + `Automatic-Reboot
  03:00` rebooted chill-01 Oct 18 03:00. Guest fstab had TWO `/mnt/data`
  lines (virtiofs + bind); systemd-fstab-generator honors only the
  first, so the Oct 16 takeover bind was silently dropped and
  `/mnt/data` fell back to dead sdc (emergency_ro, I/O errors).
  Detect: `mount | grep /mnt/data` shows `pve1-primary`, no bind;
  `systemctl status mnt-data.mount` shows `What: pve1-primary`;
  dockerd boot log `mkdir /mnt/data/...: input/output error`;
  `docker inspect` State.Error on 5 exited containers; 3 crashloop
  (suwayomi/mc/slskd) with I/O or missing-path errors.
- Cause 2 (network, latent): router ARP for 192.168.1.28 stuck on
  ghost MAC `6e:44:04:45:5b:3d` (no such device on vmbr0, taps, or
  veths). Router sends ALL .28-bound IPv4 to the ghost; bridge floods
  the unknown-unicast to every tap (visible on tap101i0 AND tap103i0),
  but the guest NIC drops wrong-MAC frames before the stack (stack
  ICMP counters frozen, iptables LOG/TRACE silent, RX drops static).
  IPv6 unaffected (separate NDP), LAN host<->guest fine, sibling VM
  103 fine. Survives guest reboot (router-side state). Gratuitous ARP
  (request + reply/opcode-2 forms, unicast + broadcast) did not fix it.
  Detect: guest ping to .1/.2-of-router fails but LAN peers reply;
  `tcpdump -e` on guest eth0 shows replies with dst MAC != guest MAC;
  same replies visible on OTHER VMs' taps (flood signature).
- Repair (storage): re-applied `mount --rbind` of pool takeover
  source; deleted the `pve1-primary /mnt/data` fstab line so the bind
  is the ONLY `/mnt/data` entry (verified generator output +
  reboot-tested Oct 19 15:27: bind held). Recreated 5 dead + restarted
  10 stale-fd containers (jellyfin/qbit/sonarr/radarr/navidrome/
  fiesta/kavita/wrtag/bazarr/family held dead-mount fds); stopped MC
  crashloop, restarted after egress fixed. Fstab backup at
  `/tmp/fstab.bak-20261019-rebind`.
- Repair (network): temporary host relay — guest default via
  192.168.1.2 (`/etc/netplan/99-homelab-relay.yaml`, metric 50,
  overrides cloud-init .1 default) + malice MASQUERADE/FORWARD for
  .28 non-LAN traffic (`/etc/network/interfaces.d/arr-routing`
  post-up lines). Both files commented with removal steps; pre-change
  copies in `/tmp/*.bak-20261019*`. WG tunnel re-handshook within a
  minute of the VPS route moving to the relay. L2-local and IPv6 paths
  untouched; same-subnet extra hop is negligible.
- Verify: `homelab-public-check` fully green (14 vhosts + 4 TCP,
  in-guest run exit 0); all 37 containers Up/healthy; MC Paper 26.2
  serving (healthy); gluetun healthy; cockpit.h 200.
- Lesson: the 172.16/12:9090 UFW rule is LOAD-BEARING — edge Caddy
  proxies cockpit.h via host.docker.internal (172.17.0.1), so deleting
  it 502s cockpit. `bootstrap.sh` comment updated to say so. Do not
  "tighten" it away (TODO P1 UFW item must preserve this path).
- On-site follow-up: reboot the router (or clear its ARP for .28),
  then from chill-01 verify direct `ping 192.168.1.1` with the relay
  removed (`ip route replace default via 192.168.1.1`), delete
  `/etc/netplan/99-homelab-relay.yaml` + the relay post-up lines,
  `netplan apply`. Also still: replace dead sdc, decide
  pool-vs-new-disk layout (see previous incident).
- Prevent: any fstab bind takeover MUST be reboot-tested before calling
  it done; generator output (`/run/systemd/generator/*.mount`) is the
  proof, not the fstab text. Consider a boot-time assert (mountpoint
  source check) that fails loudly if `/mnt/data` isn't the bind.
  Consider `Automatic-Reboot-Time` jitter so VPS + guest don't reboot
  the same minute.

## lesson 2026-10-22: suwayomi reader blank pages were 5-minute JWT expiry, not downloads

- Impact: reader showed blank/missing pages on downloaded manga; ~11% of
  image loads 401'd (311/2828 over Oct 21-22) for one Firefox client.
  Downloads on disk were intact (valid JPEGs, zero 0-byte files).
- Cause: `server.jwtTokenExpiry = "5m"` (default) with `AUTH_MODE:
  ui_login`. Access tokens expire mid-chapter; the WebUI image path
  retries with the stale token, so the same page URL flips 200 -> 401 ->
  200 seconds apart while GraphQL calls keep succeeding. Feels like
  "downloaded but won't render".
- Detect: VPS `access.log` filtered to `mg.`: bursts of 401 on
  `/api/v1/manga/*/chapter/*/page/*` + `/thumbnail` interleaved with 200s
  on the same URLs; app `application.log` `UnauthorizedException` in
  `MangaController` (`handler$11` = page images, `thumbnail`).
- Repair: stop suwayomi, set `server.jwtTokenExpiry = "7d"` in
  `/mnt/data/apps/suwayomi/server.conf` (state-only, never in git;
  server rewrites the file on shutdown so stop-first is required),
  restart. Users re-login once to mint a 7d token. Refresh expiry stays
  60d; security tradeoff is a longer-lived bearer on a single-user box.
- Prevent: never leave `jwtTokenExpiry` at 5m on a ui_login reader box;
  `server.conf` TTLs are invisible to `make deploy` — audit them after
  any Suwayomi rebuild.

## incident 2026-10-22: bursty transit loss to VPS hangs large downloads (mg blank images)

- Impact: public `mg` (and jellyfin, proven by interleaved test) large
  responses randomly stall mid-stream (150-300KB then hang, 20-245s for
  400KB-1.3MB). Suwayomi reader shows blank pages with no spinner: its
  images are `Transfer-Encoding: chunked` with no `Content-Length` and no
  `accept-ranges`, so a stalled stream never errors, never resumes, and
  the reader waits silently. Small responses (GraphQL, 304s) unaffected.
- Cause: bursty sustained-TCP loss on the client<->VPS transit path, NOT
  the homelab. Proven: raw `scp` 1MB VPS->workstation 1.7s/1.5s/218s (no
  Caddy/tunnel/app); VPS->Hetzner 100MB in 4.4s (VPS uplink fine);
  VPS->backend 1.3MB in 0.25s 5/5; backend 2ms; ICMP 0% loss idle, under
  load, and MTR end-to-end. ICMP-clean + TCP-bulk-shredded = policer or
  shaper biting sustained flows, invisible to ping. Two client networks
  (Magenta cable `83.64.155.206`, Lebara FR 4G `141.98.208.x`) affected;
  phone pages that completed were 200 in 0.1-0.3s, blanks were hung rest.
- Detect: `curl` same 1.3MB asset on `mg` alternates 0.3s / 20s+ timeout;
  interleaved mg-vs-jellyfin large downloads stall on BOTH (vhost
  independent); VPS `ss -ti :443` shows mass `bytes_retrans` +
  `delivery_rate` kbps during stall; `access.log` shows 200s with huge
  durations, no 4xx/5xx.
- Mitigation: tailnet bypass. Private `suwayomi.h.malice.biz` over
  Tailscale: 10/10 large files 0.4s (1x 3s, delivered). Phone `pixel-8`
  already in tailnet (reconnect after 31d offline). Public path left as
  is — fault is upstream transit, nothing to fix in git.
- Prevent: when "slow" hits all vhosts at once with clean ICMP, test raw
  `scp` VPS->client before touching apps; if scp stalls, it's transit.
  Suwayomi chunked-no-length responses amplify any loss into blank
  pages — consider Caddy `reverse_proxy ... flush_interval -1`
  (buffering) for mg if transit stays lossy, trading TTFB for resumeable
  Content-Length responses.

## maintenance 2026-10-30: VPS wg0 peer cleanup, P2P DNAT ownership, UFW scope

- Confirm: VPS `wg0` (`10.30.0.0/24`, `:51820`) is load-bearing, not retired.
  It is the gluetun P2P exit for chill-01: 283 GB moved, egress IP
  `194.58.47.21`, 1030 live conntrack flows on `6881`/`50300`.
- Change: removed the retired malice peer (`10.30.0.3` + `192.168.1.0/24`)
  and the dead duplicate `109.0.200.185` peer (allowed `10.10.10.0/24`,
  `10.10.20.0/24`; the live f&f hub is debian-01's own `10.10.0.0/24`).
  Applied with `wg set wg0 peer <key> remove` plus a config edit, so
  gluetun's tunnel never dropped. Backup `/etc/wireguard/wg0.conf.bak-20261030`.
- Change: DNAT ownership moved into git `vps/nftables.conf` (`ip homelab_nat`).
  Deleted the dead `25565 -> 10.30.0.3` rule and the duplicate `6881` pair from
  the live `inet firewall` table by handle, and added `6881` + `50300`
  tcp+udp -> `10.30.0.4`. Public Minecraft only worked before because
  `homelab_nat` happened to win the duplicate.
- Change: chill-01 UFW `Anywhere on wg0 ALLOW` (v4+v6) -> `from 10.44.0.1`.
- Verify: 25565/6881/50300/64738 connect from off-site, public jellyfin 302,
  files 200, immich/fiesta 200 through the tunnel, gluetun egress still
  `194.58.47.21`, `wg show wg0` one live peer with a fresh handshake.
- Lesson: `/etc/nftables.conf` on the VPS is a boot dump (crowdsec runtime sets
  with timeouts, stale inline tables), not a reappliable config. Change live
  rules by handle (`nft delete rule ... handle N`), keep the file text in sync
  for the next boot, and validate with `nft -c -f` before shipping.
- Change (same day): removed the three dead `10.30.0.5/6/7` `wg0` peers, so the
  only peer left is gluetun `10.30.0.4`. Also dropped the five duplicate
  `iifname "eth0"` DNATs (`52000`, `3478`, `52100-52200`) from `inet firewall`:
  `homelab_nat` already owns them, and duplicate DNAT is what made the `25565`
  outage order-dependent. The five `iifname "wg0" ... 194.58.47.21` hairpin
  rules stay -- they are a different path, not duplicates.
- Verify (same day): `wg show wg0` one peer with a live handshake,
  `wg-quick strip wg0` parses, 25565/64738/52000/3478/6881/50300 all connect,
  `homelab-public-check` all green, `nft -c -f /etc/nftables.conf` exits 0.
- Change (same day): disabled malice's now-orphaned `wg-quick@wg0`
  (`systemctl disable --now`); its peer was removed from the VPS, nothing
  listened on `10.30.0.3`, and it was retrying a tunnel nobody answers.
- Verify (same day): real protocol checks, not just open ports -- Minecraft
  status handshake returns Paper 26.2 (players 0/20), qBittorrent logs
  "Detected external IP 194.58.47.21" and listens TCP+UTP/6881 on
  `10.30.0.4`, slskd serves folder listings over the tunnel, Mumble answers
  the 12-byte UDP ping, TURN answers a STUN binding request on UDP 3478, and
  Neko's UDP 52000 shows DNAT'd conntrack entries from the f&f site.
- Note: Neko does not answer unsolicited STUN on 52000 (WebRTC listener only
  replies inside an ICE session), so a no-reply probe there is not a failure.

## incident 2026-10-30: Beszel blind for 7 days, and no alert rules at all

- Impact: `homelab` system showed `down` since the 2026-10-23 20:52 reboot;
  last metric was 10-23 18:50. AGENTS claimed a "Beszel >85% disk alert"
  that did not exist -- the `alerts` table was empty and `user_settings`
  had email only (no MTA on the box), so disk-full would have alerted
  nobody.
- Detect: `systems.status=down`, `max(created)` in `system_stats` stale by
  7 days, `alerts` empty, hub log only startup lines.
- Cause: the agent listens on host `:45876` and the hub reaches it over
  its compose bridge. UFW only carried an **IPv6** allow for `45876` on
  `br-8d449473ddc0`; after the reboot the IPv4 path was default-denied,
  so the hub's connection was dropped. `HUB_TO_AGENT_FAIL` from
  `nsenter -t <hub pid> -n` proved it.
- Repair: `ufw allow proto tcp from 172.16.0.0/12 to any port 45876`
  (live + `bootstrap.sh`); source is the whole docker /12 because Docker
  assigns bridge subnets dynamically.
- Repair: created Gotify app `beszel`, set the user webhook to
  `gotify://gotify:80/<token>?disabletls=yes&priority=5`, set
  `meta.appURL` to `https://beszel.h.malice.biz`, and added the alert
  rule. Beszel 0.9 semantics: `value` = threshold, `min` = minutes above
  it before firing.
- Verify: system `up`, fresh `1m` stats, a threshold-1 test rule fired
  `homelab disk usage above threshold` into Gotify (message id 3), then
  the real rule was set to `Disk` / `value 85` / `min 5`, `triggered 0`.
- Prevent: after any chill-01 reboot, confirm `systems.status=up` and a
  metric younger than 5 minutes. Keep agent UFW scoped to `172.16.0.0/12`,
  never a single `br-*` interface.

## maintenance 2026-10-31: VPS SSH is key-only

- Change: `/etc/ssh/sshd_config.d/00-homelab-hardening.conf` sets
  `PermitRootLogin prohibit-password`, `PasswordAuthentication no`,
  `KbdInteractiveAuthentication no`. The drop-in is included at the top of
  `sshd_config`, and OpenSSH takes the first value it reads, so it overrides
  `PermitRootLogin yes` / `PasswordAuthentication yes` further down.
  Backup: `/etc/ssh/sshd_config.bak-20261031`.
- Change: `vps/bootstrap.sh` writes the same drop-in, so `make vps` keeps it.
- Verify: `sshd -t` before reload; `sshd -T | grep -Ei "permitroot|passwordauth"`
  shows `without-password` / `no`; a fresh key login works; a forced password
  login fails with `Permission denied (publickey)`.
- Note: root keeps a local console password for the provider's recovery
  console -- that is the fallback, not an SSH path.

## maintenance 2026-10-31: deploy keeps the Suwayomi secret, live configs adopted

- Change: `Makefile` deploy adds `--exclude media/suwayomi-auth-password`.
  `rsync --delete` was deleting the live-only secret file on every deploy
  (dry-run: `*deleting media/suwayomi-auth-password`), which would have
  broken Suwayomi login by removing the password file it mounts.
- Change: three live-only edits adopted into git, so a deploy stops
  reverting them: screego `1.12.6` + `SCREEGO_TURN_DENY_PEERS` (blocks TURN
  relaying into private/LAN/tunnel nets), the private
  `jellyfin.h.malice.biz` vhost in `stacks/edge/Caddyfile`, and suwayomi
  `v2.4.2422-preview`.
- Verify: `make deploy` re-ran with zero container re-creations; secret still
  0600 after deploy; running containers report `screego/server:1.12.6`,
  `TURN_DENY` env present, suwayomi `v2.4.2422-preview`; public check and
  `autotag --self-check` green.
- Prevent: any live-only file under `/opt/stacks` needs an explicit rsync
  exclude, or it disappears on the next deploy.

## maintenance 2026-10-31: audit batch (alerts, deploy safety, Stirling, storage)

- Change: public check runs every 15 minutes (was daily); `notify@.service`
  logs delivery failures to the journal instead of failing silently on an
  empty `ALERT_URL`; weekly prune uses `prune -f` so images of stopped
  containers survive; the backup VPS pull now downloads to a temp dir and
  swaps only on success (a failed scp no longer wipes the old WireGuard
  copy); `shellcheck` ships in `bootstrap.sh` and `make check` falls back to
  the container image on a dev box without it.
- Change: Stirling is private-only. Removed `stirling.malice.biz` from
  `vps/sites/chill.caddy`; `stirling.h.malice.biz` answers 401 over
  Tailscale.
- Change: `/mnt/data` moved off the 4 TB bulk disk. It was a bind of
  `/mnt/pool/takeover-primary/r1/mnt/data`; it is now the `pve1-primary`
  virtiofs share (2 TB, backed up).
  - Steps: stop all stacks; rescue primary-only files to
    `/root/primary-only-20261031` (130 files, 156M); `rsync -aHAX
    --numeric-ids --delete` takeover tree -> `/mnt/primary` (2,374 files,
    104.5 GB, 177 deletions); compare `find -type f | wc -l` (32,956 both)
    and `du -sb` (590,584,670,668 bytes both); remove the bind line from
    guest `/etc/fstab`; umount/mount `/mnt/data`; start stacks.
  - Verify: `findmnt` shows `pve1-primary`; write test as deploy OK;
    public-check exit 0 (17 ok, one fewer because Stirling left the public
    set); 37 containers up, none unhealthy; Immich 200, Paperless 302,
    Jellyfin 302, Navidrome 302, fiesta 200, Stirling 401, slskd 200,
    wrtag 200, Minecraft port open, gluetun egress still `194.58.47.21`.
- Lesson: `bootstrap.sh` appended `pve1-primary /mnt/data` *in addition to*
  the takeover bind line (its `grep -q "$tag"` matched a substring), so
  `mount -a` stacked the primary share over the live tree and app writes
  briefly landed on the stale Sep tree. Fixed: the ensure now matches the
  full fstab line, and the bootstrap deletes any `/mnt/data none bind` line
  first. Re-ran `make host`: one line, correct mount, containers untouched.
- Rollback: the takeover tree on bulk is untouched; re-add the bind line and
  remount to go back until the next verified restic backup.

## incident 2026-11-02: power cut, then chill egress dead from stale router ARP

- Symptom: every public vhost returned 502; malice, chill-01 and the LAN were
  unreachable. Cause: house power cut, malice down since ~2026-11-01 18:22Z
  (VPS up, Caddy answering, WireGuard and Tailscale peers gone).
- Recovery after power: malice booted 10:12Z, VM 101 and all 37 containers
  came up, VM 103 running. Checked: no failed units, all six host disks
  0 reallocated / 0 pending sectors, no ext4 errors, restic backup ran at
  10:15Z (prune finished clean), backup watchdog 48h window fine,
  Immich/Paperless postgres accepting, Sunday vzdump from 11-01 03:30
  present on vault, public-check exit 0 after the fix below.
- Second fault: chill-01 had DNS and a live `wg0` handshake but no internet
  and no WG data path (`public-check` FAIL 000 on every host). The router
  still mapped `192.168.1.28` to a dead MAC (`da:f6:59:14:fb:40` instead of
  `bc:24:11:f3:94:93`) and dropped replies addressed to it; tcpdump on malice
  `vmbr0` showed `1.1.1.1 > 192.168.1.28` replies with dst MAC `da:f6:...`.
  GARP from chill (request and reply form, broadcast and unicast to the
  router) did not refresh it -- treat the router entry as static/pinned.
- Workaround (live): chill egress relays via malice, which masquerades on
  `vmbr0`, so replies come back to malice's MAC and are forwarded.
  `qm set 101 --ipconfig0 ip=192.168.1.28/24,gw=192.168.1.2`.
  `/etc/netplan/99-homelab-relay.yaml` was deleted: it never won (metric 50
  lost to cloud-init's metric-0 default via `.1`), and a policy-route version
  hijacked the WG/LAN paths, so the relay has to be the VM's only default.
- Undo once the router ARP entry is cleared on-site (reboot router or delete
  the static entry): `qm set 101 --ipconfig0 ip=192.168.1.28/24,gw=192.168.1.1`,
  then `netplan apply` in the guest. Verify `ping 1.1.1.1` and
  `curl https://files.malice.biz` from chill, and public-check exit 0.
- Note: chill is a VM on malice, so relaying through malice adds no failure
  mode beyond malice itself; the lab was already down when malice was.
- Follow-up 2026-11-02 (Livebox rebooted): the mapping survived the reboot.
  A raw ARP probe from malice (`who-has 192.168.1.28`) is answered only by
  chill (`bc:24:11:f3:94:93`), yet the router still sends `.28` traffic to
  `da:f6:59:14:fb:40` -- so it is a persistent device record (a former
  randomized-MAC phone/laptop), not cached ARP. The router also refuses a
  static lease on `.28` as "already in use" and refuses `.2` because it is
  outside the DHCP pool. Relay stays until that record is deleted in the
  Livebox device list, or chill is renumbered.
- Resolution 2026-11-02: the record was a phone, `A35-de-Dimitri`
  (`DA:F6:59:14:FB:40`, randomized Wi-Fi MAC) that grabbed `.28` from DHCP
  during the power cut; it was deleted from the Livebox history page
  ("Supprimer ..."). The router still answered `.28` to that MAC afterwards,
  so chill-01 was renumbered out of the DHCP pool: `ipconfig0
  ip=192.168.1.200/24,gw=192.168.1.1`, guest netplan regenerated, Jellyfin LAN
  bind -> `192.168.1.200:8096` in `stacks/media/docker-compose.yml`, relay
  route removed. Verified: direct egress, WG handshake + data (VPS backend
  307), 37 containers, Jellyfin LAN 302, public check exit 0.
  The Livebox DHCP pool is `.10-.150`; `.28` is still poisoned inside it, so a
  further router reboot is worth doing and `.28` must not be reused.
  Router API notes: SoftAtHome WS4 at `POST /ws`
  (`application/x-sah-ws-4-call+json`), login via
  `sah.Device.Information.createContext` with `Authorization: X-Sah-Login`,
  then `Authorization: X-Sah <ctx>` + `X-Context: <ctx>`; `Devices`,
  `DHCPv4.Server` and `TopologyDiagnostics` are ACL-denied to that context,
  so the GUI (or `NeMo.Intf.lan.getMIBs`) is the only way to read/modify them.
  Device records can be removed from
  `/internal/devicesHistory/index.html` ("Supprimer ...").
- Open follow-ups from this incident:
  - Point the TVs' Jellyfin bookmarks at `http://192.168.1.200:8096`; the
    `192.168.1.28:8096` bind no longer exists.
  - Reboot the Livebox once more when convenient to try to flush the `.28`
    mapping, and never assign a lab host `.28` again. `.28` is inside the
    DHCP pool (`.10-.150`), so any device the router hands it to will lose
    inbound replies (outbound works, return traffic goes to the dead MAC).
  - The live DHCP lease list should only carry `Device-22 -> .53`; the dead
    guest leases (`.48 .118 .36 .37 .27`) and the mis-typed `.50`/`.88`
    reservations were removed on 2026-11-02.

## maintenance 2026-11-02: sdc retired, takeover made live, host upgraded

- Impact: brief `/mnt/data` I/O outage on chill-01 (~10 min) during the
  sdc offlining — guest 101 was still on `pve1-primary`, not the
  takeover bind as docs assumed. Full recovery, zero data loss.
  Post-reboot `homelab-public-check` green (13 vhosts + 4 TCP) after
  ~2 min container warmup (mg/paperless/photos 502 + MC TCP fail
  immediately post-boot, same as the Sep 30 pattern).
- Cause (docs vs live): TODO/RUNBOOK said `/mnt/data` was the takeover
  bind since Oct 19. Live guest fstab still had
  `pve1-primary /mnt/data virtiofs` — the Oct 19 "reboot-proofed" edit
  never landed in the guest (backup `/tmp/fstab.bak-20261019-rebind`
  gone with tmpfs). The 2026-10-26 "takeover newer on every path"
  verification compared trees without noticing the guest wasn't ON the
  takeover. Offlining sdc broke the live virtiofs an hour later.
- Repair: SCSI rescan re-attached sdc as `sdg`, mounted ro, rsync
  `--update` salvaged newest files to the takeover tree (minecraft
  world/config + logs; 0 remaining after pass 2), then guest cutover:
  `umount -l /mnt/data` + `mount --rbind` takeover, fstab rewritten to
  the bind (generator verified `What=takeover`), all 37 containers
  restarted, sdc re-offlined. Host music bind re-pointed:
  takeover `media/music` (301G) ro over `/mnt/pool/media/music`
  (fstab-persisted); `/mnt/bulk/media/music` follows via the pool bind.
- Host work (same window): sdc retired (NFS dropped, debian-01
  automount stopped + mountpoint removed, fstab commented, `virtiofs0`
  deleted, device offlined — reappears as `sdc` each boot until
  physically pulled, re-offline or ignore); nft `ip nat` flushed;
  stale `.48/.79/.118` + `10.30` iptables + tailnet DNAT deleted;
  `arr-routing` emptied; `iptables-restore.service` disabled;
  nfs-server/rpcbind(+socket) disabled; HA lrm/crm disabled;
  `PermitRootLogin prohibit-password`; 6.17.2 kernel purged;
  orphan `pre-trim-20260916` snapshot config removed; both failing
  backup crons deleted; `hermes` user/token/ACL/system-user/`hermesctl`
  removed; `firewall=1` dropped from both NICs; OpenTofu tokens given
  +90d expiry (unused 90d — delete if still idle); `swappiness=10`;
  sdd long self-test + smartd schedule; `newaliases`;
  `malice-restic-backup` git-owned + `OnFailure=notify@` live;
  `/etc/homelab.env` copied from guest (0600, host switched to
  `gotify.h` tailnet URL — public `gotify.malice.biz` has no VPS route
  and TLS-errors); non-final dumps + ISO + skeletons removed (~4.2G).
- Upgrade: both guests sata→scsi (`virtio-scsi-single`, `iothread=1`,
  `ssd=1`, `boot order=scsi0`; PARTUUID fstab so no guest edits) —
  103 boot-tested on `virtio-scsi-pci` first, then both switched to
  `-single` for working iothreads. `apt full-upgrade` → pve-manager
  9.2.25, kernel 7.0.14-26, qemu-server 9.2.14; reboot clean
  (75s, both guests `onboot`, scsi boots fine).
- Prevent: never trust "bind is live" from docs — `mount | grep
  /mnt/data` on the GUEST is the proof before touching the old disk.
  Takeover/bind claims must be re-verified live, not carried forward.
  `/tmp` backups don't survive reboot — keep fstab/config backups in
  git or `/root`, not `/tmp`.
- Physical TODO: pull sdc + sda on-site per the disk-swap plan (sdc
  still in slot, kernel-offlined). TOTP for root@pam still open
  (needs interactive QR enrollment via the PVE web UI).

