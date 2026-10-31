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
