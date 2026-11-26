# VPS edge contract

The VPS is the public edge only: Caddy terminates HTTP(S), nftables forwards
non-HTTP ports to `chill-01` over WireGuard, and no apps run here.

## Deploy

Host state is Ansible-managed. From the repo root:

```sh
make vps
# or: ansible-playbook ansible/vps.yml
```

The playbook manages packages, SSH hardening, Caddy, nftables, sysctls, and
services. WireGuard identities are provisioned separately; keep
`/etc/wireguard` contents outside Git and untouched by the playbook. A second
run on converged hosts reports `changed=0`.

## Git-owned files

- [`Caddyfile`](Caddyfile) → `/etc/caddy/Caddyfile`
- [`sites/*.caddy`](sites/) → `/etc/caddy/sites/*.caddy`
- [`firewall.nft`](firewall.nft) → `/etc/nftables.d/homelab_firewall.conf`
  (effective `inet firewall` input/forward table)
- [`nftables.conf`](nftables.conf) → `/etc/nftables.d/homelab_nat.conf`
  (`ip homelab_nat` forwarding and return NAT)

Public vhosts are git-owned in `vps/sites/*.caddy`: the playbook copies them,
runs `caddy validate`, reloads only when validation passes, and removes site
files deleted from git.

`make vps` persists both includes after the provider base rules and checks
them with `nft -c` before applying changes. Change the Git-owned source; do
not hand-edit the live rules or flush the ruleset. The two managed tables
are replaced independently of CrowdSec and other tables.

## Public transport

Public services use the IPv4 edge. Caddy serves HTTP/1.1 and HTTP/2 on TCP
443 and redirects TCP 80 to HTTPS. HTTP/3 is disabled after the
[November 19 streaming incident](../docs/history/2026-11-17-to-19-operations.md#incident-2026-11-19-feishin-streams-stalled-on-broken-http3quic);
the Git-owned filter does not open UDP 443. Do not publish AAAA records
without an end-to-end IPv6 rollout and checks.

SSH to the VPS is key-only on TCP 4522. Caddy speaks to `chill-01` over
`chill0`. Public non-HTTP forwards and P2P entry ports are defined in
[`nftables.conf`](nftables.conf): application DNAT lands on `10.44.0.2`;
P2P DNAT lands on gluetun's `10.30.0.4` via `wg0`. The filter permits
established traffic, explicit DNAT and that P2P egress, not a general
route into the application network.
