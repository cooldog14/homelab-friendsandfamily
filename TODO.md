# todo

## next

- Deploy current repo. (done 2026-09-17: media on chill-01, photos on mirror)
- Drive swap, in order: sdd becomes bulk (done 2026-09-18, verified
  byte-identical, dashboard shows 3.6T/31%), sdc becomes primary (done
  2026-09-19: mkfs + rsync 19:35->22:08, delta sync, mapping repointed,
  VMs stop/started, guest sees 1.8T/28%), sda becomes the local restic
  repo (open: 2b free-space vs 2c local repo).
- Lesson: host-side disk remounts are invisible to chill-01 until it
  reboots (virtiofsd pins the old filesystem at VM start; guest
  remount alone does not refresh it). Plan reboots for step 2 as well.
- Lesson 2026-09-19: repointing a virtiofs directory mapping needs a
  full VM stop/start; guest reboot alone keeps the old virtiofsd.
  Cutover proof: write round-trip guest<->/mnt/primary, tree diff vs
  old copy showed only 2 live paperless shm/wal files, restore-test ok
  2026-09-19, first new-disk snapshot 1f643421 on 2026-09-20 reused
  parent 2cff3a26 (incremental, no re-seed).
- sda reality check: mount is /mnt/backup, not /mnt/backupcopy; holds
  the stale 504G pre-cutover mirror (user trims it) plus dump/,
  backup-diskX/, arr-configs/. Settle the name when doing 2c.
- Incident 2026-09-20 ~15:20 UTC: home internet loss, malice rebooted.
  /mnt/primary had NO fstab entry (was mounted by hand on 09-18), so it
  did not remount: guests served an empty shadow dir for ~10 min and
  homelab-01 wrote 155M of fresh DB files into it (preserved at
  /root/primary-shadow-20260920, real data untouched on sdc1). Fixed:
  UUID fstab entry added, disk mounted + verified 504G intact, music
  bind re-seated, VMs stop/started for virtiofsd re-export, stop
  orders re-applied. Lesson: every migrated disk gets its fstab line
  the same day it is cut over; verify with a reboot, not just a mount.
- Guest states 2026-09-19: running chill-01 (all 7 stacks), debian-01,
  hermes-01. Stopped: homelab-01 (VM 100), friend (200), arr (203),
  homelab LXC (888), alpine-01. LXC 888 is a future removal, do
  not repoint it. (Note: host reboot 2026-09-20 auto-started
  onboot guests incl. 100/200/203; re-stopped 100+200. LXC 203/arr
  destroyed 2026-09-20 after archiving /opt/arr to
  /mnt/backup/arr-203-final-20260920.tar.gz (2.9G, integrity-checked);
  /mnt/fast freed to 4%.)
- Jellyfin LAN bind for direct TV playback (done 2026-09-19, commit
  91bc3d8: LAN_IP 192.168.1.28:8096 + UFW scoped to 192.168.1.0/24).
  TV at http://192.168.1.28:8096; public vhost unchanged. DLNA skipped.
- Known gaps: /mnt/data/photos bind is correct (UPLOAD_LOCATION=/photos)
  but the library is still empty (nothing uploaded yet; only 178M of
  Immich auto-backups sit in the /data docker volume on the VM disk,
  outside restic paths). Future uploads land on the mirror and are
  covered; revisit if the /data volume grows.
  local-lvm at 79% (watch); vzdump.cron empty (no scheduled VM
  snapshots despite host README prescribing them).
- Add minimal GitOps with systemd.
- Add public exposure guard.
- Run one restore drill. (done 2026-09-17 against S3; re-run ok
  2026-09-19 post-cutover)
- Write short incident samples. (navidrome blackhole: stale slskd-egress
  mark rule; document when writing these)
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
- Jellyfin transcodes to /mnt/fast SSD (open: compose mount
  /mnt/fast/jellyfin-cache:/cache + segment deletion; reverted 2026-09-19,
  redo on a quiet evening. A 78M cache seed may still sit at
  /mnt/fast/jellyfin-cache.)
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
  downloads, disposable media.
- 2TB HDD (sdc ST2000DX002, /mnt/primary shared as pve1-mirror ->
  /mnt/data): important data, photos, documents, clean music, app data.
- 1TB HDD (sda WDC WD10TPVT, /mnt/backupcopy host-only): second restic
  repo (local copy of photos + important data). Restic to Hetzner S3
  stays as the offsite copy.
- SSD 1 (sde Samsung 850 EVO): Proxmox and VM disks.
- SSD 2 (sdf PNY CS900, /mnt/fast): cache, DB dumps, transcodes,
  staging. Hands off. Photos do NOT live here (mirror now).

Do not add RAID or ZFS complexity until matching disks exist.
Do not touch /mnt/archive (sdb) until the bulk move verifies green.
