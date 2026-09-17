# homelab

Git is the source of truth.
chill-01 VM 101 runs the apps.
The VPS is the public edge.

## design

chill-01 is Debian 13.
Docker Compose runs the stacks in `/opt/stacks`.

The VPS runs Caddy and nftables.
It terminates public TLS.
It proxies to chill-01 over WireGuard.

Tailscale is the only private/admin entry point for people.
WireGuard is only the VPS `<->` chill-01 infrastructure link.

## network

VPS public IP is `194.58.47.21`.
VPS WireGuard address is `10.44.0.1`.
chill-01 WireGuard address is `10.44.0.2`.

Public traffic enters the VPS.
Private/admin traffic enters over Tailscale.
Home has no inbound internet port.

## public routes

The source of truth is `vps/sites/*.caddy`.

- files.malice.biz -> 10.44.0.2:8085
- photos.malice.biz -> 10.44.0.2:2283
- gotify.malice.biz -> 10.44.0.2:8070
- paperless.malice.biz -> 10.44.0.2:8092
- stirling.malice.biz -> 10.44.0.2:8091
- kavita.malice.biz -> 10.44.0.2:8094
- neko.malice.biz -> 10.44.0.2:8097
- screego.malice.biz -> 10.44.0.2:5050
- jellyfin.malice.biz -> 10.44.0.2:8096
- requests.malice.biz -> 10.44.0.2:5055
- player.malice.biz -> 10.44.0.2:9180
- fiesta.malice.biz -> 10.44.0.2:5274
- upload.malice.biz -> 10.44.0.2:5000
- nvdr.malice.biz -> 10.44.0.2:4533

Mumble uses nftables.
Port 64738 TCP and UDP goes to chill-01.

Neko WebRTC uses nftables.
Port 52000 TCP and UDP goes to chill-01.

Screego TURN uses nftables.
Ports 3478 TCP and UDP go to chill-01.
Ports 52100 to 52200 UDP go to chill-01.

## private routes

The source of truth is `stacks/edge/Caddyfile`.
These names are tailnet-only under `h.malice.biz`.

- home.h.malice.biz
- dockge.h.malice.biz
- beszel.h.malice.biz
- qbittorrent.h.malice.biz
- prowlarr.h.malice.biz
- radarr.h.malice.biz
- sonarr.h.malice.biz
- bazarr.h.malice.biz
- slskd.h.malice.biz
- wrtag.h.malice.biz

Unknown private names return 404.

## stacks

- apps: Filebrowser Quantum
- photos: Immich
- docs: Stirling PDF, Paperless, Kavita
- comms: Mumble, Neko, Screego
- media: Jellyfin, qBittorrent, Prowlarr, Radarr, Sonarr, Bazarr, Jellyseerr, Navidrome, Octo-Fiesta, Feishin, DUFS, slskd, wrtag
- observability: Gotify, Dockge, Beszel, Beszel agent
- edge: private Caddy and homepage

## deploy

`make deploy` ships local stacks to chill-01.
It downs retired stacks, syncs git-owned files, then starts active stacks.

`make vps` updates the VPS.
It owns public Caddy site files and homelab nftables.

`make edge-reload` validates and restarts private Caddy.

`make check` validates compose files and shell scripts.
It needs Docker Compose and shellcheck.

## secrets

Never print secrets.
Never commit secrets.
Do not use `git add -A`.

Secrets live on hosts.
Use `.env` files for stacks.
Use `/etc/homelab.env` for backup settings.
Use WireGuard config files only for the VPS `<->` chill-01 tunnel.
Keep secret files mode 0600.

## backup

`host/backup.sh` is the backup entry point.
It dumps Immich and Paperless databases.
It snapshots Kavita, Gotify, Dockge, and Beszel sqlite databases.
It backs up `/opt`, `/mnt/data`, `/mnt/fast/photos`, `/etc`, and `/root/.ssh`.
It excludes downloads, movies, and TV.

VPS pull failure must alert.
It must not fail the home backup.

## old media cleanup

Media now lives in `stacks/media`; the old LXC 203 media deployment is retired.
Stop it before starting `stacks/media` on chill-01.
Remove old 10.30 WireGuard and nftables rules from the VPS after confirming nothing uses them.
Archive or remove the old `homelab-media` checkout after this repo is deployed.

## operations

Use `vps-ingress` for the VPS.
Use `malice` for Proxmox.
Use `chill-deploy` for chill-01.

VPS SSH is rate limited.
Reuse connections.

VM 101 is chill-01.

## hard rules

Never delete the VPS `<->` chill-01 WireGuard configs or `/etc/wireguard` on either box.
Never flush the VPS nftables ruleset.
Never bind Docker services to `0.0.0.0` unless the exception is documented.
Never add public base URLs to private-only services.
Never make an admin surface public.
