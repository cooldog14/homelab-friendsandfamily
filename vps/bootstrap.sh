#!/bin/sh
# Debian 13 VPS: the only public thing you own. Caddy (front door) + nftables
# (DNAT down the tunnel) + wg-easy in Docker (WireGuard hub, 10.44.0.0/24).
# Model is VPS-hub: clients and chill-01 all dial THIS box. Re-running is fine.
# CORRECTION 2026-09-15: the line that used to be here claiming "the old 10.30
# network is gone with VM100" was stale. The 10.30 arr network IS live (kernel
# wg on wg0:51820, arr LXC at 10.30.0.5 behind sites/arr.caddy) and it stays.
# Only the 51900 home-hub tunnel-in-tunnel design is gone; do not re-add that.
# MIGRATION.md stage 2 replaces wg-easy with a static kernel link on chill0:51824.
# DANGER (one-time, 2026-09-12): the first run after the sites/ split replaces
# the monolithic live Caddyfile. Seed /etc/caddy/sites/arr.caddy from the live
# arr route stanzas BEFORE running, then validate + curl every vhost.
# Later runs only touch repo-owned files (Caddyfile, sites/chill.caddy).
set -eu
cd "$(dirname "$0")"

apt-get update
apt-get install -y ca-certificates curl gnupg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy docker-ce docker-ce-cli containerd.io docker-compose-plugin goaccess nftables unattended-upgrades
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy

mkdir -p /var/backups
cp -a /etc/caddy/Caddyfile "/var/backups/Caddyfile.$(date +%F-%T)" 2>/dev/null || true
install -m 644 Caddyfile /etc/caddy/Caddyfile
# Split layout: repo owns the main file + sites/chill.caddy only.
# sites/arr.caddy (arr public routes, live-managed) is NEVER touched here.
mkdir -p /etc/caddy/sites
install -m 644 sites/chill.caddy /etc/caddy/sites/chill.caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy

# homelab_nat is its own table: apply without touching /etc/nftables.conf
# (which carries crowdsec + legacy rules). Persist via include (once):
#   mkdir -p /etc/nftables.d
#   install -m 644 nftables.conf /etc/nftables.d/homelab_nat.conf
#   grep -q homelab_nat /etc/nftables.conf || echo 'include "/etc/nftables.d/homelab_nat.conf"' >> /etc/nftables.conf
mkdir -p /etc/nftables.d
install -m 644 nftables.conf /etc/nftables.d/homelab_nat.conf
grep -q 'nftables.d/homelab_nat.conf' /etc/nftables.conf \
  || echo 'include "/etc/nftables.d/homelab_nat.conf"' >> /etc/nftables.conf

printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-homelab.conf
printf 'Unattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-Time "03:00";\n' > /etc/apt/apt.conf.d/51homelab
sysctl --system > /dev/null

# wg-easy (the hub). NEVER delete ./state (peers, keys, server keypair).
# .env holds WG_EASY_PASSWORD_HASH (0600, created once, never in git).
mkdir -p /opt/vps
install -m 644 docker-compose.yml docker-compose.override.yml /opt/vps/
if [ ! -f /opt/vps/.env ]; then
  echo "write WG_EASY_PASSWORD_HASH into /opt/vps/.env (0600), then: cd /opt/vps && docker compose up -d"
else
  (cd /opt/vps && docker compose up -d)
fi

# Ports: 22/80/443 delivered here; 51822/udp is wg-easy's public WireGuard.
# 64738/52000/3478/52100-52200 are DNAT'd, not delivered -- no allow needed.
# NOTE: no ufw on this box (nftables + crowdsec instead); do not add ufw lines.
# chill-fw: 10.44 host route + DOCKER-USER bypass. Without it Docker's trailing
# DROP kills all DNAT to chill-01. Must start AFTER docker (iptables chains).
install -m 644 chill-fw.service /etc/systemd/system/chill-fw.service
systemctl enable --now caddy nftables docker
systemctl enable --now chill-fw.service
echo "next: enroll phone-first via wg-easy at http://10.44.0.1:51821 over WireGuard"
