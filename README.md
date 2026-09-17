# homelab

Git is the source of truth.

chill-01 VM 101 runs the apps.
The VPS is the public edge.
Tailscale is private admin access.
WireGuard is only VPS to chill-01.

## layout

- host: chill bootstrap, backups, host timers
- stacks: Docker Compose apps
- vps: public Caddy, nftables, WireGuard endpoint

## deploy

- make deploy updates chill-01
- make vps updates the VPS
- make host bootstraps chill-01
- make edge-reload restarts private Caddy
- make check validates compose and shell files
- RUNBOOK.md has break-fix drills
- TODO.md has next work

## rules

- No secrets in git
- No public admin surfaces
- No live host edits as source of truth
- Never flush VPS nftables
- Never delete WireGuard configs
