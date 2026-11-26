# Public server setup

The VPS serves public HTTPS. It forwards selected other ports to chill-01
over WireGuard. No apps run on the VPS.

## Deploy

From the repository root:

```sh
make vps
```

Ansible manages packages, SSH, Caddy, firewall rules, sysctls, and services.
Provision WireGuard identities separately. Do not edit /etc/wireguard.
A repeat run with no changes should report changed=0.

## Git-owned files

- [Main Caddy config](Caddyfile) goes to /etc/caddy/Caddyfile.
- [Public site files](sites/) go to /etc/caddy/sites/.
- [Input and forwarding rules](firewall.nft) go to /etc/nftables.d/homelab_firewall.conf.
- [Port forwarding and return NAT](nftables.conf) go to /etc/nftables.d/homelab_nat.conf.

Ansible removes site files deleted from Git and validates Caddy before it
reloads. It validates and applies the two firewall tables after the provider
rules. It does not replace CrowdSec or other tables. Edit the source in Git,
not the live rules. Never flush the ruleset.

## Public transport

The public edge uses IPv4. Caddy redirects HTTP on port 80 to HTTPS on
port 443 and serves HTTP/1.1 and HTTP/2. HTTP/3 is off after the
[November 19 streaming incident](../docs/history/2026-11-17-to-19-operations.md#incident-2026-11-19-feishin-streams-stalled-on-broken-http3quic).
UDP 443 is closed. Do not publish AAAA records without a working IPv6 path.

SSH is key-only on port 4522. Caddy reaches chill-01 through chill0. The
[port forwards](nftables.conf) send app traffic to 10.44.0.2 and P2P traffic
to gluetun at 10.30.0.4 through wg0. The firewall allows established traffic,
explicit port forwards, and P2P egress. It does not allow general access to
the app network.
