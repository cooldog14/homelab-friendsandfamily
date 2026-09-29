# homelab

homelab for friends&family.

## start here

- `AGENTS.md`: current topology, storage map, access rules, and hard safety rules.
- `TODO.md`: transient work and open follow-ups.
- `RUNBOOK.md`: incidents, drills, and recovery notes.

Documentation rule: keep `README.md` and `stacks/README.md` small; put the big
current operating context in `AGENTS.md`.

## layout

- `host/`: chill-01 bootstrap, backups, checks, and timers.
- `stacks/`: Docker Compose apps deployed to `/opt/stacks`.
- `vps/`: public Caddy, nftables, and WireGuard endpoint.

## make commands

- `make check` validates compose, Caddy/public checks, and shell scripts.
- `make deploy` updates chill-01 over Tailscale.
- `make vps` updates the VPS edge.
- `make host` bootstraps chill-01.
