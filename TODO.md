# todo

## next

- Deploy current repo. (done 2026-09-17: media on chill-01, photos on mirror)
- Drive swap, in order: sdd becomes bulk (done 2026-09-18, verified
  byte-identical, dashboard shows 3.6T/31%), sdc becomes primary, sda
  becomes the local restic repo.
- Lesson: host-side disk remounts are invisible to chill-01 until it
  reboots (virtiofsd pins the old filesystem at VM start; guest
  remount alone does not refresh it). Plan reboots for step 2 as well.
- Add minimal GitOps with systemd.
- Add public exposure guard.
- Run one restore drill. (done 2026-09-17 against S3)
- Write short incident samples. (navidrome blackhole: stale slskd-egress
  mark rule; document when writing these)

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
