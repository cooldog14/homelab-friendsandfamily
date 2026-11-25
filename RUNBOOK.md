# Runbook

Break one thing at a time, use a quiet window, and never test by deleting data.
Follow the safety and access rules in [AGENTS.md](AGENTS.md).

## Recovery expectations

Best effort, not HA. Recovery after host, VM or disk loss is manual; full-platform
RTO is unmeasured. Nightly backups cover `/opt`, `/mnt/fast/dumps`, `/mnt/data`,
`/etc` and `/root/.ssh`, excluding downloads, movies, TV and raw music staging.
RPO depends on the latest successful snapshot, not merely the timer schedule.
Use `make restore-test` to validate recovered artifacts; record scope and timing.

## Deployment regression

Redeploy the previous good commit: `git checkout <good-commit>`, then run only
the affected target (`make deploy`, `make host`, `make vps` or `make hypervisor`).
`make deploy` ships committed files, not the working tree. Restore application
state only for a confirmed data-changing migration, not a bad container image.
Record bad/good commits, affected stacks and any state restoration.

## Public service down

Check `homelab-public-check` logs and compare `vps/sites/*.caddy` with the live
VPS configuration before changing applications. If many vhosts fail together,
check shared layers first: the `/mnt/data` takeover bind, WireGuard handshakes
on both ends, and `docker ps` for mass exits. Do not restart stacks one by one.
For an isolated application failure, inspect its logs and restart its Compose
service. Record detection and recovery times.

## Private edge

Fix the git-owned `stacks/edge/Caddyfile`, validate the configuration before
restart, deploy the committed change, then run `make edge-reload`.
Caddy reads the bind-mounted configuration at startup; unchanged Compose files
do not trigger a restart. Check the actual route afterward.
Use exact host matchers, never `map` for routing; unknown hosts must return 404.

## VPS Caddy

Fix the git-owned site file and run `make vps`; validation must block a bad
configuration before reload. See the [VPS contract](vps/README.md).

## WireGuard

Keep console/fallback access before interrupting a tunnel. Inspect handshakes
with `wg show` on each end. The backend interfaces are VPS `chill0` and
chill-01 `wg0`; restart only the affected `wg-quick@<interface>` unit.
If handshakes stay stale, check the underlay first: chill-01 must reach the VPS
endpoint `194.58.47.21` directly. A broken gateway route or stale router ARP
can kill the tunnel without WireGuard errors. Never edit `/etc/wireguard`.

## Stale backup or failed alerts

Inspect the backup unit's journal and latest successful snapshot. Repair the
cause and run the backup; never refresh a success marker without a real success.
`homelab-backup-watchdog` alerts after 48 hours. Retention keeps three snapshots
per repository and refuses unexpected backup path sets; do not bypass that guard.

Check Prometheus → Alertmanager → bridge → Gotify, plus `notify@` delivery.
After host deployment/reboot, verify backup/check timers and run
`homelab-pipeline-check` and `homelab-alert-check`. The external WAN Worker and
Healthchecks cover loss of chill-01/Gotify; a green public application alone
does not prove notification delivery.

## History

Record dated incidents, maintenance and drill results in
[operations history](docs/history/2026-09-11-operations.md), not in the procedures
above. Historical commands and status are not current instructions.
Completed work and prior verification are in the
[2026-11-25 backlog snapshot](docs/history/2026-11-25-backlog.md).
