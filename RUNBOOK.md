# runbook

Break one thing at a time.
Use a quiet window.
Do not test by deleting data.

## public service down

Break: stop one harmless public service.
Observe: public-check fails, Gotify alerts, systemd logs show failure.
Repair: restart the stack from Dockge or docker compose.
Note: detection time and repair time.

## private caddy bad config

Break: test a bad edge Caddy config.
Observe: edge-reload must fail before restart.
Repair: restore the valid config.
Note: whether validation blocked the outage.

## backup stale

Break: simulate an old backup marker.
Observe: backup watchdog alerts Gotify.
Repair: run backup or restore the marker.
Note: alert path and delay.

## WireGuard link

Break: only with console access, stop the tunnel briefly.
Observe: public HTTP fails and make tunnel shows the issue.
Repair: restart wg-quick.
Note: user impact and recovery command.

## VPS Caddy bad config

Break: test a bad site file.
Observe: Caddy validation blocks reload.
Repair: fix the file and run make vps.
Note: what the validation caught.

## restore drill

Break: nothing in production.
Restore: one small DB dump or state file to a temp path.
Verify: file readable or DB integrity ok.
Note: RTO, RPO, and exact commands.

## incident note

Incident:
Impact:
Detection:
Repair:
Repair time:
Prevention:
