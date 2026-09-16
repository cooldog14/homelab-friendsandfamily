# homelab

These notes apply to this folder.
Keep the system simple.
Git is the source of truth.
Dockge is for editing and logs.

## design

The host is Debian 13.
Docker Compose runs the apps.

The VPS is the public entry point.
It runs Caddy and nftables.
It terminates TLS.
It proxies to chill-01 over WireGuard.

chill-01 is the home server.
It binds services to 10.44.0.2.
It also runs private Caddy on its Tailscale address.

Tailscale is for phones and laptops.
WireGuard is for the VPS link.

## network

VPS public IP is 194.58.47.21.
VPS WireGuard address is 10.44.0.1.
chill-01 WireGuard address is 10.44.0.2.

Public traffic enters the VPS.
Private traffic enters over Tailscale.
Home has no inbound internet port.

## public routes

The source of truth is vps/sites/chill.caddy.

files.1x8.me goes to 10.44.0.2:8085.
photos.1x8.me goes to 10.44.0.2:2283.
gotify.1x8.me goes to 10.44.0.2:8070.
paperless.1x8.me goes to 10.44.0.2:8092.
stirling.1x8.me goes to 10.44.0.2:8091.
kavita.1x8.me goes to 10.44.0.2:8094.
neko.1x8.me goes to 10.44.0.2:8097.
screego.1x8.me goes to 10.44.0.2:5050.

Mumble uses nftables.
Port 64738 TCP and UDP goes to chill-01.

Neko WebRTC uses nftables.
Port 52000 TCP and UDP goes to chill-01.

Screego TURN uses nftables.
Ports 3478 TCP and UDP go to chill-01.
Ports 52100 to 52200 UDP go to chill-01.

## private routes

The source of truth is stacks/edge/Caddyfile.

dockge goes to 5001.
beszel goes to 8090.

Unknown private names return 404.
Cockpit is not behind Caddy.
Use 10.44.0.2:9090.

## stacks

apps runs Filebrowser Quantum.
photos runs Immich.
docs runs Stirling PDF, Paperless, and Kavita.
comms runs Mumble, Neko, and Screego.
observability runs Gotify, Dockge, Beszel, and Beszel agent.
edge runs private Caddy.

## deploy

make deploy ships local stacks to chill-01.
It downs retired stacks, then syncs and starts active stacks.

make vps updates the VPS.
It owns public Caddy and homelab_nat.

make edge-reload validates and reloads private Caddy.

make check validates compose files and shell scripts.
It needs Docker Compose.

## secrets

Never print secrets.
Never commit secrets.
Do not use git add -A.

Secrets live on hosts.
Use .env files for stacks.
Use /etc/homelab.env for backup settings.
Use WireGuard config files for tunnel keys.
Keep secret files mode 0600.

Move secrets by file or pipe.
Verify by hash or length.
Delete temp files.

## backup

host/backup.sh is the backup entry point.
It dumps Immich and Paperless databases.
It snapshots Kavita, Gotify, Dockge, and Beszel sqlite databases.
It backs up /opt, /mnt/data, /mnt/fast/photos, /etc, and /root/.ssh.
It excludes downloads.

VPS pull failure must alert.
It must not fail the home backup.

## operations

Use vps-ingress for the VPS.
Use malice for Proxmox.
Use chill-deploy for chill-01.

VPS SSH is rate limited.
Reuse connections.

VM 101 is chill-01.

## hard rules

Never delete the chill0 WireGuard peer or /etc/wireguard on either box.
Never flush the VPS nftables ruleset.
Never bind Docker services to 0.0.0.0 unless the exception is documented.
Never add public base URLs to private-only services.
Never make an admin surface public.
