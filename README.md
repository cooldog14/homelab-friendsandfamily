# homelab

VM 101 runs the apps.
The VPS is the public edge.
Tailscale is private admin access.
WireGuard is only VPS to VM.

## layout

- host: VM bootstrap, backups, host timers
- stacks: Docker Compose apps
- vps: public Caddy, nftables, WireGuard endpoint

## deploy

- make deploy updates VM
- make vps updates the VPS
- make host bootstraps VM 
- make edge-reload restarts private Caddy
- make check validates compose and shell files
