# runbook

Break one thing at a time.
Use a quiet window.
Do not test by deleting data.

## public service down

- Drill: stop one harmless public service.
- Detect: `homelab-public-check` fails; Gotify alerts; systemd logs show failure.
- Repair: restart the stack with Docker Compose.
- Record: detection time and repair time.

## private caddy bad config

- Drill: test a bad edge Caddy config.
- Detect: Caddy validation fails before restart.
- Repair: restore the valid config.
- Record: whether validation blocked the outage.

## backup stale

- Drill: simulate an old backup marker.
- Detect: `homelab-backup-watchdog` alerts Gotify.
- Repair: run backup or restore the marker.
- Record: alert path and delay.

## WireGuard link

- Drill: only with console access, stop the tunnel briefly.
- Detect: public HTTP fails; `ssh vps-ingress 'sudo wg show chill0'` shows the issue.
- Repair: `sudo systemctl restart wg-quick@chill0` on the broken side.
- Record: user impact and recovery command.

## VPS Caddy bad config

- Drill: test a bad site file.
- Detect: Caddy validation blocks reload.
- Repair: fix the git-owned site file and run `make vps`.
- Record: what validation caught.

## incident 2026-09-20: jellyfin disk full, then green glitch

Impact: playback stalled from root-disk ENOSPC; later PGS subtitle burn-in
showed green frames. No data loss.

Detect:
- `docker logs` shows ffmpeg `No space left on device` / ENOSPC.
- `df -h` shows root full; `du -sh` finds HLS cache and Docker image use.
- Clean encode logs plus subtitle burn-in in the ffmpeg chain points at filter
  corruption; confirm with client-side subtitle toggles.

Repair:
- Free safe space only: builder prune + orphan-image removal. Never remove
  running images or the active HLS session.
- Move Jellyfin cache to `/mnt/fast/jellyfin-cache`.
- Keep Jellyfin HEVC HW decode on, throttling on, segment deletion on, keep
  120s.
- Use VAAPI overlay on UHD 630; it avoids the QSV green-frame path.

Prevent:
- Verify weekly Docker prune, Beszel >85% disk Gotify alert, and real playback
  using `/mnt/fast/jellyfin-cache`.
- Check disk before blaming the database; isolate filter/client bugs with
  client-side toggles first.

## lesson 2026-09-21: host-side deletes on virtiofs shares don't free space

Detect:
- Compare `df -h` vs `du -sh`; free inodes with held blocks means unlinked
  open files.
- List holders with `lsof -n | grep '(deleted)' | grep -v memfd`. Grep
  `(deleted)` broadly because virtiofs fd links can be share-relative.

Repair:
- From malice, release clean guest caches:
  `qm guest exec <VMID> -- bash -c "sync; echo 2 > /proc/sys/vm/drop_caches"`
- Re-check `df` twice, 10-30s apart.
- If space stays held, find guest holders with `lsof`/`fuser` and stop that
  workload. Last resort: full VM stop/start.

Prevent:
- Delete shared-tree data from the guest side when possible.
- Stop consumers before host-side `rm`.
- After storage migrations, drop caches once and verify `df` ~= `du`.

## process 2026-09-21: storage role swap (sdb -> vault/vzdump, sda -> backup/restic)

- Local restic belongs on `/mnt/backup`; vzdump belongs on `/mnt/vault`.
- Rename host mountpoints by changing `fstab`, `storage.cfg`, and
  `mapping/directory.cfg`; path changes need a full stop/start for guests using
  the share.
- Keep store IDs, virtiofs tags, and guest mountpoints stable unless a deploy
  changes them.
- Delete old mountpoint skeletons after unmounting to avoid silent root-disk
  writes.
- Before deleting stale mirrors, compare sorted file lists:
  `find . -type f | sort` and `comm -23`; spot-check overlaps with md5.
- Move keeps with `cp -a`, verify with md5 + `diff -r`, then delete sources.
- For guest disks, use `pct destroy` or `pct set <id> -delete unused<N>`;
  never `rm` a live rootfs.
- Expect `df` to lag `du` after shared-tree deletes; use the virtiofs cache
  release above.
- Wire dump storage with `pvesm set <store> --content ...`; Proxmox manages
  `<path>/dump/`.
- Proof-run a stopped small guest, then create the schedule with
  `pvesh create /cluster/backup`.

## lesson 2026-09-28: local restic and cloud-first backup cutover

Failure: `homelab-backup` skipped offsite backup when `/mnt/backup` was in
`RequiresMountsFor` before the guest had that mount.

Detect:
- Failed timer with no useful script output.
- Stale `last-ok` marker.

Repair:
- Run cloud backup first.
- Check `/mnt/backup` inside the local section so missing local storage fails
  after offsite completes.
- Once `pve1-backup -> /mnt/backup` is mounted, restore the mount requirement,
  initialize `/mnt/backup/restic`, and run the local backup.

Troubleshoot:
- Manual restic churn from a missing latest parent: stop it, clear the stale
  lock, rerun with the known parent snapshot.
- S3 503s/hangs with a fresh verified cloud snapshot: stop poking and let the
  timer retry.
- Full VM stop/start for virtiofs can regenerate cloud-init SSH host keys;
  verify the new fingerprint through `qm guest exec` before trusting SSH.

## lesson 2026-09-28: app credentials are not all env vars

- Gotify: `.env` default password only seeds initial admin; reset app DB/API
  state after backing it up if the in-app password drifted.
- Navidrome 0.63: passwords are encrypted with the app key; use
  `navidrome user edit --user <name> --set-password`.
- Compose: `$` inside `.env` values is expanded and can truncate passwords.
  For passwords containing `$`, mount a host-only `0600` file and use the
  app's `*_PASSWORD_FILE` support.

## lesson 2026-09-28: storage migrations leave stale app state

- qBittorrent can keep `.fastresume` paths and sizes from retired storage
  after content moves to `/pool`. Quarantine stale `.torrent`/`.fastresume`
  first; do not delete media to satisfy torrent state.
- Jellyfin: prove cache location with real playback after deploy before
  deleting old cache directories. Only remove empty old paths with no active
  references.

## lesson 2026-09-28: public app rollout checks

- Before exposing a private app publicly: confirm native auth works off-tailnet,
  add only the exact public Caddy host, run `make check`, run `make vps`, and
  verify `homelab-public-check`.
- Minecraft Paper 26.2 needs Java 25; Java 21 boot-loops. Keep RCON passwords
  only in the live stack `.env`, never in git. Run Chunky pregen before launch,
  outside backup windows.
