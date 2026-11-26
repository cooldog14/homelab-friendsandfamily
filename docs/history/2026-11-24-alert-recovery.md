# Alert and probe recovery — 2026-11-24

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## maintenance 2026-11-24: restore alert delivery and private endpoint probes

- A1 (alert delivery): `/etc/homelab.env` on `chill-01` pointed `ALERT_URL`
  at `https://gotify.malice.biz/message`, which has no VPS route and fails
  TLS from the host. It now uses `https://gotify.h.malice.biz/message` with
  the same token; mode 0600 was preserved. `notify@audit-test.service`
  completes with no curl error and a POST to `ALERT_URL` returns 200.
- `host/backup.sh` `alert()` ended with `|| true`, so a dead URL or any
  future curl/TLS failure stayed silent. It now logs
  `homelab alert delivery failed` via `logger`, matching `notify@.service`.
  Commit `fbbe582c7`; the file is installed by `ansible/roles/chill_units`.
- A2 (private probes): all 16 `blackbox-private` probes had been failing
  since 2026-11-20. Live `iptables -L DOCKER-USER -v -n` showed the
  `-i br-+ -o br-+ DROP` rule with 2,043K packets while the
  `-d 100.64.0.0/10 DROP` rule had 0. Root cause was host script drift:
  `/usr/local/bin/homelab-firewall-neko` was a stale older version
  (sha256 `111c77a1…`) that dropped all cross-bridge traffic including
  observability → edge. HEAD `host/firewall-neko.sh` (`68ebed26…`) already
  skips `$edge_br` as a destination, so no new allow rule was needed.
- Repair: `make host` (`ok=52 changed=4 failed=0`) reinstalled the
  committed script and re-ran it. No hand edits to `/usr/local/bin`.
- Verify: installed hash matches HEAD; `iptables -S DOCKER-USER` shows
  explicit per-bridge rules with no `br-+` wildcard and no edge bridge in
  the cross-bridge DROPs; `sum(probe_success{job="blackbox-private"})=16`;
  zero firing alerts; private TLS expiry metric non-zero; public HTTP 13/13
  and TCP 4/4 unchanged; no failed systemd units. Alerts cleared on their
  own — nothing was silenced.
- Still open: the two credentials exposed in the 2026-11-09 review have not
  been rotated (this incident's Navidrome follow-up and TODO-FIXES P0-1);
  live media config still differs from git (audit A3).

