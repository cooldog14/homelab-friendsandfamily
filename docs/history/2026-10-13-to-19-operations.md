# Operations — October 13–19, 2026

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

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

