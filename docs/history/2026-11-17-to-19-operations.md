# Operations — November 17–19, 2026

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## maintenance 2026-11-17: isolation, edge, recovery, and monitoring hardening

- Impact: application containers were recreated during the deploy; private admin
  UIs were unavailable briefly while Caddy and Stirling restarted. The public
  checks stayed green after the normal two-minute warmup. One planned reboot of
  `chill-01` verified mount ordering and boot-time isolation.
- Isolation: added `homelab-firewall-neko.service`, enabled after Docker and
  re-applied by `make deploy`. Removed the broad `wg0` UFW allow, leaving only
  `10.44.0.1`. Added one scoped `DOCKER-USER` allow for Prometheus to scrape the
  hypervisor on Tailscale TCP/9100; 89 marker rules present after reboot.
- Admin network: added external `homelab-edge` bridge network. Private Caddy and
  the admin services now use it; Filebrowser, Stirling, Gotify, Radarr, Sonarr,
  Bazarr and wrtag have no host-published admin port. Quoting/qBittorrent/
  Prowlarr/slskd are bound only to Docker's `172.17.0.1` gateway and proxied by
  private Caddy via `host.docker.internal`. VPS probes to all admin ports fail.
- VPS: `vps/firewall.nft` now owns the effective input/forward table. Forwarding
  is DNAT-only plus `wg0 -> eth0`; broad `10.44.0.0/24` accepts and the stale
  `8088` rule were removed from `/etc/nftables.conf`. Applying the policy exposed
  missing P2P source NAT, repaired in `vps/nftables.conf` with
  `10.30.0.4 -> eth0 masquerade`. Gluetun recovered to healthy and reports the
  VPS public IP.
- Backup: database dumps are now atomic and failure-aware. PostgreSQL and
  Filebrowser failures preserve the previous dump; SQLite and Bolt snapshots are
  integrity-checked. Suwayomi is paused only for a tar snapshot, Minecraft is
  flushed, live PostgreSQL/model-cache data is excluded, and a non-zero exit
  after snapshots preserves `OnFailure`. Added weekly sampled-data checks for
  the hosted cloud/local repos and the malice repo. Unattended reboot moved to
  `02:30`.
- Observability: cAdvisor and Grafana limits are 1 GiB; OOM/kernel-OOM alerts
  exist. `prometheus-node-exporter` on malice listens only on its Tailscale
  address and is up in Prometheus. PVE has a `gotify` endpoint and the default
  matcher targets both `mail-to-root` and `gotify`; target test succeeded. The
  VPS heartbeat client checks public HTTP/TCP every five minutes and sends the
  configured external heartbeat only on success; an immediate delivery
  completed successfully. Its fail and recovery pings were accepted. A
  GitHub-hosted public probe runs every 10 minutes, opens an assigned outage
  issue on failure and closes it after recovery; both paths were tested.
- Deploy/storage: `/mnt/data` source is asserted by device/inode identity,
  Docker requires `/mnt/data /mnt/pool /mnt/fast`, deploy archives HEAD instead
  of the working tree, applies isolation after compose, and records
  `/opt/stacks/.deployed-commit`.
- Verification: `make host` second run `changed=0`; `make vps` second run
  `changed=0`; `make hypervisor` second run `changed=0`. `chill-01` rebooted
  cleanly with 42 containers running and zero unhealthy snapshots, 89 isolation
  rules restored, and the takeover bind verified. The VPS also rebooted cleanly:
  persisted firewall/NAT, SSH, Caddy, WireGuard, gluetun egress, public checks
  and the heartbeat timer all recovered; `nft -c` passes. Public check is 13 HTTP
  + 4 TCP green. All 16 private vhosts return 200/302/401. Backup succeeded
  with 21 SQLite dumps, 3 Bolt snapshots and a 1.3G Suwayomi archive. The
  expanded restore drill passed (40 paths, 1.63 GiB; cold 6m45s, warm 1m22s).
  A forced missing PostgreSQL container and missing SQLite source preserved
  old dumps and recorded failures. Hosted cloud/local and hypervisor 5% data
  checks both completed successfully.
- Remaining: physical removal of retired `sdc` and staged `sda` remains
  on-site.
- Rollback: restore the previous stack tree with a commit checkout, run
  `make host`, `make vps`, `make deploy`; validate any firewall rollback with
  `nft -c` before applying and never flush the ruleset.

## maintenance 2026-11-17: retention, edge enforcement, and PG18

- Impact: every stack was recreated, so public and private routes blipped for
  the usual warmup. The hypervisor rebooted for a kernel upgrade, taking all
  three guests down for the duration. Public check is 13 HTTP + 4 TCP green
  afterwards, all 16 private vhosts answer, and 42 containers are up with none
  unhealthy or restarting.
- Backup: retention is now the latest three snapshots per repository, enforced
  by `homelab-restic-retention` (`host/restic-retention.py`) after each
  snapshot. It refuses a snapshot whose path set is not the five current paths
  unless `--cleanup-legacy` is passed, so a future path edit fails the backup
  instead of deleting history. The 38 legacy-layout snapshots and the excess
  current-path snapshots were pruned: cloud 191 then 94 packs, local 57 packs.
  Both repositories hold exactly three current-path snapshots and pass
  `restic check`; the 5% sampled reads and the restore drill pass.
- Edge: Caddy 2.11.9 and CrowdSec 1.8.2 now come from Cloudsmith and
  packagecloud; the bouncer is 0.0.38 in nftables mode with `input` and
  `forward` hooks. Upgrading from CrowdSec 1.4 left `/etc/crowdsec` full of
  symlinks into hub content that was never downloaded, so no parser or scenario
  ran; the dangling links were pruned and the collection set (linux, sshd,
  base-http-scenarios, http-cve, caddy) reinstalled. `acquis.yaml` now reads
  only what the host has: sshd via journald and the redacted Caddy access log.
  Within a minute of the restart a real scanner drew five scenarios and a 4h
  ban. dpkg replaced the binary without restarting the engine, so the role now
  notifies a restart on package change; the same applied to the bouncer, which
  only created its forward chain after an explicit restart.
- Immich: PostgreSQL 14.19 → 18.4 through the `-upgrade` image, then the
  regular PG18 image. pg_upgrade dropped `vchord`, so it was recreated at 1.1.1
  and pgvector updated to 0.8.5 before the server started. Asset/album/user
  counts are unchanged (0/1/1); the photo library is empty in both the database
  and `/mnt/data/photos`. `state/immich/db/14.bak` stays until the next backup
  and restore drill pass. `immich-admin schema-check` still reports
  `user_metadata_audit` as missing although the function and its trigger exist.
- Containers: `no-new-privileges` and `cap_drop: [ALL]` on every service except
  the privileged cAdvisor. Capabilities were added back only where the image
  failed: redis (`SETUID/SETGID` for `setpriv`), Paperless and Stirling
  (`CHOWN/DAC_OVERRIDE/SETUID/SETGID` for s6 chown plus drop), gluetun
  (`NET_ADMIN`), Caddy (`NET_BIND_SERVICE`), both PostgreSQL servers and the
  LinuxServer images. Images: Paperless 3.5.0 (migrations applied), Gotify 3.1.1
  (migration ran, 1 user and 4 applications intact), Jellyfin 12.4, Seerr
  v3.5.2, Minecraft 2026.11.0-java25 (saves flushed first; world loaded,
  "Done (14.6s)"), slskd 0.26.2.
- Hypervisor: fresh vzdump of all guests (6.1G, 37G, 2.7G), PVE matcher set to
  `gotify` only, mail queue drained, then a full upgrade (pve-manager 9.2.28,
  qemu-server 9.2.15, 0 pending) and a reboot. All three guests came back and
  node exporter is up. Kernel `7.0.14-29-pve` is installed and GRUB's
  `/boot/grub/grub.cfg` lists it first, but the host still boots
  `7.0.14-26-pve`: the EFI system partition (`sde2`) is not mounted at
  `/boot/efi`, so `update-grub` cannot refresh the ESP menu and the firmware
  boots the previous entry. Left alone deliberately — a bootloader change with
  no console access is a worse risk than one point release behind. Prometheus
  now alerts on hypervisor memory below 10% and on any swap-in rate.
- Deploy: `make host`, `make vps` and `make hypervisor` second runs report
  `changed=0`.
- Rollback: previous image tags are in the commit before this one. The Immich
  path is `14.bak` plus the pre-upgrade dump at
  `/mnt/fast/dumps/immich-pg14-pre-upgrade.dump` (18 MB, `pg_restore --list`
  clean). Stack state was archived to
  `/mnt/fast/scratch/pre-upgrade-20261117T125357Z` before recreation.

## incident 2026-11-18: fake release payloads, partial packs, and indexer coverage

- Queue: 29 Sonarr records, not a mount/VPN fault. Four `importPending`
  were fake releases, not video: statusMessages showed `Invalid video
  file, unsupported extension: '.7z'`, `Caution: Found executable file
  with extension: '.exe'`, and `Caution: Found potentially dangerous file
  with extension: .zipx`. `file(1)` confirmed two 0.9-1.0G PE32+ Windows
  executables plus real 7z/ZIP archives, all from LimeTorrents/Nyaa.
  Torrents and data were deleted; none was executed on chill.
- Ten `importBlocked` S14 rows were one incomplete `MULTi` pack with
  E01-E09 only. Sonarr refuses a partial season and keeps the completed
  torrent queued; the library already had the nine files. The pack was
  removed; S14E10 is re-downloading as `Waiting for Big Mo 1080p AMZN
  WEB-DL DDP5.1 H.264-NTb` from the new Torrent Downloads indexer.
- Thirteen `importBlocked` S04 rows were one valid DVDrip pack with scene
  filenames `clue-sun401.avi`..`clue-sun413.avi`. With no `SxxExx`,
  Sonarr's `FullSeasonSpecification` treats each file as the whole season.
  The torrent was removed (data kept), files renamed to `S04E01..E13`,
  and ManualImport moved 13/13 into `/pool/tv`.
- S15E05 was a dead fake: qbit `stalledDL`, 0 complete peers, 97
  leechers. Sonarr only warns on stalled downloads, so the queue never
  clears. Replaced with `S15E05 PROPER 1080p HEVC x265-MeGusta` (387M);
  the first 1080p and 720p picks had dead or near-dead swarms.
- The four fake Traitors episodes were replaced with proper EZTV
  `1080p HDTV H264-DARKFLiX` releases and imported; S02 is now 10/10.
- Supply root cause: public-indexer quality, not Prowlarr/RSS wiring.
  Prowlarr grew from 10 to 16 indexers: Anime Tosho, ExtraTorrent.st,
  TorrentByte, Torrent Downloads, World-torrent, YTS. Cloudflare-protected
  ones need FlareSolverr, which Prowlarr already runs; its proxy is
  tag-gated (`flaresolverr`, tag 1), so the new indexers were tagged with
  it. The first sync attempts hit the indexer backoff (`429 ... disabled
  till 01:11Z`) and left stale `ApplicationIndexerMapping` rows pointing
  at Sonarr ids 29-31 that did not exist. Later syncs tried to UPDATE
  those ghosts and never ADDed the indexers. Deleting and re-adding
  ExtraTorrent.st, TorrentByte and Torrent Downloads cleared the
  mappings; Sonarr now has 15 indexers (the three new TV sources plus
  Anime Tosho/World-torrent). YTS is movies-only and stays in Radarr.
- Prevention: qbit `excluded_file_names` now blocks `.exe/.scr/.com/.bat/
  .cmd/.ps1/.vbs/.js/.jse/.wsf/.hta/.msi/.lnk/.reg`; Sonarr release
  profile `Reject archive wrappers` ignores `7z` and `zipx` titles.
  Completed/failed removal was already enabled; it cannot clear a
  *blocked import*, which is why the S04/S14 rows persisted for weeks.
- Exposure: the payloads sat in `/mnt/data/downloads`, the main
  Filebrowser root (`/mnt/data:/srv`), reachable only through the private
  admin instance; the public family instance mounts `/mnt/data/family`
  only. No execution evidence: chill is Linux and qbit autorun is off.
- State-only (not git): those six Prowlarr indexers and tag 1; qbit
  exclusions; Sonarr release profile id 1. The arrs were upgraded the
  same day; see the EZTV maintenance note below.

## maintenance 2026-11-18: Octo-Fiesta stages music for wrtag

- Change: Octo-Fiesta's `/app/downloads` bind moved from
  `music/clean` to `media/downloads/octo-fiesta`. It no longer writes
  music into the Navidrome library; `homelab-wrtag-import <dir>` queues a
  reviewed directory through wrtagweb, so wrtag is the only writer to
  `clean`. Playlist exports also land under the staging tree; regenerate
  them after the album is imported.
- Daily: `homelab-music-import.timer` runs at 06:15, queues staging
  directories older than one hour, and writes
  `/opt/stacks/observability/state/music-review.json`. The home dashboard
  shows a warning with the number of albums needing input/retry and a
  Music review block in Media activity.
- Review: admin Filebrowser (`files.h.malice.biz`) -> `media/downloads/
  octo-fiesta`. The existing `media/downloads/_to-review` backlog is
  untouched.
- Verify: `docker inspect media-octo-fiesta-1` shows the staging bind as
  `/app/downloads`; a test download lands there; `homelab-wrtag-import`
  returns a wrtag job; `systemctl status homelab-music-import.timer`
  shows the next run.
- Rollback: restore `/mnt/data/media/music/clean:/app/downloads` in
  `stacks/media/docker-compose.yml` and run `make deploy`.

## maintenance 2026-11-18: arr upgrade and EZTV mirror

- Change: Prowlarr 2.4.0 -> 3.0.2, Sonarr 4.0.17 -> 4.0.20, Radarr
  6.2.1 -> 7.0.3; tags pinned in `stacks/media/docker-compose.yml`.
- EZTV: the definition tried `eztvx.to` first. From the VPS egress that
  host returns Cloudflare 451 ("legal order ... within United Kingdom"),
  which Prowlarr reported as `Indexer is disabled` 410 to Sonarr. The
  other mirrors reject a plain fetch with a challenge but pass through
  FlareSolverr. Fix: EZTV `baseUrl` -> `https://eztv.yt/`; the indexer
  keeps tag 1 (`flaresolverr`). State only, not git.
- Verify: Prowlarr `/api/v1/indexerstatus` is empty and an EZTV search
  returns results; Sonarr and Radarr health are empty; both report the
  new versions. Sonarr's single queue row is an Archer `delay` hold, not
  a stalled download.
- Rollback: extract
  `/mnt/fast/scratch/pre-upgrade-arr-20261118T120435Z.tgz` into
  `/opt/stacks/media/state/` and revert the image tags; clear the EZTV
  base URL in the indexer UI.

## maintenance 2026-11-18: minecraft pauses when empty

- Change: `PAUSE_WHEN_EMPTY_SECONDS=60` in `stacks/games`
  (commit `e4f6be4`). Paper was already in use; no server switch was needed.
  Paper defaults this to `-1`, so it is opt-in, not a vanilla-default flip.
- Verify: `logs/latest.log` shows `Server empty for 60 seconds, pausing`;
  server-list ping still returns the MOTD; RCON still answers while paused
  and the backup quiesce path (`save-off`, `save-all flush`, `save-on`)
  succeeded. `homelab-public-check` TCP 25565 passed after the restart.
- Measure: idle JVM CPU fell from ~0.79% of one core (pre-change, 22h
  uptime) to ~0.34% after JIT settled (120s `/proc` delta; server thread
  0.19%, spark monitors 0.08%). Ignore the first ~15 min after a restart:
  C2 compilation transiently shows 1-2%. Absolute host saving is small
  because the 19M world was already near-idle: TPS 20, MSPT 0.1ms.
- Prevent: Paper calls this out as plugin-incompatible by default. The only
  plugins here are Chunky, spark and bStats; do not add ticking plugins
  without retesting pause. Chunky pregen stalls while paused, so temporarily
  set `PAUSE_WHEN_EMPTY_SECONDS=-1` for a pregen run. Vanilla calls
  `autoSave()` when it pauses, so this adds no unsaved-data window; world
  time, crops and furnaces still stop while nobody is online.


## maintenance 2026-11-18: one metrics surface, one alert engine

- Change: `home.h` stopped being a second monitoring system. It now renders
  live state only (current CPU/mem/net/disk numbers, container state, Compose
  inventory, Caddy routes, backups, logs, app APIs) and links to Grafana for
  every time series. Grafana owns the charts, the 7 d capacity projection and
  the per-host backup age; its backup stat now uses `min by (host)` so a fresh
  malice marker cannot mask a stale chill-01 one.
- Alerts: Prometheus is the only threshold engine. The dashboard stopped
  re-deriving HostDown, DiskUsageHigh, TLS expiry, public/private route
  failures, TCP probes, job timers, backup freshness and WireGuard handshake,
  and now passes every firing/pending Prometheus alert through instead of
  hiding rules it duplicated (`MIRRORED_RULES` is gone). New rules:
  `PrivateEndpointDown`, `TLSCertExpiringSoonPrivate`, `TCPProbeDown`,
  `DiskFillingSoon`, `BackupStatsFailing`, `BackupStatsStale`,
  `BackupRepositoryEmpty`. Local checks that remain are only what no metric
  exports: container lifecycle/health, authenticated app reachability, and
  dashboard source-read failures.
- Private edge: new `blackbox-private` Prometheus job probes all 16
  `*.h.malice.biz` vhosts through the tailnet address. `home.h` reads those
  `probe_*` series instead of making its own TLS handshakes; `clients.py`
  lost `probe_tls` and `PRIVATE_EDGE` is no longer a dashboard setting.
- Code removed: `_fetch_telemetry` range queries and sparklines,
  `DISK_SLOPE_Q`/`SERIES`, `parsers.days_until_full`, `disk_severity`,
  `tls_severity`, and the mirrored-rule filter. Dashboard runtime is narrower
  by roughly 250 lines; the parser/alert tests were reduced to the surviving
  contracts.
- Verify: `promtool check config` and `check rules` (25 rules) passed on
  chill-01; 41 dashboard unit tests passed; `node --check` and JSON/YAML
  validation passed. From inside `observability-dashboard-1`,
  `https://{home,grafana,cockpit}.h.malice.biz` returned 200 and
  `{stirling,sonarr}.h.malice.biz` returned 401 (expected, allowed by the
  blackbox module), so the new job's DNS/TLS path works from the container
  network. After deploy: all 16 `blackbox-private` targets up, 25 rules
  loaded with the `fuse.*` forecast filter, Grafana serves 14 panels, and
  `home.h` renders 43/43 running services with zero console errors. The
  live `Mémoire hyperviseur < 10%` warning now reaches the strip through
  the pass-through instead of a local copy.
- Rollback: revert the commit and `make deploy`; Prometheus restarts with the
  previous rule set and `home.h` returns to its local derivations.

## maintenance 2026-11-18: wrtag web UI auth disabled behind the tailnet

- Change: `WRTAG_WEB_AUTH` moved from `basic-auth-from-api-key` to
  `disabled` in `stacks/media/docker-compose.yml`. `wrtag.h.malice.biz`
  opens without a browser password prompt; the tailnet stays the outer
  boundary, exactly as for the `*.h` vhosts generally.
- Not changed: `/op/*` keeps `apiKeyMiddleware`, so `homelab-wrtag-import`
  and slskd's `autotag.sh` still authenticate with `WRTAG_WEB_API_KEY`.
  slskd's own UI auth is untouched.
- Verify: deployed commit `f88c552610`; `media-wrtag-1` recreated and Up,
  live env `WRTAG_WEB_AUTH=disabled`. `GET /` and `/jobs` return 200 with no
  credentials; `POST /op/move` returns 401 without the key and 400 (unknown
  operation, key accepted) with it.
- Rollback: revert the commit and `make deploy`; the container recreates
  with the previous auth mode and the browser prompt returns.

## incident 2026-11-19: Feishin streams stalled on broken HTTP/3/QUIC

- Impact: playback on `player.malice.biz` (Feishin web) and the Octo-Fiesta
  Subsonic endpoint stalled and re-buffered while the server was healthy.
- Detect: Caddy `caddy.log` shows `fiesta.malice.biz` stream requests over
  `HTTP/3.0` ending in `writing: deadline exceeded` after 20-500 ms. The same
  track/range over HTTP/2 returns `206` and completes. The client network
  also keeps Tailscale on a DERP relay instead of a direct UDP path.
- Cause: QUIC/UDP is unreliable on the client network; HTTP/3 large
  responses die mid-stream. Feishin then re-issues `Range` requests from
  the buffered offset, which looks like stutter/seeking. Storage
  (76-430 MB/s reads), Navidrome/Octo-Fiesta (44 MB FLAC in 11.8 s public),
  and bandwidth (~20 Mbit/s client, 1.5 Mbit/s FLAC) were not the limit.
- Repair: `vps/Caddyfile` sets `servers { protocols h1 h2 }`; commit
  `25cb9af3`. Live VPS copied/validated/reloaded directly because the
  Ansible SFTP connection hung; run `make vps` again when SSH is stable.
- Redaction: `fiesta.malice.biz` uses `import log_redacted`; the global
  `caddy.log` format also filters `p`/`t`/`s`/api keys. New access and error
  entries show `p=REDACTED`.
- Verify: no `Alt-Svc` on `player`/`fiesta`; live config protocols are
  `h1,h2`; a 1 MB range over HTTP/2 returns `206` in 1.34 s and the access
  log records `HTTP/2.0` with a redacted URI. Clear the browser Alt-Svc
  cache if an existing session keeps trying QUIC.
- Follow-up: rotate the `francis` Navidrome password and update Feishin/
  Subsonic clients; old Caddy logs still contain the pre-redaction `p=`
  value. Purge/rotate those logs after the password change. If playback
  still buffers, address Feishin's raw-FLAC next-track preload (use
  Navidrome directly/transcode, not Octo-Fiesta's chunked transcode).
- Rollback: remove the `servers` block and redeploy; HTTP/3 returns.

