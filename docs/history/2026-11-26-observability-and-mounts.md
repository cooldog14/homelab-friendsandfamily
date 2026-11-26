# Observability, mounts, and review fixes — 2026-11-26

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## maintenance 2026-11-26: continuation gate review

- Preserved verified commits `f9be19d`, `c682c80`, `6f5ba5b`, and `46b5858`.
  Prior-run evidence carries forward: OpenTofu has only `PVEAuditor` at `/`,
  `make tofu-plan` returned no changes, and the SSH/resolver/firewall/public
  header work was verified. None was reapplied.
- Independent recovery remains unproven. No `APP_ENV`/`MALICE_ENV` paths were
  supplied; the known private config directory contains only the Cloudflare
  Worker and OpenTofu env records. Their contents were not read. No restore,
  SQL import, or Bolt application smoke was run.
- Read-only VM100 review via `ssh -o BatchMode=yes -o ConnectTimeout=6 malice`
  found `work-01` running with 8192 MiB. The 2026-11-22 local archive
  `vzdump-qemu-100-2026_11_22-03_30_02.vma.zst` is nonempty (9,144,706,650
  bytes); its task log ends `Finished Backup of VM 100`. Interactive console
  access and an operator-confirmed guest workload check remain unproven, so
  memory was not changed and no baseline/swap-in measurement was taken.

## maintenance 2026-11-26: scanner, observability and mount source changes

Commits `63a68fef00`, `0f1c3873bd`, `832d17a3c3`, and `66cd384af5` record the
download scanner/host metrics, dashboard and Prometheus rules, Worker failure
logging, and mount/proxy source changes. Owner Music Manager/Caddy changes were
left uncommitted.

- First `make host` deployed the scanner root guard, service, timer, and host
  metrics (`ok=60 changed=4 failed=0`). One service run returned status 0 and
  the textfile metrics showed scan success 1 and executable file count 0; the
  timer was active. A follow-up copied `chill.caddy` and `media.caddy` into
  `/usr/local/share/homelab-public-sites` for the prober (`ok=59 changed=1`);
  this did not reload or deploy VPS Caddy. The third run was idempotent
  (`ok=59 changed=0 failed=0`).
- First `make hypervisor` installed the malice metrics collector
  (`ok=20 changed=2 failed=0`); its repeat was idempotent
  (`ok=20 changed=0 failed=0`). A manual metrics run refreshed the file; the
  source sample showed no WireGuard peer series, as expected on malice.
- Dashboard, queue-age and payload rules are committed but not deployed.
  `host/check-probe-targets.py` reports the owner-added
  `music.h.malice.biz` private route missing from `blackbox-private`. This is a
  source integration gate, not an observed live outage. The live
  `DASHBOARD_BAZARR_API_KEY` is absent. No stack deployment, Caddy reload, VPS
  route deployment, or Worker deployment occurred.
  Full `make check` was not run because the known target contract fails; scoped
  checks below passed.
- Mount narrowing and Filebrowser proxy changes are committed but not deployed.
  Every new bind source existed as a real directory; `/mnt/data` resolves to
  `pve1-pool[/takeover-primary/r1/mnt/data]` and `/mnt/pool` to `pve1-pool`,
  both virtiofs. No data was moved and no mount was changed.
- Validation: dashboard tests 76/76; host tests 44/44; alert bridge contract
  43 rules; Ansible syntax check; shellcheck; Worker `node --check`; Promtool
  rule check and detection scenarios; `docker compose config` for apps, media,
  edge, and observability on chill-01; private Caddy adapt and public Caddy
  validate all passed. The observability Compose check used a validation-only
  placeholder for the absent Bazarr key; no secret was printed.
- Public DNS queries returned no CAA, DS, or MX answer. Live requests to
  `files.malice.biz` (200) and `jellyfin.malice.biz` (302) returned HSTS,
  `X-Content-Type-Options`, and `Referrer-Policy`. No DNS change was made.
- No Healthchecks account/receipt was available; no `/fail`, recovery, or real
  notification failure drill was run. No clean-machine restore was run because
  trusted `APP_ENV`/`MALICE_ENV` files were not supplied.
- Read-only cleanup review found 846.4 MB reclaimable builder cache and five
  `.bak` files totaling 27,726,447 bytes. Neither was deleted; the latest
  restic snapshot was not checked for this cleanup. VM 100 remains at 8 GiB;
  no memory, kernel, ESP, reboot, disk, or tailnet-device change was made.

## maintenance 2026-11-26: review fixes

- `0267ca59ef` preserves full-precision observation timestamps in `/metrics`
  and withholds failed Arr queue counts from the dashboard snapshot.
- `8ccde7b56e` keeps Filebrowser proxy-header trust off on shared networks.
  Password/passkey configuration and Caddy's public headers and log redaction
  are unchanged.
- Of the reviewed mount batches, only Jellyfin/Bazarr (`46b5858`) is enabled in
  the committed manifests. Later batches are held in separate, mount-only commits:
  - qBittorrent/Radarr/Sonarr: `2431903931`
  - slskd: `2947ca7cbe`
  - wrtag: `fede553c67` (activate with the coordinated Music Manager change)
  - admin Filebrowser: `bd935a69f0`
  Reverse each hold only when the preceding batch and this batch's
  prerequisites pass. Use the [rollout procedure](../../RUNBOOK.md#mount-narrowing-rollout).
- Corrected the boot and retirement procedures: no `grub-install`, keep the
  signed boot chain and fallback kernel, and preserve `sda` and `sdb`. Only
  the serial-verified `sdc` can be retired after the recovery, VM 100, console,
  and on-site gates pass.
- Checks: 27 dashboard metric/snapshot tests passed. A disposable local
  browser fixture showed the Sonarr failure with no count and the successful
  empty Radarr queue with count 0. Apps/media Compose config, private Caddy
  adapt, public Caddy validate, and Filebrowser YAML checks passed.
- No production changes. Owner Music Manager work was not committed or
  deployed; its private-probe mismatch and absent dashboard Bazarr key
  remain rollout gates.
