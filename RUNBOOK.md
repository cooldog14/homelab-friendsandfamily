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
