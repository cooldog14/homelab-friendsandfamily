# TODO

Current work only. See the [runbook](RUNBOOK.md) for procedures and
[history](docs/history/README.md) for results.

## Next

- [ ] Prove recovery from offsite on another machine. Use the escrow records
  and test the restored apps. See the [recovery procedure](RUNBOOK.md#recovery-expectations).
  Repeat the drill quarterly after it passes.
- [ ] Confirm separate Gotify receipts from the two paths. Confirm the
  independent Healthchecks recipient, 5-minute period, and 15-minute grace.
  Prove failure and recovery using the [notification drills](RUNBOOK.md#notification-drills)
  when authorized readback is available.

## Next deployments

The [November 26 rollout](docs/history/2026-11-26-media-and-monitoring-rollout.md)
records the live media and monitoring checks. Music Manager stays on its own
branch. Add the private probe when its route is integrated.

- [ ] [Continue one mount batch at a time](RUNBOOK.md#mount-narrowing-rollout).
  Check qBittorrent and Arr paths and test a disposable import next. Keep
  Filebrowser header trust off on shared Docker networks.
- [ ] Deploy the Worker logging fix with authorized Cloudflare access. Check
  that a scheduled heartbeat succeeds.

## Needs access or a maintenance window

- [ ] Verify VM 100 at 4 GiB after checking a recent successful backup and
  matching archive, testing the interactive console, and confirming
  the workload with the owner. Keep it at 8 GiB until then.
- [ ] Update the signed EFI boot setup after proving recovery and VM 100
  sizing. Require a tested console and someone on site. Keep 7.0.14-26-pve
  as fallback. See the [boot procedure](RUNBOOK.md#malice-boot-and-disk-maintenance).
- [ ] Retire only the serial-verified sdc after the boot checks pass. Keep
  sda for local restic and sdb for the vault. Verify mounts, guest autostart,
  backups, and public checks.
- [ ] Decide whether to disable Tailscale key expiry for chill-01 and malice
  before March 2027. Leave offline admin devices registered.
- [ ] Decide whether to keep Cloudflare Universal SSL before adding CAA. It
  [adds issuers to the DNS answers](vps/README.md#dns-certificate-policy).
  Rule out inbound mail before adding null MX. DNSSEC needs both DNS and
  registrar access.
- [ ] Check the latest restic snapshot and get cleanup approval first. Prune
  only the build cache and delete only DB backup files proven obsolete.

## Accepted risks and decisions

These are choices and constraints, not outages.

- No UPS/NUT; revisit power-loss mitigation when hardware is available.
- VPS retains two unrestricted root authorized keys and private-key copies;
  secret rotation/root-key restrictions remain an accepted policy risk.
- Minecraft remains public without a whitelist, with RCON enabled; revisit as
  the player base grows.
- Decide whether to accept or separate P2P egress on the public edge IP:
  an abuse complaint could suspend the whole edge.
- Confirm whether rebuild-from-git plus offsite application data is sufficient,
  or full VM images also need offsite retention.
