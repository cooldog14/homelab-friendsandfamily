# todo

## next (updated 2026-09-21 evening)

- Commit pending docs (README, RUNBOOK, TODO, host/README,
  homelab.env.example, photos compose comment: role swap + vault).
- Backups phase: `restic init` on /mnt/backup; solve chill-01 visibility
  (new virtiofs share for /mnt/backup vs host-side restic); rewire
  backup.sh/service defaults off guest /mnt/archive; extend restore-test
  to kavita/dockge/beszel; re-run one restore drill to a temp path.
- Deploy fix: `deploy@10.44.0.2` unreachable from towa (no route), key
  denied from malice. Repair SSH path or designate a connected host,
  then `make deploy` (ships jellyfin /mnt/fast cache move + guest
  pve1-archive path rename /mnt/archive -> /mnt/vault).
- Jellyfin DB check: restart + SQLite integrity check (rollback-error
  leftover from 09-20 disk-full); verify HLS lands on /mnt/fast;
  delete old /opt/stacks/media/state/jellyfin-cache if empty.
- qBittorrent hygiene with deploy: still references retired
  /mnt/archive paths (seeding handles held 228G post-delete 09-21).
  Remove dead torrents or repoint save-paths; expect torrent errors
  until cleaned.
- Guest states 2026-09-21: running chill-01 (101, 36 containers),
  debian-01 (103), hermes-01 (204). Stopped: alpine-01 (102), friend
  (200). DESTROYED 09-21: homelab LXC (888, via pct destroy after
  confirming its disk was the only copy — gone from pct list) and
  homelab-01 VM (100, gone; last image kept at
  /mnt/vault/backup-old-vm-lxc). LXC 200 still onboot:1 (auto-starts
  on host reboot); rootfs on fast, detached unused0 removed.
- Known gaps: /mnt/data/photos bind is correct (UPLOAD_LOCATION=/photos)
  but the library is still empty (nothing uploaded yet; only 178M of
  Immich auto-backups sit in the /data docker volume on the VM disk,
  outside restic paths). Future uploads land on the mirror and are
  covered; revisit if the /data volume grows.
  local-lvm Data% 32.8% 2026-09-21 (old 79% watch retired); vzdump
  scheduling DONE 2026-09-21 (`weekly-vault`: all guests, snapshot,
  zstd, Sun 03:30, keep-last 8, proof snapshot ok).
- `privacy` stack runs live (/opt/stacks/privacy) but is NOT in Makefile
  STACKS: decide add-it vs intentionally hand-managed.
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
- Jellyfin HW accel (done 2026-09-20: VT-d enabled in BIOS, iGPU 8086:3e92
  on vfio-pci, hostpci0 on VM 101, PVE 9.2.20 kernel 7.0.14-17,
  renderD128 in chill-01, QSV enabled, h264_qsv verified in-container;
  compose carries group 991. Rollback: /root/101.conf.pre-igpu on malice.)
- Jellyfin transcode tuning (done 2026-09-20 post-film: encoding.xml set
  HEVC HW decode on (was h264/vc1 only), throttling on, segment deletion
  on with keep 120s (was off/720s); restart clean, 0 errors, h264_qsv
  encode + hevc_qsv decode of the F1 remux verified in-container.
  Rollback: encoding.xml.pre-qsv-tune-20260920 next to encoding.xml.)
- Jellyfin qsv->vaapi switch (open: green glitch on Ford v Ferrari 4K remux
  traced to the overlay_qsv PGS burn-in stage, encode log clean at ~2x.
  VAAPI uses the same iHD driver/silicon with equal speed/quality and the
  more stable overlay_vaapi; UHD 630 has no QSV-only features. Flip
  HardwareAccelerationType in encoding.xml + restart at a quiet moment.)
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
  /mnt/fast (or /mnt/pool) cache move above.

## storage layout

Intended end state; Proxmox paths and virtiofs tags never change, only
the devices behind them move.

- 4TB HDD (sdd ST4000DM004, /mnt/bulk -> /mnt/pool): movies, TV,
  downloads, disposable/re-downloadable media; excluded from backups.
- 2TB HDD (sdc ST2000DX002, /mnt/primary shared as pve1-mirror ->
  /mnt/data): important data, photos, documents, clean music, app data.
- Vault disk (sdb, host /mnt/vault, shared as pve1-archive -> guest
  /mnt/archive): Proxmox vzdump target (`data` store + weekly
  `weekly-vault` job, snapshot mode, zstd, keep-last 8; live since
  2026-09-21, proof snapshot ok). Also holds
  `/mnt/vault/backup-old-vm-lxc` (VM-100 last image, arr-203 final tar,
  users/ keeps). Renamed from /mnt/archive 2026-09-21 (mount + storage +
  mapping rewired, chill-01 stop/started, 36 containers back). Restic to
  Hetzner S3 stays as the offsite copy.
- 1TB HDD (sda WDC WD10TPVT, /mnt/backup host-only): cleared 2026-09-21
  (stale 504G pre-cutover mirror proven redundant by file-list diff,
  migration scratch, old 101/203 snapshots removed; VM-100 image, arr-203
  tar, users/ moved to vault, md5-verified). Designated local restic
  drive (`/mnt/backup/restic`). OPEN: chill-01 has no /mnt/backup —
  restic repo wiring (new virtiofs share or host-side restic) belongs to
  the backups phase; `restic init` still owed.
- SSD 1 (sde Samsung 850 EVO): Proxmox and VM disks.
- SSD 2 (sdf PNY CS900, /mnt/fast): disposable scratch/cache: Jellyfin
  transcodes, DB dumps, imports, build/scratch staging. Hands off for
  family data. Photos do NOT live here (mirror now).

Do not add RAID or ZFS complexity until matching disks exist.
Do not expose /mnt/backup or /mnt/vault to apps or family storage; they are backup-only.
