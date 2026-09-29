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
- Repair: run backup; restore the marker only after a real success.
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

## drill 2026-09-29: restore-test ok

- Proof: snapshot 6cd039f7 (2026-09-29 04:16 UTC) restored to a temp path;
  immich/paperless dumps, kavita/gotify/beszel DBs (integrity ok),
  homelab.env, wg0.conf, VPS Caddy/nftables, and /mnt/data/photos all present.
- Repeat quarterly.
