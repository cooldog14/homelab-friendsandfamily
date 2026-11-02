#!/bin/sh
# Debian 13 -> homelab. Run as root from this dir. Re-running is fine.
# No Caddy and nothing on 80/443: the VPS is the front door, this box only talks over wg0.
set -eu
cd "$(dirname "$0")"
# /etc/os-release lives on the host, not in git
# shellcheck disable=SC1091
deb=$(. /etc/os-release && echo "$VERSION_CODENAME")

apt-get update
apt-get install -y ca-certificates curl
curl -fsSL https://download.docker.com/linux/debian/gpg -o /usr/share/keyrings/docker.asc
echo "deb [signed-by=/usr/share/keyrings/docker.asc] https://download.docker.com/linux/debian $deb stable" > /etc/apt/sources.list.d/docker.list
curl -fsSL "https://pkgs.tailscale.com/stable/debian/$deb.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian $deb main" > /etc/apt/sources.list.d/tailscale.list
apt-get update
# wireguard is permanent, not transitional: wg0 carries the VPS return path for
# chill public vhosts. Tailscale is for roaming devices only.
apt-get install -y cockpit docker-ce docker-compose-plugin qemu-guest-agent restic shellcheck sqlite3 tailscale ufw unattended-upgrades wireguard

install -d /opt/stacks
# Restart docker only when its config actually changed: an unconditional
# restart flaps every container (and trips the public black-box check).
daemon_changed=0
cmp -s host/daemon.json /etc/docker/daemon.json || daemon_changed=1
install -m 644 host/daemon.json /etc/docker/daemon.json
install -m 755 host/backup.sh /usr/local/bin/homelab-backup
install -m 755 host/backup-watchdog.sh /usr/local/bin/homelab-backup-watchdog
install -m 755 host/public-check.sh /usr/local/bin/homelab-public-check
PUBLIC_SITES_SRC=public-sites
[ -d "$PUBLIC_SITES_SRC" ] || PUBLIC_SITES_SRC=vps/sites
install -d -m 0755 /usr/local/share/homelab-public-sites
rm -f /usr/local/share/homelab-public-sites/*.caddy
install -m 644 "$PUBLIC_SITES_SRC"/*.caddy /usr/local/share/homelab-public-sites/
install -m 644 host/homelab-backup.service host/homelab-backup.timer host/homelab-backup-watchdog.service host/homelab-backup-watchdog.timer host/homelab-public-check.service host/homelab-public-check.timer host/homelab-docker-prune.service host/homelab-docker-prune.timer 'host/notify@.service' /etc/systemd/system/
# LAN keeps password SSH (no key needed on the home network); everywhere else
# stays key-only, root never logs in directly.
printf 'PasswordAuthentication no\nPermitRootLogin no\nMatch Address 192.168.1.0/24\n    PasswordAuthentication yes\n' > /etc/ssh/sshd_config.d/homelab.conf
printf 'Unattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-Time "04:30";\n' > /etc/apt/apt.conf.d/51homelab
ensure_virtiofs() {
  tag=$1
  target=$2
  # Takeover guard (2026-11-02): /mnt/data is a pool bind, not virtiofs.
  # Never append over a live bind: check the mountpoint first.
  if grep -Eq "[[:space:]]${target}[[:space:]]" /etc/fstab; then
    echo "ensure_virtiofs: $target already in fstab, skipping $tag" >&2
    return 0
  fi
  # Match the full mount line, not a substring: "pve1-primary" also appears in
  # paths like /mnt/pool/takeover-primary, and a loose match skips the append.
  grep -qE "^${tag}[[:space:]]+${target}[[:space:]]" /etc/fstab \
    || echo "$tag $target virtiofs rw,relatime,nofail 0 0" >> /etc/fstab
}
# NOTE (2026-11-02): /mnt/data as a pool bind IS the live layout (takeover).
# Never auto-delete it: the guard above skips ensure_virtiofs when present.
# Renamed 2026-09-30: migrate old tags before ensuring the new ones.
sed -i 's|pve1-mirror /mnt/data|pve1-primary /mnt/data|' /etc/fstab
sed -i 's|pve1-archive /mnt/vault|pve1-vault /mnt/vault|' /etc/fstab
ensure_virtiofs pve1-primary /mnt/data
ensure_virtiofs pve1-fast /mnt/fast
ensure_virtiofs pve1-vault /mnt/vault
ensure_virtiofs pve1-pool /mnt/pool
ensure_virtiofs pve1-backup /mnt/backup
mkdir -p /mnt/data /mnt/fast /mnt/vault /mnt/pool /mnt/backup && mount -a
rmdir /mnt/archive 2>/dev/null || true
install -d -m 0755 -o 1000 -g 1000 /mnt/fast/jellyfin-cache /mnt/fast/scratch /mnt/fast/imports
install -d -m 0700 /mnt/fast/dumps

printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-homelab.conf
sysctl --system > /dev/null

# Humans use Tailscale/private Caddy for admin apps.
# Public app traffic arrives over the wg0 tunnel from the VPS.
# No DNS service here.
# LAN keeps plain SSH (no Tailscale/key needed on the home network).
ufw allow in on eth0 from 192.168.1.0/24 to any port 22 2>/dev/null || true
ufw delete allow 53/tcp 2>/dev/null || true
ufw delete allow 53/udp 2>/dev/null || true
# Cockpit is host admin + web terminal. Keep it a people-only path:
# tailscale0 allow covers direct tailnet clients; 172.18.0.0/16 covers ONLY
# the pinned edge_default subnet (edge Caddy proxies cockpit.h via
# host.docker.internal → 172.17.0.1 → host 9090); wg0 deny keeps it off the
# VPS/WireGuard path. Never widen back to 172.16/12: Neko (comms bridge)
# users would reach Cockpit + web terminal (audit CHILL-2).
ufw delete deny in on wg0 to any port 9090 2>/dev/null || true
ufw insert 1 deny in on wg0 to any port 9090
ufw delete allow from 172.16.0.0/12 to any port 9090 proto tcp 2>/dev/null || true
ufw allow from 172.18.0.0/16 to any port 9090 proto tcp
# Beszel agent (host netns :45876): hub connects over its compose bridge.
# Docker assigns bridge subnets dynamically, so keep the /12 source (found
# 2026-10-30: pinning one bridge killed monitoring on recreation).
ufw allow from 172.16.0.0/12 to any port 45876 proto tcp
ufw allow in on wg0 && ufw allow in on tailscale0 && ufw --force enable
# DOCKER-USER: UFW never sees Docker-published ports (DOCKER chain jumps
# before ufw-user-input). Neko's browser (comms_default, currently
# 172.19.0.0/16) reaches every 10.44.0.2 published admin port + Cockpit
# without this. Idempotent: flush our marker comment, re-add.
# NOTE: comms_default is NOT pinned (ephemeral) — match by interface
# wildcard instead: every br-* EXCEPT edge's gets the drop. Edge bridge
# name resolves at runtime via docker network inspect.
if command -v docker >/dev/null 2>&1 && command -v iptables >/dev/null 2>&1; then
  iptables -S DOCKER-USER 2>/dev/null | grep -q 'homelab-neko-block' && \
    while iptables -S DOCKER-USER 2>/dev/null | grep -q 'homelab-neko-block'; do
      rule=$(iptables -S DOCKER-USER 2>/dev/null | grep 'homelab-neko-block' | head -1 | sed 's/^-A/-D/')
      # shellcheck disable=SC2086
      iptables $rule 2>/dev/null || break
    done
  edge_br=$(docker network inspect edge_default --format '{{.Id}}' 2>/dev/null | cut -c1-12 | sed 's/^/br-/')
  if [ -z "$edge_br" ]; then echo "edge_default missing, skipping DOCKER-USER" >&2; else
  # shellcheck disable=SC2010
  for br in $(ls /sys/class/net/ | grep '^br-'); do
    [ "$br" = "$edge_br" ] && continue
    for dst in 10.44.0.2 172.17.0.1 192.168.1.0/24 100.64.0.0/10; do
      iptables -I DOCKER-USER -i "$br" -d "$dst" -m comment --comment homelab-neko-block -j DROP 2>/dev/null || true
    done
  done
  fi
  # Persist across reboot (iptables-restore service reads this on chill-01).
  mkdir -p /etc/iptables && iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
fi
# LAN-only media playback (e.g. Jellyfin 8096 bound to the LAN IP in compose,
# never 0.0.0.0). Scoped to the home subnet; nothing internet-facing changes.
ufw allow in on eth0 from 192.168.1.0/24 to any port 8096 2>/dev/null || true

systemctl daemon-reload
if [ "$daemon_changed" -eq 1 ]; then
  systemctl restart docker
else
  echo "daemon.json unchanged, skipping docker restart"
fi
systemctl reload ssh
systemctl enable --now qemu-guest-agent tailscaled cockpit.socket homelab-backup.timer homelab-backup-watchdog.timer homelab-public-check.timer homelab-docker-prune.timer
# Beszel agent (host netns, :45876): hub connects via 172.17.0.1, so the
# agent must LISTEN there (not 127.0.0.1) and UFW must allow the
# observability bridge. Never positional `ufw delete N` (audit CHILL-5).
ufw delete allow 45876/tcp 2>/dev/null || true
ufw allow from 172.20.0.0/16 to 172.17.0.1 port 45876 proto tcp 2>/dev/null || true
# wg0 is the static VPS<->chill-01 tunnel. Keep /etc/wireguard/wg0.conf at
# 0600, then: systemctl enable --now wg-quick@wg0
# tailscaled is installed and running but unauthenticated: join the tailnet once,
# by hand, then it persists. `--accept-dns=false` keeps the host resolver alone
# (same reason AdGuard went away). Read the IP back for stacks/edge/.env:
#   tailscale up --accept-dns=false --hostname=chill-01 && tailscale ip -4
echo "next: tailscale up, write /etc/homelab.env + stacks/edge/.env, then make deploy"
