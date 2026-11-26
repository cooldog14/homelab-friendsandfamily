# TODO

Open work only. Keep procedures in the [runbook](RUNBOOK.md) and results in
[operations history](docs/history/README.md).

## Next maintenance priorities

- [ ] Prove independent offsite recovery with trusted escrow and disposable
  application restores. See the [recovery procedure](RUNBOOK.md#recovery-expectations);
  repeat the drill quarterly after the first proof.
- [ ] Prove both Gotify delivery paths with a harmless real failure and
  separate receipts. Independently confirm the Healthchecks channel,
  5-minute period / 15-minute grace, failure receipt, and recovery. Follow the
  [notification drills](RUNBOOK.md#notification-drills) when authorized readback
  is available.

## Gated rollouts

The [November 26 record](docs/history/2026-11-26-observability-and-mounts.md)
distinguishes deployed host work from verified source. The owner’s
`music.h.malice.biz` route/probe mismatch and missing live
`DASHBOARD_BAZARR_API_KEY` must be resolved before the stack rollout.

- [ ] Deploy and verify cached app health, Arr import-age, payload, and missing
  OOM-counter alerts. The host scanner/timer are already active; that does not
  prove the Prometheus scrape or alerts.
- [ ] Roll out [mount narrowing one batch at a time](RUNBOOK.md#mount-narrowing-rollout).
  Jellyfin/Bazarr is first; later batches are held in Git. Keep Filebrowser
  proxy-header trust off on shared Docker networks.
- [ ] Release the Worker logging fix only with authorized Cloudflare Worker
  access, then confirm a scheduled heartbeat succeeds.

## Gated operator work

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
- [ ] Decide whether to disable Tailscale key expiry for chill-01 and malice
  before March 2027. Keep existing offline admin devices registered unless
  explicitly revoked.
- [ ] Add CAA, DNSSEC/DS, and null MX only after issuer, mail, and account
  prerequisites are confirmed. Preserve the [public transport policy](vps/README.md#public-transport).
- [ ] Review chill-01's build cache and old DB `.bak` files. Prune only the
  build cache and remove only proven obsolete files after verifying the latest
  restic snapshot and getting cleanup approval.

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
