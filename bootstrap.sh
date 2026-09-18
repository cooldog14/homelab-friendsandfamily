#!/bin/sh
# Debian 13 -> homelab. Run as root from this dir. Re-running is fine.
# No Caddy and nothing on 80/443: the VPS is the front door, this box only talks over wg0.
set -eu
cd "$(dirname "$0")"
# /etc/os-release lives on the host, not in git
# shellcheck disable=SC1091
deb=$(. /etc/os-release && echo "$VERSION_CODENAME")

apt-get update
apt-get install -y ca-certificates curl gnupg
curl -fsSL https://download.docker.com/linux/debian/gpg -o /usr/share/keyrings/docker.asc
echo "deb [signed-by=/usr/share/keyrings/docker.asc] https://download.docker.com/linux/debian $deb stable" > /etc/apt/sources.list.d/docker.list
curl -fsSL "https://pkgs.tailscale.com/stable/debian/$deb.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian $deb main" > /etc/apt/sources.list.d/tailscale.list
apt-get update
# wireguard is permanent, not transitional: wg0 carries the VPS return path for
# chill public vhosts. Tailscale is for roaming devices only.
apt-get install -y docker-ce docker-compose-plugin git qemu-guest-agent restic sqlite3 tailscale ufw unattended-upgrades wireguard
systemctl disable --now cockpit.socket 2>/dev/null || true
rm -rf /etc/systemd/system/cockpit.socket.d
apt-get purge -y cockpit cockpit-bridge cockpit-system cockpit-ws 2>/dev/null || true

install -d /opt/stacks /opt/dumps
# Restart docker only when its config actually changed: an unconditional
# restart flaps every container (and trips the public black-box check).
old_daemon=$(md5sum /etc/docker/daemon.json 2>/dev/null | cut -d' ' -f1 || true)
install -m 644 host/daemon.json /etc/docker/daemon.json
new_daemon=$(md5sum /etc/docker/daemon.json | cut -d' ' -f1)
install -m 755 host/backup.sh /usr/local/bin/homelab-backup
install -m 755 host/backup-watchdog.sh /usr/local/bin/homelab-backup-watchdog
install -m 755 host/public-check.sh /usr/local/bin/homelab-public-check
install -m 644 host/homelab-backup.service host/homelab-backup.timer host/homelab-backup-watchdog.service host/homelab-backup-watchdog.timer host/homelab-public-check.service host/homelab-public-check.timer 'host/notify@.service' /etc/systemd/system/
systemctl disable --now homelab-disk-usage.timer 2>/dev/null || true
rm -f /usr/local/bin/homelab-disk-usage /etc/systemd/system/homelab-disk-usage.service /etc/systemd/system/homelab-disk-usage.timer
printf 'PasswordAuthentication no\nPermitRootLogin no\n' > /etc/ssh/sshd_config.d/homelab.conf
printf 'Unattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-Time "03:00";\n' > /etc/apt/apt.conf.d/51homelab
grep -q pve1-mirror /etc/fstab || echo 'pve1-mirror /mnt/data virtiofs rw,relatime,nofail 0 0' >> /etc/fstab
grep -q pve1-fast /etc/fstab || echo 'pve1-fast /mnt/fast virtiofs rw,relatime,nofail 0 0' >> /etc/fstab
grep -q pve1-archive /etc/fstab || echo 'pve1-archive /mnt/archive virtiofs rw,relatime,nofail 0 0' >> /etc/fstab
grep -q pve1-pool /etc/fstab || echo 'pve1-pool /mnt/pool virtiofs rw,relatime,nofail 0 0' >> /etc/fstab
mkdir -p /mnt/data /mnt/fast /mnt/archive /mnt/pool && mount -a

printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-homelab.conf
sysctl --system > /dev/null

# 22 is for LAN admin. Humans use Tailscale/private Caddy for admin apps.
# Public app traffic arrives over the wg0 tunnel from the VPS.
# No DNS service here.
ufw delete allow 53/tcp 2>/dev/null || true
ufw delete allow 53/udp 2>/dev/null || true
ufw allow 22/tcp && ufw allow in on wg0 && ufw allow in on tailscale0 && ufw --force enable

systemctl daemon-reload
if [ "$old_daemon" != "$new_daemon" ]; then
  systemctl restart docker
else
  echo "daemon.json unchanged, skipping docker restart"
fi
systemctl reload ssh
systemctl enable --now qemu-guest-agent tailscaled homelab-backup.timer homelab-backup-watchdog.timer homelab-public-check.timer
# wg0 is the static VPS<->chill-01 tunnel. Keep /etc/wireguard/wg0.conf at
# 0600, then: systemctl enable --now wg-quick@wg0
# tailscaled is installed and running but unauthenticated: join the tailnet once,
# by hand, then it persists. `--accept-dns=false` keeps the host resolver alone
# (same reason AdGuard went away). Read the IP back for stacks/edge/.env:
#   tailscale up --accept-dns=false --hostname=chill-01 && tailscale ip -4
echo "next: tailscale up, write /etc/homelab.env + stacks/edge/.env, then make deploy"
