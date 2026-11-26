# Operations — November 2–9, 2026

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## incident 2026-11-02: power cut, then chill egress dead from stale router ARP

- Symptom: every public vhost returned 502; malice, chill-01 and the LAN were
  unreachable. Cause: house power cut, malice down since ~2026-11-01 18:22Z
  (VPS up, Caddy answering, WireGuard and Tailscale peers gone).
- Recovery after power: malice booted 10:12Z, VM 101 and all 37 containers
  came up, VM 103 running. Checked: no failed units, all six host disks
  0 reallocated / 0 pending sectors, no ext4 errors, restic backup ran at
  10:15Z (prune finished clean), backup watchdog 48h window fine,
  Immich/Paperless postgres accepting, Sunday vzdump from 11-01 03:30
  present on vault, public-check exit 0 after the fix below.
- Second fault: chill-01 had DNS and a live `wg0` handshake but no internet
  and no WG data path (`public-check` FAIL 000 on every host). The router
  still mapped `192.168.1.28` to a dead MAC (`da:f6:59:14:fb:40` instead of
  `bc:24:11:f3:94:93`) and dropped replies addressed to it; tcpdump on malice
  `vmbr0` showed `1.1.1.1 > 192.168.1.28` replies with dst MAC `da:f6:...`.
  GARP from chill (request and reply form, broadcast and unicast to the
  router) did not refresh it -- treat the router entry as static/pinned.
- Workaround (live): chill egress relays via malice, which masquerades on
  `vmbr0`, so replies come back to malice's MAC and are forwarded.
  `qm set 101 --ipconfig0 ip=192.168.1.28/24,gw=192.168.1.2`.
  `/etc/netplan/99-homelab-relay.yaml` was deleted: it never won (metric 50
  lost to cloud-init's metric-0 default via `.1`), and a policy-route version
  hijacked the WG/LAN paths, so the relay has to be the VM's only default.
- Undo once the router ARP entry is cleared on-site (reboot router or delete
  the static entry): `qm set 101 --ipconfig0 ip=192.168.1.28/24,gw=192.168.1.1`,
  then `netplan apply` in the guest. Verify `ping 1.1.1.1` and
  `curl https://files.malice.biz` from chill, and public-check exit 0.
- Note: chill is a VM on malice, so relaying through malice adds no failure
  mode beyond malice itself; the lab was already down when malice was.
- Follow-up 2026-11-02 (Livebox rebooted): the mapping survived the reboot.
  A raw ARP probe from malice (`who-has 192.168.1.28`) is answered only by
  chill (`bc:24:11:f3:94:93`), yet the router still sends `.28` traffic to
  `da:f6:59:14:fb:40` -- so it is a persistent device record (a former
  randomized-MAC phone/laptop), not cached ARP. The router also refuses a
  static lease on `.28` as "already in use" and refuses `.2` because it is
  outside the DHCP pool. Relay stays until that record is deleted in the
  Livebox device list, or chill is renumbered.
- Resolution 2026-11-02: the record was a phone, `A35-de-Dimitri`
  (`DA:F6:59:14:FB:40`, randomized Wi-Fi MAC) that grabbed `.28` from DHCP
  during the power cut; it was deleted from the Livebox history page
  ("Supprimer ..."). The router still answered `.28` to that MAC afterwards,
  so chill-01 was renumbered out of the DHCP pool: `ipconfig0
  ip=192.168.1.200/24,gw=192.168.1.1`, guest netplan regenerated, Jellyfin LAN
  bind -> `192.168.1.200:8096` in `stacks/media/docker-compose.yml`, relay
  route removed. Verified: direct egress, WG handshake + data (VPS backend
  307), 37 containers, Jellyfin LAN 302, public check exit 0.
  The Livebox DHCP pool is `.10-.150`; `.28` is still poisoned inside it, so a
  further router reboot is worth doing and `.28` must not be reused.
  Router API notes: SoftAtHome WS4 at `POST /ws`
  (`application/x-sah-ws-4-call+json`), login via
  `sah.Device.Information.createContext` with `Authorization: X-Sah-Login`,
  then `Authorization: X-Sah <ctx>` + `X-Context: <ctx>`; `Devices`,
  `DHCPv4.Server` and `TopologyDiagnostics` are ACL-denied to that context,
  so the GUI (or `NeMo.Intf.lan.getMIBs`) is the only way to read/modify them.
  Device records can be removed from
  `/internal/devicesHistory/index.html` ("Supprimer ...").
- Open follow-ups from this incident:
  - Point the TVs' Jellyfin bookmarks at `http://192.168.1.200:8096`; the
    `192.168.1.28:8096` bind no longer exists.
  - Reboot the Livebox once more when convenient to try to flush the `.28`
    mapping, and never assign a lab host `.28` again. `.28` is inside the
    DHCP pool (`.10-.150`), so any device the router hands it to will lose
    inbound replies (outbound works, return traffic goes to the dead MAC).
  - The live DHCP lease list should only carry `Device-22 -> .53`; the dead
    guest leases (`.48 .118 .36 .37 .27`) and the mis-typed `.50`/`.88`
    reservations were removed on 2026-11-02.

## maintenance 2026-11-02: sdc retired, takeover made live, host upgraded

- Impact: brief `/mnt/data` I/O outage on chill-01 (~10 min) during the
  sdc offlining — guest 101 was still on `pve1-primary`, not the
  takeover bind as docs assumed. Full recovery, zero data loss.
  Post-reboot `homelab-public-check` green (13 vhosts + 4 TCP) after
  ~2 min container warmup (mg/paperless/photos 502 + MC TCP fail
  immediately post-boot, same as the Sep 30 pattern).
- Cause (docs vs live): TODO/RUNBOOK said `/mnt/data` was the takeover
  bind since Oct 19. Live guest fstab still had
  `pve1-primary /mnt/data virtiofs` — the Oct 19 "reboot-proofed" edit
  never landed in the guest (backup `/tmp/fstab.bak-20261019-rebind`
  gone with tmpfs). The 2026-10-26 "takeover newer on every path"
  verification compared trees without noticing the guest wasn't ON the
  takeover. Offlining sdc broke the live virtiofs an hour later.
- Repair: SCSI rescan re-attached sdc as `sdg`, mounted ro, rsync
  `--update` salvaged newest files to the takeover tree (minecraft
  world/config + logs; 0 remaining after pass 2), then guest cutover:
  `umount -l /mnt/data` + `mount --rbind` takeover, fstab rewritten to
  the bind (generator verified `What=takeover`), all 37 containers
  restarted, sdc re-offlined. Host music bind re-pointed:
  takeover `media/music` (301G) ro over `/mnt/pool/media/music`
  (fstab-persisted); `/mnt/bulk/media/music` follows via the pool bind.
- Host work (same window): sdc retired (NFS dropped, debian-01
  automount stopped + mountpoint removed, fstab commented, `virtiofs0`
  deleted, device offlined — reappears as `sdc` each boot until
  physically pulled, re-offline or ignore); nft `ip nat` flushed;
  stale `.48/.79/.118` + `10.30` iptables + tailnet DNAT deleted;
  `arr-routing` emptied; `iptables-restore.service` disabled;
  nfs-server/rpcbind(+socket) disabled; HA lrm/crm disabled;
  `PermitRootLogin prohibit-password`; 6.17.2 kernel purged;
  orphan `pre-trim-20260916` snapshot config removed; both failing
  backup crons deleted; `hermes` user/token/ACL/system-user/`hermesctl`
  removed; `firewall=1` dropped from both NICs; OpenTofu tokens given
  +90d expiry (unused 90d — delete if still idle); `swappiness=10`;
  sdd long self-test + smartd schedule; `newaliases`;
  `malice-restic-backup` git-owned + `OnFailure=notify@` live;
  `/etc/homelab.env` copied from guest (0600, host switched to
  `gotify.h` tailnet URL — public `gotify.malice.biz` has no VPS route
  and TLS-errors); non-final dumps + ISO + skeletons removed (~4.2G).
- Upgrade: both guests sata→scsi (`virtio-scsi-single`, `iothread=1`,
  `ssd=1`, `boot order=scsi0`; PARTUUID fstab so no guest edits) —
  103 boot-tested on `virtio-scsi-pci` first, then both switched to
  `-single` for working iothreads. `apt full-upgrade` → pve-manager
  9.2.25, kernel 7.0.14-26, qemu-server 9.2.14; reboot clean
  (75s, both guests `onboot`, scsi boots fine).
- Prevent: never trust "bind is live" from docs — `mount | grep
  /mnt/data` on the GUEST is the proof before touching the old disk.
  Takeover/bind claims must be re-verified live, not carried forward.
  `/tmp` backups don't survive reboot — keep fstab/config backups in
  git or `/root`, not `/tmp`.
- Physical TODO: pull sdc + sda on-site per the disk-swap plan (sdc
  still in slot, kernel-offlined). TOTP for root@pam still open
  (needs interactive QR enrollment via the PVE web UI).

## maintenance 2026-11-03: audit backlog deployed (Neko block, auth, VPS, upgrades)

- Rebase: remote had 3 new commits (Oct 31 VPS/SSH/atomic-backup batch,
  Nov 2 `.28→.200` renumber + `/mnt/data`→pve1-primary revert). Kept
  local as live truth (sdc retired, takeover live), cherry-picked
  remote's fixes (VPS key-only SSH, atomic VPS pull, `.200` renumber,
  15-min check, `/12` Beszel UFW). Critical: remote's
  `sed -i '\|/mnt/data none bind|d'` would have destroyed the live
  takeover on next `make host` — removed, guard kept + full-line match.
- Neko lateral: `DOCKER-USER` 70 rules (pre-DNAT host IPs + post-DNAT
  cross-bridge `-o br-*`, edge exempt), 9090→`172.18.0.0/16` (edge
  pinned). Lesson: pre-DNAT-only misses published ports (DNAT rewrites
  dst first) — `:5030` stayed 200 until the `-o` rules. Verified all
  5 probes timeout, edge+public intact.
- cap_drop fallout (audit predicted): neko needed CHOWN/SETUID/SETGID
  (supervisord socket), mumble +CHOWN/DAC_OVERRIDE/SETUID/SETGID
  (entrypoint chown + write as 10000), jellyseerr +DAC_OVERRIDE/CHOWN
  (root over 1000-owned bind). Gotify/Beszel/Screego/Feishin fine.
- Auth: slskd→401 (random creds in live `.env`, never printed),
  wrtag→401 (`basic-auth-from-api-key`; `enabled` invalid per README),
  `:8191` unpublished (Prowlarr `localhost:8191` 200), qbit whitelist
  emptied + password rotated + arr DBs updated (`authentication
  succeeded` in logs; localhost bypass is qbit-design, non-exploitable
  post-DOCKER-USER), arr `Enabled` + API keys verified via same-stack
  DNS, Bazarr forms auth + `1.6.2`.
- VPS: `make vps` (reboot `01:30`, stirling already private),
  `format filter` redaction (query `p/t/s/api_key/ApiKey/token`,
  4 headers; multi-`delete` per field rejected — one `delete` line per
  header path required); probe `api_key=PROBE`→`api_key=REDACTED`.
  Old `access-*.gz` deleted, goaccess timer retired + HTML removed.
- Upgrades: Immich `v3.3.5`, Filebrowser `2.0.2` (config
  `server.port`→`http.*` migrated, DBs in `/root`), Jellyfin `12.3`
  (config tarball `/root`, no `12.3.0` tag exists), Seerr `v3.5.1`
  (`init`, chown), Neko `3.2.0`. All 37 Up, public-check 17/17 green.
- State-only changes (never in git, record here): qbit password
  (random, in sonarr/radarr DBs), Bazarr `admin` forms password
  (random), arr `AuthenticationRequired=Enabled`, slskd web creds
  (live `.env`). Temp secrets shredded; DB/config backups in `/root`.
- OPEN: rotate Navidrome/Jellyfin creds (were in deleted logs);
  `trustProxyHeaders` for Filebrowser 2.x behind Caddy (unverified);
  Jellyfin full rescan check; move admin ports off 10.44.0.2; Immich
  PG 14 EOL 2026-11-12 (plan dump+restore).

## maintenance 2026-11-09: IaC cutover (Ansible + OpenTofu) and Prometheus/Grafana observability

- What changed: `bootstrap.sh` and `vps/bootstrap.sh` deleted — host state
  is Ansible-only (`ansible/chill.yml`, `ansible/vps.yml`, roles under
  `ansible/roles/`: `chill_base`, `chill_docker`, `chill_storage`,
  `chill_units`, `chill_firewall`, `vps_edge`). OpenTofu (`tofu/`)
  codifies VM 101 import-only: `prevent_destroy`, plan-only policy,
  never apply; token in `~/.config/homelab/tofu.env` (outside the repo).
- New observability services in the `observability` stack: gotify,
  beszel, beszel-agent, prometheus, alertmanager,
  alertmanager-gotify-bridge, node-exporter, cadvisor (privileged,
  documented exception), blackbox-exporter, grafana (~45 containers
  total). Prometheus is published only on `127.0.0.1:9091` because
  Cockpit owns `*:9090`; Grafana is private-only via
  `grafana.h.malice.biz` -> `10.44.0.2:3000`.
- `host/metrics.sh` + `homelab-metrics.timer` export backup age and
  WireGuard handshake age as node_exporter textfile metrics, so a
  stalled collector shows up as a missing series. `host/firewall-neko.sh`
  was extracted from the deleted bootstrap script. New `make
  edge-reload` target: Caddy does not reload on route edits, and
  `compose up -d` on an unchanged file is a no-op.
- Verification actually performed: double playbook runs on both hosts
  report `changed=0`; all services active; public-check 13 HTTP + 4 TCP
  green; `promtool` config/rules, `amtool check-config` and blackbox
  config checks pass; alert test `HostDown` delivered to Gotify then
  resolved; `make restore-test` 15 s; `tofu plan -detailed-exitcode` = 0.
- Rollback: re-run the playbooks from a known-good commit. Caddy and
  VPS configs are still on disk at `/etc/caddy` and `/etc/nftables.d`.
  The VM itself is never applied by tofu — `tofu state` can be
  discarded with `tofu state rm` if needed.
- OpenTofu caveat: `smbios`, `vga`, cloud-init `user_account` and
  provider-only flags are in `lifecycle.ignore_changes` because the
  provider cannot read them back on an imported VM; they are
  documentation-only and drift there is invisible to `plan`.

## maintenance 2026-11-09: retire Beszel (Prometheus + cAdvisor replace it)

- What changed: Beszel (`beszel` hub + `beszel-agent`) is gone from
  `stacks/observability/docker-compose.yml`. Prometheus + cAdvisor +
  Grafana already cover host and per-container metrics with real alert
  rules, so the hub, its agent, the `:8090` private vhost and the
  host-network agent on `:45876` were redundant attack surface and a
  second place for monitoring to go stale (it went blind for 7 days on
  2026-10-30). Gotify stays: it is the sink for Alertmanager,
  `notify@.service` and the backup units.
- Code removed: both compose services (including the `beszel-agent`
  host-network exception comment, `extra_hosts` and the
  `docker.sock` mount), `BESZEL_KEY` from `.env.example`, the
  `beszel.db` dump line in `host/backup.sh`, the `@beszel` matcher +
  `reverse_proxy` in `stacks/edge/Caddyfile`, the Beszel link on
  `home.h`, the two Beszel UFW allows in `chill_firewall` (replaced by
  two idempotent `delete: true` cleanups), and the
  `stacks/(comms|observability)` host-network exception in
  `make check` (now `stacks/comms` only).
- Live cleanup on chill-01: `make deploy` removed
  `observability-beszel-1` and `observability-beszel-agent-1`
  (`--remove-orphans`), `make edge-reload` restarted Caddy so the vhost
  now falls through to the "unknown private service" 404. The
  `BESZEL_KEY` line was deleted in place from the host `.env`
  (mode kept `600`), `state/beszel` was renamed to
  `state/beszel.removed-20261109` (delete it once the short history is
  not needed), and the leftover UFW `45876` rules were deleted by the
  first `make host` (`172.16.0.0/12 -> 45876` and
  `172.20.0.0/16 -> 172.17.0.1:45876` both reported `changed`). The
  Gotify app `beszel` was left in place: it costs nothing and its
  token is not referenced by any config now.
- Verification actually performed: `docker compose -p observability ps`
  shows the 8 remaining services Up and no beszel container; `ss -lntp`
  has no `45876` listener; `http://10.44.0.2:8090` refuses
  (`000`/connection failure); `https://beszel.h.malice.biz` returns
  `404`; Prometheus `/api/v1/targets?state=any` = 24 targets, 0 down,
  `probe_success{job="blackbox-http"}` 13/13; Grafana
  `/api/dashboards/uid/homelab-overview` served the dashboard (10
  panels after the same-day container-table refactor: host stats,
  probes and a single `Conteneurs` table with per-container memory,
  CPU, uptime and restarts);
  `homelab-public-check` green (13 HTTP + 4 TCP); `make host` second
  run `changed=0 failed=0`, `make vps` `changed=0`; `make check` steps
  (compose config, Caddy adapt/validate, promtool/amtool/blackbox,
  shellcheck, dashboard JSON) pass, `make ansible-check`,
  `ansible-lint ansible` and `make tofu-check` pass.
- Tradeoff: Prometheus keeps `--storage.tsdb.retention.time=15d` (1 GB
  `mem_limit`); Beszel kept per-container history indefinitely. If long
  history matters, raise the retention flag (disk under
  `state/prometheus` is the only cost) instead of reintroducing a
  second metrics store.
- Rollback: re-add the services from git history, e.g.
  `git show 1a8913c492d2058d2123b73e4951de9640f37c11:stacks/observability/docker-compose.yml`
  for the pre-removal compose file, restore `BESZEL_KEY` in `.env`,
  move `state/beszel.removed-20261109` back to `state/beszel`, revert
  the Caddyfile/backup role change, then `make deploy && make
  edge-reload && make host`.
- Grafana admin password: `GF_SECURITY_ADMIN_PASSWORD` (from
  `GRAFANA_ADMIN_PASSWORD` in the stack `.env`) only **seeds** the
  `admin` user on first init. Grafana hashes it into
  `state/grafana/grafana.db` and never re-reads the env var, so editing
  `.env` alone does not change the login. The `.env` value is the
  documented login; to reset it to that value use
  `sudo sh -c '. /opt/stacks/observability/.env; docker exec
  observability-grafana-1 grafana cli --homepath /usr/share/grafana
  admin reset-admin-password "$GRAFANA_ADMIN_PASSWORD"'` (never echo
  the value). Verified 2026-11-09: after the CLI reset, `POST /login`
  with `admin` + the `.env` password returns `200`, `/api/user` with
  the returned cookie returns `200`, and
  `/api/dashboards/uid/homelab-overview` returns `200`.

