# TODO

Open work only. Record incidents and drill results via [RUNBOOK.md](RUNBOOK.md).
Completed work and verification: [2026-11-25 snapshot](docs/history/2026-11-25-backlog.md) and the 2026-11-26 continuation in [operations history](docs/history/2026-09-11-operations.md).

## Safety and recovery

- [ ] Prove independent offsite recovery with trusted escrow and disposable
  application restores. See [recovery expectations](RUNBOOK.md#recovery-expectations).
- [ ] Verify VM 100 at 4 GiB only after a recent successful dump and matching
  archive, tested interactive guest console, and owner-confirmed workload.
  Keep it at 8 GiB until then.
- [ ] Refresh malice's signed EFI boot path after independent recovery and
  VM 100 sizing are proven, with tested console access and an on-site operator.
  Keep `7.0.14-26-pve` as fallback; follow the
  [boot procedure](RUNBOOK.md#malice-boot-and-disk-maintenance).
- [ ] After the boot checks pass, retire only the serial-verified `sdc`. Keep
  `sda` (`/mnt/backup`) and `sdb` (`/mnt/vault`). Do not pull or wipe either
  backup disk. Verify mounts, guest autostart, backups, and public checks.
- [ ] Confirm Healthchecks' external notification channel and 5m period / 15m
  grace; prove a real `/fail` notification and recovery. No authorized account
  or receipt was available 2026-11-26.
- [ ] After an authorized receipt is available, exercise a harmless real failure
  and confirm `notify@` → Gotify and `HomelabJobFailed` → bridge → Gotify.
- [ ] Repeat the restore drill quarterly; record scope, timing and result.

## Instrumentation and hygiene

- [ ] Deploy and verify app health instrumentation (Caddy admin, Jellyseerr,
  Navidrome, Radarr/Sonarr/Bazarr). Source committed 2026-11-26; rollout is
  blocked by the `music.h.malice.biz` private-probe contract and missing live
  `DASHBOARD_BAZARR_API_KEY`.
- [ ] Deploy and verify `ArrImportBlockedTooLong`, executable-payload, and
  `ContainerOOMMetricsMissing` rules. The scanner/timer are live and successful;
  Prometheus rules are committed but not deployed while the private-probe
  contract fails.
- [ ] Roll out [mount narrowing one batch at a time](RUNBOOK.md#mount-narrowing-rollout).
  Jellyfin/Bazarr is first; later batches are held in Git. The private-probe
  contract still blocks stack rollout. Leave Filebrowser proxy-header trust
  off on shared Docker networks.
- [ ] Add CAA, DNSSEC/DS, and null MX; document IPv4-only public service.
  HSTS/baseline headers and HTTP/3 were already deployed and verified. Public
  DNS queries on 2026-11-26 returned no CAA, DS, or MX answer; no DNS edits made.
- [ ] Review the chill-01 build cache (846.4 MB reclaimable) and five DB `.bak`
  files (27,726,447 bytes observed 2026-11-26). Do not delete until the latest
  restic snapshot is verified and cleanup is explicitly approved.
- [ ] Decide whether to disable Tailscale key expiry for chill-01 and malice
  before March 2027. Keep existing offline admin devices registered unless
  explicitly revoked.
- [ ] Resolve remaining documentation drift: `vps/README.md` missing
  `vps/firewall.nft`, edge bootstrap comments, photos/games “mirror disk” comments.

## Accepted risks and decisions

These are policy/hardware constraints, not unfinished deployments.

- No UPS/NUT; revisit power-loss mitigation when hardware is available.
- VPS retains two unrestricted root authorized keys and private-key copies;
  secret rotation/root-key restrictions remain an accepted policy risk.
- Minecraft remains public without a whitelist, with RCON enabled; revisit as
  the player base grows.
- Decide whether to accept or separate P2P egress on the public edge IP:
  an abuse complaint could suspend the whole edge.
- Confirm whether rebuild-from-git plus offsite application data is sufficient,
  or full VM images also need offsite retention.
