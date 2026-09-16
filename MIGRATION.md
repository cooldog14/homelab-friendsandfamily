# wg-easy -> static WireGuard + Tailscale

## The design (decided 2026-09-15)

Two transports, each doing the job it is actually good at:

- **Plain static WireGuard for infrastructure links.** VPS<->chill-01 and VPS<->arr. Both have
  one permanently dialable end (the VPS's fixed public IP), so the other side just dials out
  forever and WireGuard learns its address from the authenticated packet. No coordination
  server, no DDNS, no NAT traversal, no third party. This carries every public service.
- **Tailscale for roaming devices only.** Phones and laptops, where *neither* end has a fixed
  reachable address and static config cannot work. Direct peer-to-peer, so phone<->chill-01
  traffic stops hairpinning through the VPS.

The failure boundary this buys: **Tailscale can disappear entirely and every public service
keeps serving.** You would lose only the private `*.h.malice.biz` names and fall back to
IP:port. Putting the public path on Tailscale would not have that property.

### Why roaming devices cannot just use WireGuard — measured, not assumed

Tested from a restricted network 2026-09-15:

    VPS ssh  194.58.47.21:4522   blocked
    VPS https 194.58.47.21:443   OPEN
    controlplane.tailscale.com:443   OPEN
    derp1.tailscale.com:443          OPEN

Standard ports only. That is why chill-01 is unreachable from the office today: the wg tunnel
is UDP 51822 and the egress filter drops it. Tailscale's control plane AND its DERP relay both
answer on 443, so Tailscale works from there where plain WireGuard structurally cannot.

Corollary: forwarding a UDP port on the Livebox at home would NOT fix work access, because the
blocker is the corporate egress filter, not home's reachability. That option is still worth
having as a way to make the Tailscale dependency optional, but it can never be the work path.

Corollary 2: put Tailscale on the **VPS** as well, for MANAGEMENT ACCESS ONLY. The data path
stays static WireGuard. This makes `ssh` to the VPS work from filtered networks instead of
failing on 4522, which is otherwise a hard blocker on doing stage 2 from anywhere but home.

### The 10.44 addressing is preserved exactly

chill-01 stays `10.44.0.2`, the VPS stays `10.44.0.1`, the subnet stays `10.44.0.0/24`.
That is deliberate and it is what keeps this migration small. Untouched as a result:

    vps/nftables.conf            DNAT still targets 10.44.0.2
    vps/sites/chill.caddy        reverse_proxy still targets 10.44.0.2
    every stack's ${WG_IP}       still 10.44.0.2
    host/slskd-egress.sh         wg0 stays, interface name stays, script stays
    stacks/edge/.env UPSTREAM    stays 10.44.0.2 forever, never flipped
    the 10.30 arr tunnel         untouched
    the legacy inet firewall     untouched

### Withdrawn ideas — do not resurrect

- *"Move the public path onto Tailscale."* Rejected: it makes a third party a dependency of
  every public service for no gain.
- *"Put Tailscale on the arr LXC and delete the 10.30 tunnel."* Rejected: the 10.30 link is a
  static server-to-server link that already works. Same reasoning as keeping VPS<->chill-01
  on WireGuard.
- *"Move Jellyfin/requests onto chill-01."* Rejected 2026-09-15; the arr LXC stays.
- *"Drop ufw on the VPS."* Based on a misreading — `vps/bootstrap.sh:58` records that this box
  never had ufw. ufw is chill-01 only.
- *"Replace slskd-egress.sh with Gluetun."* Now OPTIONAL, not required, because wg0 survives.
  Only worth doing if you want the P2P traffic off the VPS or dislike the iptables script.

---

## Stage 0 — DNS to Cloudflare — DONE 2026-09-15

Nameservers moved; registration stays at Namecheap. Namecheap's own API needs account
eligibility *and* IPv4 allowlisting, and chill-01 egresses from a dynamic home IP, so DNS-01
renewals there would have broken silently on every ISP rotation.

Verified: `malice.biz NS` = `emma` / `lewis.ns.cloudflare.com`; apex and `vault.malice.biz`
both answering `194.58.47.21`. All original records carried over, including the `media` CNAME
to Hetzner and the SPF/DKIM/DMARC trio.

`*.h.malice.biz A 100.64.0.1` added as a placeholder the same day. Verified: `immich.h` and
`paperless.h` return `100.64.0.1` while `vault`, `nvdr`, `www` and the apex still return the
VPS. Bare `h.malice.biz` DOES still resolve to the VPS — Cloudflare synthesizes it from
`*.malice.biz` rather than returning NODATA as strict RFC 4592 would. Harmless; do not browse
it, because the VPS Caddy may issue an on-demand cert for it (see below).

Remaining: a Cloudflare API token scoped to **Zone:DNS:Edit on malice.biz and nothing else**,
no client-IP filter (that is the Namecheap trap), for `CF_API_TOKEN` in `stacks/edge/.env`.

### Leave every record on "DNS only"

Cloudflare nags to proxy. Do not. On this zone the orange cloud breaks four things:

- `vpn.malice.biz` gates on `remote_ip 10.44.0.0/24`; proxied, every request arrives from a
  Cloudflare address. (Moot once stage 2 deletes that vhost, but true until then.)
- Mumble (64738), slskd's peer port (50300), neko WebRTC (52000) and screego TURN
  (3478, 52100-52200) are not HTTP. Cloudflare does not carry those ports at all.
- `homelab-public-check.sh` would black-box test Cloudflare's cache instead of your Caddy. It
  caught real 502s that Beszel showed green.
- `*.h.malice.biz` points into `100.64.0.0/10`. Cloudflare cannot reach it, ever.

### The email warning is deliberate

`v=spf1 -all` + `p=reject` + a null DKIM key is a correct "this domain sends and receives no
mail" lockdown. Do not add an MX to satisfy the dashboard. Consequence: `admin@malice.biz` is
the ACME contact in both Caddyfiles, so Let's Encrypt expiry notices go nowhere. Issuance does
not depend on it.

Rollback: point the nameservers back at Namecheap. Namecheap does not keep a copy of the zone
after the switch.

---

## Stage 1 — Tailscale + the private Caddy

Fully additive. wg-easy keeps running, nothing public changes, rollback is one command.

1. `make host` — installs `tailscale`, adds the ufw `tailscale0` allowance, enables
   `tailscaled`. It does **not** authenticate; that stays manual.
2. On chill-01: `tailscale up --accept-dns=false --hostname=chill-01`, then `tailscale ip -4`.
   `--accept-dns=false` keeps the host resolver untouched, same reason AdGuard was retired.
3. Edit the existing `*.h.malice.biz` record to that `100.x` address, still **DNS only**. One
   field, not a new record.
4. Enroll phone and laptop from the devices themselves. **Disable key expiry on chill-01** in
   the admin console — an expired key takes private access down for reasons unrelated to your
   network. Consider tailnet lock if you want the control plane unable to insert a node.
5. Write `stacks/edge/.env` (0600): `TS_IP` from step 2, `CF_API_TOKEN` from stage 0,
   `UPSTREAM=10.44.0.2`.
6. `make deploy`. Watch the first start in Dockge — the wildcard cert is issued over DNS-01 and
   takes a minute. A bad `CF_API_TOKEN` shows up here as an ACME failure loop.
7. Verify from the phone on cellular: `https://immich.h.malice.biz` loads with a valid cert.
   Install it as a PWA — the thing plain HTTP could not do.
8. Verify the path is direct: `tailscale ping chill-01` should report a direct connection, not
   `via DERP`. DERP means traversal failed and you are relaying.

**DNS-rebinding check — PASSED 2026-09-15.** Some resolvers refuse answers in `100.64.0.0/10`.
Tested from the phone on cellular against its own resolver, Tailscale off:
`http://immich.h.malice.biz` gave `ERR_CONNECTION_TIMED_OUT`, meaning the name resolved and
only the placeholder address was unreachable; `DNS_PROBE_FINISHED_NXDOMAIN` would have been the
failure. No tailnet nameserver override needed. Re-test if you switch carrier or enable
Private DNS / DoT — the fix would be a tailnet nameserver plus `--accept-dns` ON for phones,
which is the opposite of chill-01's setting, deliberately.

Once names resolve, set `SEARXNG_BASE_URL`, `PAPERLESS_URL` and miniflux's `BASE_URL` to their
`https://<name>.h.malice.biz` values. Own commit — Paperless rejects logins if that origin is
wrong, so you want a clean revert.

Rollback: `docker compose -p edge down`. The `10.44.0.2:<port>` URLs never stopped working.

---

## Stage 2 — wg-easy -> static two-peer kernel WireGuard

The only structural change. Replaces a peer-minting GUI, its database, and a container-hosted
tunnel with two config files.

What this deletes: the `wg-easy` container, `/opt/vps/state` and its "never delete this"
landmine, the enrollment chicken-and-egg, the `WG_CONFIG_PORT` 51822-vs-51820 confusion (a
kernel interface has one port, full stop), the `172.27.0.0/24` bridge and its static container
IP, the in-container `WG_POST_UP` masquerade, the `vpn.malice.biz` vhost, and
**`chill-fw.service` entirely** — because the tunnel moves onto the host, the VPS has
`10.44.0.0/24` on-link, so the `ip route ... via 172.27.0.2` and the `DOCKER-USER` ACCEPT both
become unnecessary. That ACCEPT is what cost two hours of Mumble downtime on 2026-09-11.

### Interface naming matters

- **chill-01 keeps `wg0`.** `host/slskd-egress.sh` hardcodes `wg0` in five places. Keep the
  name and that script needs no edit at all. Only `/etc/wireguard/wg0.conf`'s `[Peer]` block
  changes: new `PublicKey`, new `Endpoint` port. `AllowedIPs = 0.0.0.0/0`, `Table = off` and
  `PostUp = /usr/local/sbin/slskd-egress.sh` all stay exactly as documented in that script's
  header.
- **The VPS gets `chill0`, NOT `wg0`.** The VPS's `wg0` is the 10.30 arr tunnel and is
  load-bearing. `nftables.conf`'s `iifname != "wg0"` refers to that one and stays correct.

### Use a new port, 51824

wg-easy publishes `0.0.0.0:51822/udp`, so a kernel interface cannot bind 51822 while the
container is alive. Rather than juggle, give `chill0` **51824 permanently**. 51822 has no
special meaning. This turns a "stop one, start the other, hope" step into a prepare-then-flip.

### Pre-flight, in this order, before touching anything live

1. **Add an nftables input accept for `51824/udp` FIRST.** Today 51822 works only because
   Docker inserts its own accept when publishing the port. Once the tunnel is a kernel
   interface, Docker is not involved and there is no accept — the handshake will fail and you
   will debug it with public services already down. The legacy table's existing
   `kernel-WG 51820/udp accept` is the pattern to copy.
2. Read the live ruleset: `nft list ruleset > /root/ruleset.$(date +%F).bak`. Commit a copy to
   the repo as a reference snapshot. You are about to reason about rules git does not own.
3. Generate two keypairs: `wg genkey | tee priv | wg pubkey > pub` on each box. Private keys go
   to `/etc/wireguard/*.conf` at 0600 and into your password manager. Never into git.
4. Write `/etc/wireguard/chill0.conf` on the VPS from `vps/chill0.conf.example` and the new
   `wg0.conf` on chill-01, but **do not enable either yet**.
5. Back up both the current `/etc/wireguard/wg0.conf` on chill-01 and `/opt/vps/state` on the
   VPS. Take the `/opt/vps/state` copy into the restic set — every existing peer lives there
   and nothing else can recreate them.
6. Confirm you can reach the VPS out-of-band. SSH is on `4522` over `eth0` and is unaffected by
   all of this, but confirm your provider's rescue console works *before* you edit a firewall,
   not after.

### Cutover, ~2 minutes of public downtime

Do the VPS side first; chill-01 dialing a dead endpoint is harmless.

    # VPS
    cd /opt/vps && docker compose down
    systemctl disable --now chill-fw.service
    ip route del 10.44.0.0/24 2>/dev/null || true
    systemctl enable --now wg-quick@chill0
    wg show chill0

    # chill-01
    systemctl restart wg-quick@wg0
    wg show wg0        # expect a recent handshake and a peer at 194.58.47.21:51824

Then verify in this order, stopping at the first failure:

1. `ping -c3 10.44.0.2` from the VPS. If this fails, nothing else will.
2. `curl -sS -o /dev/null -w '%{http_code}' https://vault.malice.biz` — proves Caddy still
   reaches chill-01, and that Caddy's source address (now `10.44.0.1` natively, no masquerade)
   is inside chill-01's `AllowedIPs`.
3. `systemctl start homelab-public-check` on chill-01 — covers all ten public vhosts at once.
   Do not wait for the daily timer.
4. Mumble, from outside. It is the canary for the DNAT path and it is what broke last time.
5. `sudo /usr/local/sbin/slskd-egress.sh` then, inside the container,
   `curl -s https://ifconfig.me` — must print the VPS address, not your home IP. The script is
   idempotent and re-running it after a tunnel restart is expected.

### Cleanup, only after the above is green

- Delete `vps/docker-compose.yml`, `vps/docker-compose.override.yml`, `vps/chill-fw.service`
  from the repo, and their `install`/`docker compose up`/`systemctl enable` lines from
  `vps/bootstrap.sh`.
- Delete the `vpn.malice.biz` stanza from `vps/sites/chill.caddy`.
- Drop the `/opt/vps/state` pull from `host/backup.sh` and add `/etc/wireguard` in its place.
- `rm -rf /opt/vps` on the VPS, once the restic copy is confirmed restorable.
- Rewrite the wg-easy parts of `AGENTS.md` and `README.md` rather than amending them.

### Rollback

Restore chill-01's old `wg0.conf`, `systemctl restart wg-quick@wg0`; on the VPS
`systemctl disable --now wg-quick@chill0`, `cd /opt/vps && docker compose up -d`,
`systemctl enable --now chill-fw.service`. Keep both old configs on disk, not just in git
history, until this has survived a reboot of both boxes.

---

## Optional, not scheduled

- **slskd -> Gluetun.** Only if you want P2P off the VPS or dislike the 45-line iptables
  script. Gluetun with `VPN_SERVICE_PROVIDER=custom`, `VPN_TYPE=wireguard`,
  `WIREGUARD_ENDPOINT_IP=194.58.47.21` (an IP — Gluetun does not resolve hostnames) needs its
  own small wg interface on the VPS, so it trades one script for one more tunnel. Its killswitch
  is genuinely better than the blackhole route, which is the only real argument for it.
- **Tighten the DNAT rule.** `iifname != "wg0"` also matches `chill0` after stage 2. Harmless,
  but `iifname "eth0"` would be more precise. A firewall edit for a cosmetic gain — low priority.
- **Adopt `arr.caddy` into git** as `vps/sites/arr.caddy`. The "never touch it" rule exists only
  because it was hand-edited once; adopting it removes the special case permanently and makes
  the VPS fully reproducible from this repo.
