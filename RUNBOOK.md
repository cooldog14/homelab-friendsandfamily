# runbook

Break one thing at a time.
Use a quiet window.
Do not test by deleting data.

## public service down

Break: stop one harmless public service.
Observe: public-check fails, Gotify alerts, systemd logs show failure.
Repair: restart the stack from Dockge or docker compose.
Note: detection time and repair time.

## private caddy bad config

Break: test a bad edge Caddy config.
Observe: edge-reload must fail before restart.
Repair: restore the valid config.
Note: whether validation blocked the outage.

## backup stale

Break: simulate an old backup marker.
Observe: backup watchdog alerts Gotify.
Repair: run backup or restore the marker.
Note: alert path and delay.

## WireGuard link

Break: only with console access, stop the tunnel briefly.
Observe: public HTTP fails and make tunnel shows the issue.
Repair: restart wg-quick.
Note: user impact and recovery command.

## VPS Caddy bad config

Break: test a bad site file.
Observe: Caddy validation blocks reload.
Repair: fix the file and run make vps.
Note: what the validation caught.

## restore drill

Break: nothing in production.
Restore: one small DB dump or state file to a temp path.
Verify: file readable or DB integrity ok.
Note: RTO, RPO, and exact commands.

## incident 2026-09-20: jellyfin disk full, then green glitch

Incident: chill-01 (VM 101) root disk filled to 100% mid-film (F1 4K remux,
family movie night); after recovery the next film (Ford v Ferrari 4K remux)
showed green glitch everywhere on the Tizen TV app.
Impact: film 1 stalled (ffmpeg exit 228, 0-byte HLS playlist/segments, 80x
SQLite Error 13, 1354x rollback cascade, resume not saving); container stayed
healthy, no data loss. Film 2 unwatchable with PGS subtitles (silent frame
corruption, encoder log clean at ~2x speed).
Detection: user report during playback. `docker logs` showed `No space left
on device` on ffmpeg log writes; `df` showed 100%/0 free; `du` found a 26G
single-session HLS cache + 42G docker images on the 80G root disk.
Thought process: the rollback/SQLite errors looked like DB corruption at
first, but `database or disk is full` + ffmpeg ENOSPC pointed at disk, not
the DB. For the green glitch, a clean encode log + `overlay_qsv` subtitle
burn-in stage in the ffmpeg chain pointed at silent filter corruption;
isolation proposed via subs-off toggle on the TV.
Repair (live, no pauses): builder prune (2.8G) + orphan-image removal only
(never running images, never the active session) -> 13G free, ENOSPC gone.
Post-film: encoding.xml set HEVC HW decode on, throttling on, segment
deletion on/keep 120s; jellyfin restarted clean (0 errors); h264_qsv encode
+ hevc_qsv decode smoke-tested on the real file. Decision qsv->vaapi pending:
same iHD driver/silicon (QSV on Linux wraps VAAPI), same speed/quality, and
overlay_vaapi avoids the green-frame bug; UHD 630 has no QSV-only features
worth keeping.
Repair time: ~1h alongside playback; tuning ~15 min post-film.
Prevention: jellyfin-cache moved to /mnt/fast/jellyfin-cache in git
2026-09-21; still add >85% / Gotify alert and weekly builder/image prune.
Lesson: check disk before blaming the database; filter-stage corruption logs
nothing, so isolate with client-side toggles first.

## lesson 2026-09-21: host-side deletes on virtiofs shares don't free space

Context: cleared /mnt/archive on malice (media/ + downloads/, ~228G).
`rm` exited clean and `du` showed 32K, but `df` still showed 228G used
while `df -i` showed inodes free: unlinked-but-open files.
Detect: compare `df -h` vs `du -sh` on the share; confirm with `df -i`.
List holders with `lsof -n | grep '(deleted)' | grep -v memfd` — grep
`(deleted)` broadly, not the share path: virtiofsd fd links display
relative to the share (`/media/...`), so `grep archive` misses them,
and so does `find /proc/*/fd -lname '/mnt/archive/*'`.
Repair (zero downtime, no reboot): the guest owns the references, so
release from the guest via malice:
`qm guest exec <VMID> -- bash -c "sync; echo 2 > /proc/sys/vm/drop_caches"`.
`sync` first (only clean caches are dropped); `2` drops slab
(dentries/inodes), which is what triggers the FUSE release (`1` is
pagecache only and won't do it). Re-check `df` twice, ~10-30s apart:
block accounting lags (observed a transient 79G before settling to 2M).
Escalate: if space stays held, a guest process has files actively open —
find it with guest-side `lsof`/`fuser` (usually the torrent client
seeding retired paths) and stop that workload first. Last resort is a
full VM stop/start (restarts host virtiofsd workers; guest reboot alone
keeps the old virtiofsd).
Prevention: delete shared-tree data from the guest side when possible,
or stop consumers (pause/remove dead torrents) before host-side `rm`.
After any storage migration, `drop_caches` once and verify `df` ~= `du`
before declaring space reclaimed.

## process 2026-09-21: storage role swap (sdb -> vault/vzdump, sda -> backup/restic)

Capacity forced it: /mnt/primary is 504G and growing, so a restic repo
could never fit on the 466G disk; the 1TB holds it with headroom, while
vzdump generations (~20G each) fit the 466G for many rotations.
Rename a host mountpoint (here /mnt/archive -> /mnt/vault): only the
path moves, never the store id or mapping name. Touch fstab (UUID line,
keep a copy under /root), storage.cfg (`data` path), and
mapping/directory.cfg (mapping path). The mapping-path change needs a
full VM stop/start for every guest using the share (here only 101);
a guest reboot alone keeps the old virtiofsd. The guest-side mountpoint
may keep the old name (tag unchanged, still mounts) — rename it with
the next deploy instead of a second bounce. Delete any skeleton left
under the old path after unmounting, or silent root-disk writes follow.
Prove redundancy before deleting a stale mirror: build sorted file
lists on both sides (`find . -type f | sort`) and `comm -23` them —
here all 26,980 mirror files existed in live primary (only live runtime
logs differed). Spot-md5 overlapping pairs; differing sizes across
releases (Backrooms 2.7G vs 16.9G) mean upgrades, not loss.
Move flagged keeps with `cp -a` (preserves key perms), verify by md5 +
`diff -r`, then delete sources. API-first for guest disks: `pct destroy`
for dead containers, `pct set <id> -delete unused<N>` for detached disks
(Proxmox removes the raws itself); never `rm` a live rootfs.
Expect `df` to lag `du` after big deletes on shared trees — see the
virtiofs lesson above; guest `drop_caches` frees it with no reboot.
Wire the dump target by adding `backup` to the store content
(`pvesm set <store> --content ...`); Proxmox manages `<path>/dump/`
itself. Proof-run a stopped small guest first, then create the schedule
via `pvesh create /cluster/backup` (here: all guests, snapshot, zstd,
Sun 03:30, keep-last 8). Open after this run: chill-01 cannot see the
1TB, so restic wiring (new virtiofs share or host-side restic) plus
`restic init` belong to the backups phase.

## incident note

Incident:
Impact:
Detection:
Repair:
Repair time:
Prevention:
