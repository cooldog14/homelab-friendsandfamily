# Case study: a public edge for a host that has no public IP

## Problem

The application host is a VM on a home hypervisor. It has a private LAN address,
a WireGuard address on a tunnel, and a tailnet address — and no public address.
The ISP router cannot be trusted to forward ports, the residential address
changes, and the machine is the only application host, so "publish it directly"
is not an option.

Constraints:

- Public HTTPS for friends and family, with real certificates.
- No inbound port on the home router.
- Admin traffic must never share the public path with anonymous visitors.
- One host is enough: no Kubernetes, no service mesh, no second control plane.

## Design

A small VPS runs the public edge, not the applications. Caddy, nftables and
CrowdSec handle ingress; a static WireGuard tunnel reaches the application host.

```mermaid
flowchart LR
  U[Internet client] -->|443| E[Edge VPS<br/>Caddy + nftables]
  E -->|WireGuard tunnel| A[App VM<br/>published app ports]
  A --> P[Private Caddy<br/>wildcard cert, tailnet]
  T[Admin on tailnet] --> P
  E -->|UDP/TCP forwards| A
```

Three layers, each with one job:

1. **Public TLS terminates on the VPS.** Caddy owns the public names, gets
   certificates over ACME (HTTP-01/DNS-01 as available), and proxies to the
   tunnel address. The home IP is never in public DNS.
2. **The tunnel carries backends only.** The WireGuard link is static, key-only,
   and scoped to the published app ports. It is not an admin path.
3. **Admin lives on the tailnet.** A second Caddy on the application host serves
   `*.h.example.com` from a wildcard DNS-01 certificate. It listens on the
   tailnet address, not the VPS WireGuard path. Exact-host matchers choose
   the backend for each private name.

The split matters: public vhosts are declared on the VPS, private vhosts on the
application host. Two Caddies never race for the same name, which would mean two
ACME orders and a rate-limited afternoon.

### Non-HTTP traffic

Some services are not HTTP: a voice server (TCP+UDP), a browser sandbox over
WebRTC (UDP port range), a TURN server, a game server. Those get explicit
nftables DNAT rules on the VPS, forwarded to the tunnel address, with the same
"only what is published" discipline as the HTTP vhosts.

### Why not a tunnel-everything mesh?

A mesh VPN that publishes services would also publish the admin surfaces unless
each one is fenced again. The VPS edge keeps the public and private sets
physically distinct: an anonymous visitor can only reach names that exist in the
public Caddy sites directory.

## Failure modes seen in practice

| Symptom | Cause | First check |
|---|---|---|
| Every public vhost 502s at once | WireGuard handshake stale or route missing | `wg show` handshake age, then `ping` the tunnel address |
| One vhost 502s, others fine | Backend port wrong, or the app binds only on the LAN address | `curl` the backend from the VPS over the tunnel |
| Public vhost hangs, LAN fine | Stale ARP entry on the router for the app host | `tcpdump -e` on the app NIC: replies to a foreign MAC |
| 404 "unknown private service" | Host not matched by an exact matcher, fell through to the default | the private Caddyfile matcher list |
| Caddy reload did nothing | Config changed on disk but the process was never restarted | restart the container, not `up -d` |

Two of these cost real hours:

- **The reload trap.** An unchanged Compose definition is a no-op for
  `docker compose up -d`, so the original deploy left old routes live after a
  Caddyfile edit. The current deploy detects Caddyfile changes and restarts
  Caddy; `make edge-reload` remains an explicit restart.
- **The ARP blackhole.** After a power cut the router kept an ARP entry pointing
  at a MAC address that no longer existed. Every inbound packet to the app host
  was flooded to the wrong destination and dropped by the guest NIC before the
  kernel counters moved — so the host looked healthy and unreachable at the same
  time. Gratuitous ARP did not clear it; only the router's own state could. The
  lesson: when one address family fails while the other is fine, suspect layer 2
  before the firewall.

## Verification

The edge is verified from the outside in, never assumed:

- A black-box public check curls every declared public vhost. It accepts
  2xx, 3xx, or the expected authentication response `401`. The timer and
  failure notification catch broken routes such as a `502`.
- The same host list is linted in CI against the private Caddyfile, so a public
  name can never be duplicated on the private edge.
- Prometheus `blackbox_exporter` probes the public URLs and the forwarded TCP
  ports every 30s, and alerts on `probe_success == 0`.
- Certificate expiry is a first-class metric, not a calendar reminder.
