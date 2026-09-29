# VPS edge contract

The VPS is the public edge only: Caddy terminates HTTP(S), nftables forwards
non-HTTP ports to `chill-01` over WireGuard, and no apps run here.

## Git-owned files

- `/etc/caddy/Caddyfile` from `vps/Caddyfile`
- `/etc/caddy/sites/*.caddy` from `vps/sites/*.caddy`
- `/etc/nftables.d/homelab_nat.conf` from `vps/nftables.conf`

`vps/nftables.conf` owns only the `ip homelab_nat` NAT table. It must not flush
or replace the provider/local firewall ruleset.

## Live firewall contract

Keep the live VPS input/forward policy aligned with this contract:

| Purpose | Protocol/port | Direction |
|---|---:|---|
| SSH admin | TCP `4522` | internet -> VPS |
| Public HTTP(S) | TCP `80`, `443` | internet -> VPS Caddy |
| WireGuard backend | UDP `51824` | internet/home -> VPS `chill0` |
| Mumble | TCP+UDP `64738` | internet -> DNAT `10.44.0.2` |
| Neko WebRTC | TCP+UDP `52000` | internet -> DNAT `10.44.0.2` |
| Screego TURN | TCP+UDP `3478`, UDP `52100-52200` | internet -> DNAT `10.44.0.2` |
| Minecraft | TCP `25565` | internet -> DNAT `10.44.0.2` |

Anything else needs a matching Git change and runbook note before it becomes
permanent.
