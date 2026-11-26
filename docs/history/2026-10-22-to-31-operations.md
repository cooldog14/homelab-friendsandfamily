# Operations — October 22–31, 2026

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## lesson 2026-10-22: suwayomi reader blank pages were 5-minute JWT expiry, not downloads

- Impact: reader showed blank/missing pages on downloaded manga; ~11% of
  image loads 401'd (311/2828 over Oct 21-22) for one Firefox client.
  Downloads on disk were intact (valid JPEGs, zero 0-byte files).
- Cause: `server.jwtTokenExpiry = "5m"` (default) with `AUTH_MODE:
  ui_login`. Access tokens expire mid-chapter; the WebUI image path
  retries with the stale token, so the same page URL flips 200 -> 401 ->
  200 seconds apart while GraphQL calls keep succeeding. Feels like
  "downloaded but won't render".
- Detect: VPS `access.log` filtered to `mg.`: bursts of 401 on
  `/api/v1/manga/*/chapter/*/page/*` + `/thumbnail` interleaved with 200s
  on the same URLs; app `application.log` `UnauthorizedException` in
  `MangaController` (`handler$11` = page images, `thumbnail`).
- Repair: stop suwayomi, set `server.jwtTokenExpiry = "7d"` in
  `/mnt/data/apps/suwayomi/server.conf` (state-only, never in git;
  server rewrites the file on shutdown so stop-first is required),
  restart. Users re-login once to mint a 7d token. Refresh expiry stays
  60d; security tradeoff is a longer-lived bearer on a single-user box.
- Prevent: never leave `jwtTokenExpiry` at 5m on a ui_login reader box;
  `server.conf` TTLs are invisible to `make deploy` — audit them after
  any Suwayomi rebuild.

## incident 2026-10-22: bursty transit loss to VPS hangs large downloads (mg blank images)

- Impact: public `mg` (and jellyfin, proven by interleaved test) large
  responses randomly stall mid-stream (150-300KB then hang, 20-245s for
  400KB-1.3MB). Suwayomi reader shows blank pages with no spinner: its
  images are `Transfer-Encoding: chunked` with no `Content-Length` and no
  `accept-ranges`, so a stalled stream never errors, never resumes, and
  the reader waits silently. Small responses (GraphQL, 304s) unaffected.
- Cause: bursty sustained-TCP loss on the client<->VPS transit path, NOT
  the homelab. Proven: raw `scp` 1MB VPS->workstation 1.7s/1.5s/218s (no
  Caddy/tunnel/app); VPS->Hetzner 100MB in 4.4s (VPS uplink fine);
  VPS->backend 1.3MB in 0.25s 5/5; backend 2ms; ICMP 0% loss idle, under
  load, and MTR end-to-end. ICMP-clean + TCP-bulk-shredded = policer or
  shaper biting sustained flows, invisible to ping. Two client networks
  (Magenta cable `83.64.155.206`, Lebara FR 4G `141.98.208.x`) affected;
  phone pages that completed were 200 in 0.1-0.3s, blanks were hung rest.
- Detect: `curl` same 1.3MB asset on `mg` alternates 0.3s / 20s+ timeout;
  interleaved mg-vs-jellyfin large downloads stall on BOTH (vhost
  independent); VPS `ss -ti :443` shows mass `bytes_retrans` +
  `delivery_rate` kbps during stall; `access.log` shows 200s with huge
  durations, no 4xx/5xx.
- Mitigation: tailnet bypass. Private `suwayomi.h.malice.biz` over
  Tailscale: 10/10 large files 0.4s (1x 3s, delivered). Phone `pixel-8`
  already in tailnet (reconnect after 31d offline). Public path left as
  is — fault is upstream transit, nothing to fix in git.
- Prevent: when "slow" hits all vhosts at once with clean ICMP, test raw
  `scp` VPS->client before touching apps; if scp stalls, it's transit.
  Suwayomi chunked-no-length responses amplify any loss into blank
  pages — consider Caddy `reverse_proxy ... flush_interval -1`
  (buffering) for mg if transit stays lossy, trading TTFB for resumeable
  Content-Length responses.

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

## maintenance 2026-10-31: audit batch (alerts, deploy safety, Stirling, storage)

- Change: public check runs every 15 minutes (was daily); `notify@.service`
  logs delivery failures to the journal instead of failing silently on an
  empty `ALERT_URL`; weekly prune uses `prune -f` so images of stopped
  containers survive; the backup VPS pull now downloads to a temp dir and
  swaps only on success (a failed scp no longer wipes the old WireGuard
  copy); `shellcheck` ships in `bootstrap.sh` and `make check` falls back to
  the container image on a dev box without it.
- Change: Stirling is private-only. Removed `stirling.malice.biz` from
  `vps/sites/chill.caddy`; `stirling.h.malice.biz` answers 401 over
  Tailscale.
- Change: `/mnt/data` moved off the 4 TB bulk disk. It was a bind of
  `/mnt/pool/takeover-primary/r1/mnt/data`; it is now the `pve1-primary`
  virtiofs share (2 TB, backed up).
  - Steps: stop all stacks; rescue primary-only files to
    `/root/primary-only-20261031` (130 files, 156M); `rsync -aHAX
    --numeric-ids --delete` takeover tree -> `/mnt/primary` (2,374 files,
    104.5 GB, 177 deletions); compare `find -type f | wc -l` (32,956 both)
    and `du -sb` (590,584,670,668 bytes both); remove the bind line from
    guest `/etc/fstab`; umount/mount `/mnt/data`; start stacks.
  - Verify: `findmnt` shows `pve1-primary`; write test as deploy OK;
    public-check exit 0 (17 ok, one fewer because Stirling left the public
    set); 37 containers up, none unhealthy; Immich 200, Paperless 302,
    Jellyfin 302, Navidrome 302, fiesta 200, Stirling 401, slskd 200,
    wrtag 200, Minecraft port open, gluetun egress still `194.58.47.21`.
- Lesson: `bootstrap.sh` appended `pve1-primary /mnt/data` *in addition to*
  the takeover bind line (its `grep -q "$tag"` matched a substring), so
  `mount -a` stacked the primary share over the live tree and app writes
  briefly landed on the stale Sep tree. Fixed: the ensure now matches the
  full fstab line, and the bootstrap deletes any `/mnt/data none bind` line
  first. Re-ran `make host`: one line, correct mount, containers untouched.
- Rollback: the takeover tree on bulk is untouched; re-add the bind line and
  remount to go back until the next verified restic backup.

