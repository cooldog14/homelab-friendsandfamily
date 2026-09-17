# agent rules

This file is for automation only. Humans should start with `README.md`.

## hard rules

- Git is the source of truth; do not treat live host edits as durable.
- Never print or commit secrets. Do not use `git add -A`.
- Keep secrets on hosts in stack `.env` files, `/etc/homelab.env`, and WireGuard configs.
- Never make an admin surface public or add public base URLs to private-only services.
- Tailscale is the only private/admin entry point for people.
- WireGuard is only the VPS `<->` chill-01 infrastructure link.
- Never delete the VPS/chill-01 WireGuard configs or `/etc/wireguard` on either host.
- Never flush the VPS nftables ruleset.
- Never bind Docker services to `0.0.0.0` unless the exception is documented.
