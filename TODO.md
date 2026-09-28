# todo

## next (updated 2026-09-28)

### P0 — access / tailnet (new identity live)

- Tailnet move 2026-09-27 (UndauntedGeiger replaces frasseberry):
  verified 2026-09-28 from fedora: `malice` (100.99.204.109) and
  `chill-01` (100.92.173.71) ping + ssh ok on UndauntedGeiger;
  `ssh malice` -> `qm list` shows 101 running, 102 stopped, 103 running;
  `pct list` shows 200 stopped, 204 running. Stale
  `malice.taila725ed.ts.net 100.90.216.64` still listed on frasseberry,
  offline 20h. Retire frasseberry: remove that shared copy from admin
  console, delete old machines, move macbook/towa/pixel-8/hermes-01,
  revoke used auth keys.
- VPS fallback SSH: REMOVED 2026-09-28 (line 5 `root@debian-13`
  deleted from `/etc/pve/priv/authorized_keys`; pre-removal copy at
  `/root/authorized_keys.before-fallback-removal-2026-09-28`). Original
  `/root/authorized_keys.bak-2026-09-27` untouched.
- Access matrix (UndauntedGeiger): `ssh malice` for Proxmox;
  `ssh chill-01` (deploy@100.92.173.71 via Tailscale, works 2026-09-28)
  for the VM; `qm guest exec 101` via malice also works (wg0
  10.44.0.2/24 confirmed inside guest). BROKEN: `deploy@10.44.0.2`
  (WG-only) times out from fedora (no route) and from malice; do not
  use bare `make deploy`/`make host` until fixed — override
  `HOST=chill-01` instead. Emergency only `ssh vps` -> `ssh 10.30.0.3`.

### P1 — deploy path + backups (graceful, cloud first)

- Deploy fix: `HOST=chill-01` (Tailscale) works; WG `10.44.0.2` path
  does not. Use `make host HOST=chill-01` / `make deploy HOST=chill-01`
  until Makefile default is updated or a connected host is designated.
  Then ship jellyfin /mnt/fast cache move + guest pve1-archive path
  rename /mnt/archive -> /mnt/vault (both already in git).
- Backups 2026-09-28: nightly FAILED this morning (last-ok
  2026-09-27T04:31, failed 2026-09-28T04:41, no script output). Cause:
  live script failed closed on early `mountpoint -q /mnt/backup` +
  service `RequiresMountsFor=... /mnt/backup`, guest has no /mnt/backup.
  FIXED in git + shipped 2026-09-28 via `make host HOST=chill-01`
  (exit 0, live md5 matches git): service requires only
  /mnt/data /mnt/fast; script runs cloud first, local fails loud after.
  Manual cloud run 16:23 churned (no auto-parent, full re-read) —
  stopped, stale lock cleared, re-ran parented
  (`--parent 8513e3b4`, the 09-27 snapshot) 16:33, calm.
  VERIFIED 16:52: new snapshot 3eca779f (327G — ~182G drop matches the
  new media/downloads + messy excludes), all dumps present
  (immich.sql, paperless.sql, gotify/beszel/dockge/kavita dbs);
  last-ok stamped 2026-09-28T16:52, watchdog green. Full chain intact
  (37 snapshots). Prune left to the nightly run. Local copy still owed
  (share below). Watchdog deadline 09-29 04:31.
- Virtiofs share for /mnt/backup — WIRED 2026-09-28 (~17:00 UTC,
  services down ~10 min, accepted): mapping `pve1-backup->/mnt/backup`
  created on malice, `qm set 101 --virtiofs4 pve1-backup`, full
  `qm stop`/`qm start` 101 (iGPU vfio OpRegion ok), guest fstab
  `pve1-backup /mnt/backup` via `make host HOST=chill-01`, mounted
  (916G). NOTE: guest regenerates SSH host keys on boot (cloud-init) —
  verified new ED25519 fingerprint via `qm guest exec` before trusting,
  updated local known_hosts. Service `RequiresMountsFor` re-added
  /mnt/backup (in git + shipped). `restic init` done on
  /mnt/backup/restic; first local backup running detached as
  homelab-local-backup. Cloud S3 flaky since ~16:57 (503s on Stat,
  reads hanging) — cloud already holds verified 16:52 snapshot;
  tonight's timer retries cloud. Bootstrap fstab pve1-archive ->
  /mnt/vault shipped with it.
- Restore drill: extend `make restore-test` to kavita/dockge/beszel
  (currently immich/paperless/gotify + homelab.env + wg0.conf + VPS
  Caddy/nftables), then re-run one drill to a temp path. Watchdog gives
  48h (last-ok 09-27, so must succeed by 09-29).

### P2 — app health after deploy

- Jellyfin DB check DONE 2026-09-28: `PRAGMA integrity_check` ok on
  jellyfin.db + library.db (09-20 rollback leftover cleared by restart);
  HLS/cache on /mnt/fast via compose (verify next film night).
- Jellyfin qsv->vaapi switch DONE 2026-09-28: flipped
  HardwareAccelerationType qsv->vaapi in encoding.xml (backup
  encoding.xml.pre-vaapi-20260928), restarted healthy, log confirms
  `VAAPI device /dev/dri/renderD128 is Intel GPU (iHD)`. Proved on the
  exact glitch file (Ford v Ferrari 4K remux, HEVC 10-bit + PGS):
  30s overlay_vaapi burn-in test in-container, 719 frames, ~3x speed,
  zero errors. i7-8700K UHD 630 uses the same silicon either way;
  VAAPI drops the buggy overlay_qsv stage. Rollback: flip the tag back
  + restart.
- qBittorrent hygiene with deploy: still references retired
  /mnt/archive paths (seeding handles held 228G post-delete 09-21).
  Remove dead torrents or repoint save-paths; expect torrent errors
  until cleaned.

### P3 — hygiene / docs

- Commit pending docs (README, RUNBOOK, TODO, host/README,
  homelab.env.example, photos compose comment: role swap + vault).
- `privacy` stack DITCHED 2026-09-28 (unused): no containers, no
  /opt/stacks/privacy; leftover volume privacy_companioncache (184K,
  unreferenced) removed. Nothing in git references it.
- Document `beszel-agent` network_mode:host exception (AGENTS.md
  requires documented 0.0.0.0/host binds; screego has one, beszel
  does not).
- Prevention owed from disk-full: >85% disk Gotify alert + weekly
  builder/image prune (images back at 31G).
- Add minimal GitOps with systemd.
- Add public exposure guard.
- Write short incident samples. (navidrome blackhole: stale slskd-egress
  mark rule; document when writing these. New candidates: 09-21
  virtiofs-held-space after archive clear; 09-21 role swap.)
- Guest states (verified 2026-09-28, matches 2026-09-21 notes): running
  chill-01 (101), debian-01 (103), hermes-01 (204). Stopped: alpine-01
  (102), friend (200). DESTROYED 09-21: homelab LXC 888 and homelab-01
  VM 100 (last image kept at /mnt/vault/backup-old-vm-lxc). LXC 200
  still onboot:1; rootfs on fast, detached unused0 removed.
- Known gaps: /mnt/data/photos bind is correct (UPLOAD_LOCATION=/photos)
  but the library is still empty (nothing uploaded yet; only 178M of
  Immich auto-backups sit in the /data docker volume on the VM disk,
  outside restic paths). Future uploads land on the mirror and are
  covered; revisit if the /data volume grows.

## done

- vzdump scheduling DONE 2026-09-21 (`weekly-vault`: all guests,
  snapshot, zstd, Sun 03:30, keep-last 8, proof snapshot ok; verified
  active 2026-09-28).
- local-lvm Data% 32.8% 2026-09-21 (old 79% watch retired; 37.7%
  2026-09-28, healthy).
- Jellyfin HW accel (done 2026-09-20: VT-d enabled in BIOS, iGPU 8086:3e92
  on vfio-pci, hostpci0 on VM 101, PVE 9.2.20 kernel 7.0.14-17,
  renderD128 in chill-01, QSV enabled, h264_qsv verified in-container;
  compose carries group 991. Rollback: /root/101.conf.pre-igpu on malice.)
- Jellyfin transcode tuning (done 2026-09-20 post-film: encoding.xml set
  HEVC HW decode on (was h264/vc1 only), throttling on, segment deletion
  on with keep 120s (was off/720s); restart clean, 0 errors, h264_qsv
  encode + hevc_qsv decode of the F1 remux verified in-container.
  Rollback: encoding.xml.pre-qsv-tune-20260920 next to encoding.xml.)
- Jellyfin transcodes to /mnt/fast SSD (done 2026-09-21 in git: compose
  mount /mnt/fast/jellyfin-cache:/cache + deploy creates/chowns it. After
  deploy, old /opt/stacks/media/state/jellyfin-cache can be deleted if empty.)
- Incident 2026-09-20 ~19:20 UTC: Jellyfin root disk full during F1 4K
  remux playback (Tizen). Cause: HLS transcode to /cache on the 80G VM
  root disk (26G, 625 .ts, one session) + 42G docker images filled / to
  100%/0 free. Impact: ffmpeg log writes failed (exit 228), 80x SQLite
  Error 13 disk full, 1354x rollback cascade on POST
  /Sessions/Playing/Progress (resume not saving), HLS stalls; container
  stayed healthy, no restart, movie kept playing. Fix (live, no pause):
  builder prune (2.8G) + removed orphan images only (pgvecto-rs, pingvin,
  gonic, uptime-kuma, joplin, scrutiny, searxng, homepage, slskd/feishin
  old tags, invidious, adguard, vaultwarden, syncthing) -> 83%/13G free,
  ENOSPC cleared. Leftover: rollback errors persist until a jellyfin
  restart + db integrity check (after the movie); durable fix is the
  /mnt/fast (or /mnt/pool) cache move above. Full postmortem in
  RUNBOOK.md: incident 2026-09-20.

## storage layout

Intended end state; Proxmox paths and virtiofs tags never change, only
the devices behind them move.

- 4TB HDD (sdd ST4000DM004, /mnt/bulk -> /mnt/pool): movies, TV,
  downloads, disposable/re-downloadable media; excluded from backups.
- 2TB HDD (sdc ST2000DX002, /mnt/primary shared as pve1-mirror ->
  /mnt/data): important data, photos, documents, clean music, app data.
- Vault disk (sdb, host /mnt/vault, shared as pve1-archive -> guest
  /mnt/vault): Proxmox vzdump target (`data` store + weekly
  `weekly-vault` job, snapshot mode, zstd, keep-last 8; live since
  2026-09-21, proof snapshot ok). Also holds
  `/mnt/vault/backup-old-vm-lxc` (VM-100 last image, arr-203 final tar,
  users/ keeps). Renamed from /mnt/archive 2026-09-21 (mount + storage +
  mapping rewired, chill-01 stop/started, 36 containers back). Guest
  mountpoint moved to /mnt/vault in git + shipped 2026-09-28
  (bootstrap fstab). Restic to Hetzner S3 stays as the offsite copy.
- 1TB HDD (sda WDC WD10TPVT, host /mnt/backup, guest /mnt/backup via
  pve1-backup virtiofs4 since 2026-09-28): local restic drive
  (`/mnt/backup/restic`, init done 2026-09-28, first backup running).
  Cleared 2026-09-21 (stale 504G pre-cutover mirror proven redundant by
  file-list diff, migration scratch, old 101/203 snapshots removed;
  VM-100 image, arr-203 tar, users/ moved to vault, md5-verified).
- SSD 1 (sde Samsung 850 EVO): Proxmox and VM disks.
- SSD 2 (sdf PNY CS900, /mnt/fast): disposable scratch/cache: Jellyfin
  transcodes, DB dumps, imports, build/scratch staging. Hands off for
  family data. Photos do NOT live here (mirror now).

Do not add RAID or ZFS complexity until matching disks exist.
Do not expose /mnt/backup or /mnt/vault to apps or family storage; they are backup-only.
