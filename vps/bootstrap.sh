#!/bin/sh
# Debian 13 VPS: public Caddy + nftables + static kernel WireGuard
# (chill0: 10.44.0.0/24). Re-running is fine.
set -eu
cd "$(dirname "$0")"

apt-get update
apt-get install -y ca-certificates curl gnupg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy goaccess nftables unattended-upgrades wireguard
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
install -d -m 755 /var/lib/homelab-traffic
install -m 755 traffic-report.sh /usr/local/bin/homelab-traffic-report
install -m 644 homelab-traffic-report.service homelab-traffic-report.timer /etc/systemd/system/

mkdir -p /var/backups
cp -a /etc/caddy/Caddyfile "/var/backups/Caddyfile.$(date +%F-%T)" 2>/dev/null || true
tar -C /etc/caddy -czf "/var/backups/caddy-sites.$(date +%F-%T).tgz" sites 2>/dev/null || true
install -m 644 Caddyfile /etc/caddy/Caddyfile
mkdir -p /etc/caddy/sites
rm -f /etc/caddy/sites/*.caddy
install -m 644 sites/*.caddy /etc/caddy/sites/
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy

# homelab_nat is its own table: apply without touching /etc/nftables.conf
# (which carries provider/local rules). Persist via include (once):
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

# Static WireGuard (the VPS<->chill-01 link). The config lives at
# /etc/wireguard/chill0.conf (0600, host-only, never in git) — created once
# during the stage-2 cutover. This script never writes keys; it just keeps the
# link enabled across re-runs.
systemctl enable --now caddy nftables
systemctl daemon-reload
systemctl enable --now homelab-traffic-report.timer
systemctl start homelab-traffic-report.service
systemctl enable --now wg-quick@chill0 || echo "missing /etc/wireguard/chill0.conf — restore it from backup before relying on public vhosts"
echo "public vhosts live in /etc/caddy/sites; private/admin access uses Tailscale"
