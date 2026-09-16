# homelab

Debian 13 home server.
Docker Compose runs the apps.
The VPS is the public entry point.
WireGuard connects the VPS to the home server.
Tailscale connects personal devices to private services.

## hosts

The VPS is public.
It runs Caddy, nftables, Docker, and CrowdSec.
It owns public TLS.
It holds 10.44.0.1 on kernel interface chill0 (51824/udp, static config in /etc/wireguard).

chill-01 is private.
It has address 10.44.0.2 on WireGuard.
It has a Tailscale address for private names.
It binds services to 10.44.0.2.
It does not accept internet traffic directly.

## public services

files.malice.biz
photos.malice.biz
gotify.malice.biz
paperless.malice.biz
stirling.malice.biz
kavita.malice.biz
neko.malice.biz
screego.malice.biz

Mumble uses TCP and UDP port 64738.

## private services

Private names use the tailnet Caddy.
They are under h.1x8.me.
The map lives in stacks/edge/Caddyfile.
Unknown private names return 404.

dockge.h.1x8.me
beszel.h.1x8.me

Cockpit stays raw.
Use 10.44.0.2:9090.

## stacks

apps runs Filebrowser Quantum.
photos runs Immich.
docs runs Stirling PDF, Paperless, and Kavita.
comms runs Mumble, Neko, and Screego.
observability runs Gotify, Dockge, Beszel, and the Beszel agent.
edge runs private Caddy.

## deploy

Edit files.
Commit and push.
Run make deploy.
Run make vps after public Caddy or nftables changes.
Run make edge-reload after private Caddy changes.
Run make check before pushing when Docker Compose is available.

## rules

No secrets in git.
Secrets live in .env files and host config files.
Keep secret files mode 0600.

Do not delete the chill0 WireGuard peer or /etc/wireguard on either box.
Do not put a peer endpoint inside AllowedIPs.
Do not expose admin surfaces publicly.
Keep Tailscale key expiry disabled for chill-01.
