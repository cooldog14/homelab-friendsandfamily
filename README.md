# homelab

homelab for friends&family.

## start here

`AGENTS.md`: current topology, storage map, access rules, and hard safety rules.
`TODO.md`: self explanatory.
`RUNBOOK.md`: incidents and notes.

## layout

`host/`: bootstrap, backups, checks, and timers.
`stacks/`: Docker Compose apps deployed to `/opt/stacks`.
`vps/`: public Caddy, nftables, and WireGuard endpoint.

## make commands

`make check` validates compose, Caddy/public checks, and shell scripts.
`make deploy` updates chill-01 over Tailscale.
`make vps` updates the VPS edge.
`make host` bootstraps chill-01.
