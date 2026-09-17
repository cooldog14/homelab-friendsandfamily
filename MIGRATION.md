# current migration state

The homelab is now one repo and one home workload host.

## current model

- chill-01 VM 101 runs the Docker stacks.
- The VPS is the public edge.
- WireGuard is only the VPS `<->` chill-01 infrastructure link.
- Tailscale is the only private/admin entry point for people.
- Media moved from the old LXC 203 layout into `stacks/media`.
- Public Caddy site files live in `vps/sites/*.caddy` and are installed by `make vps`.
- Private/admin names live in `stacks/edge/Caddyfile` under `*.h.malice.biz`.

## live cleanup after deploy

1. Stop the old LXC 203 media stack before starting `stacks/media` on chill-01.
2. Copy the media `.env` secrets to `/opt/stacks/media/.env` on chill-01.
3. Run `make deploy`.
4. Run `make vps`.
5. Remove the old VPS 10.30 WireGuard interface/config.
6. Remove old VPS nftables rules for 10.30 and port 6881 after confirming no traffic uses them.
7. Remove or archive the old `homelab-media` checkout after the merged repo is pushed.

## do not resurrect

- Do not add WireGuard for phones, laptops, or admin access. Use Tailscale.
- Do not keep arr/LXC 203 as a deployment target.
- Do not put admin services on public `*.malice.biz` routes.
- Do not add a dashboard container for the homepage; Caddy serves the static page.
- Do not bring back Cockpit.
