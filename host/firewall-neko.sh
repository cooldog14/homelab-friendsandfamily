#!/bin/sh
# DOCKER-USER isolation for the Neko browser container.
#
# UFW never sees Docker-published ports: the DOCKER chain jumps before
# ufw-user-input, so UFW rules cannot gate them. Neko's browser (comms bridge)
# otherwise reaches every 10.44.0.2 published admin port and Cockpit.
#
# Idempotent: flush our marker rules, re-add. Prints "changed" or "unchanged"
# so Ansible reports state without guessing.
set -eu

MARKER=homelab-neko-block
SAVED=/etc/iptables/rules.v4

blocked_rules() {
  iptables -S DOCKER-USER 2>/dev/null | grep "$MARKER" | sort || true
}

if ! command -v docker >/dev/null 2>&1 || ! command -v iptables >/dev/null 2>&1; then
  echo "skipped: docker or iptables missing"
  exit 0
fi

before=$(blocked_rules)

while iptables -S DOCKER-USER 2>/dev/null | grep -q "$MARKER"; do
  rule=$(iptables -S DOCKER-USER 2>/dev/null | grep "$MARKER" | head -1 | sed 's/^-A/-D/')
  # shellcheck disable=SC2086
  iptables $rule 2>/dev/null || break
done

edge_br=$(docker network inspect edge_default --format '{{.Id}}' 2>/dev/null | cut -c1-12 | sed 's/^/br-/')
if [ -z "$edge_br" ]; then
  echo "edge_default missing, skipping DOCKER-USER" >&2
  exit 0
fi

# Every br-* EXCEPT edge's. comms_default is ephemeral (not pinned), so match by
# interface wildcard instead of a fixed subnet.
for path in /sys/class/net/br-*; do
  [ -e "$path" ] || continue
  br=${path##*/}
  [ "$br" = "$edge_br" ] && continue
  # Pre-DNAT host IPs: blocks direct host services (Cockpit :9090 via
  # 172.17.0.1, beszel-agent, LAN, tailnet).
  for dst in 10.44.0.2 172.17.0.1 192.168.1.0/24 100.64.0.0/10; do
    iptables -I DOCKER-USER -i "$br" -d "$dst" -m comment --comment "$MARKER" -j DROP 2>/dev/null || true
  done
  # Post-DNAT cross-bridge: DNAT rewrites dst before filter, so the rules above
  # miss published-port traffic. Block container->other-bridge instead. Safe:
  # every cross-service reference is same-stack DNS (gotenberg/tika/navidrome/
  # redis) or edge->published-port, and edge is exempt.
  # (Proven 2026-11-03: pre-DNAT-only left :5030 open.)
  for other_path in /sys/class/net/br-*; do
    [ -e "$other_path" ] || continue
    other=${other_path##*/}
    [ "$other" = "$br" ] && continue
    [ "$other" = "$edge_br" ] && continue
    iptables -I DOCKER-USER -i "$br" -o "$other" -m comment --comment "$MARKER" -j DROP 2>/dev/null || true
  done
done

# Persist across reboot (iptables-restore reads this on chill-01).
mkdir -p /etc/iptables
iptables-save > "$SAVED" 2>/dev/null || true

after=$(blocked_rules)
if [ "$before" = "$after" ]; then
  echo unchanged
else
  echo changed
fi
