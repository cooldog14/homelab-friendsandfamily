#!/bin/sh
# External dead-man client. Runs on the VPS, checks the public edge through
# Caddy locally, then pings an external Healthchecks-style URL. A failed check
# intentionally sends no ping, so the external service alerts after its grace
# period even when the whole application VM is offline.
set -eu
ENV_FILE=${HEARTBEAT_ENV:-/etc/homelab-heartbeat.env}
SITES_DIR=${PUBLIC_CADDY_SITES_DIR:-/etc/caddy/sites}

[ -r "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
: "${HEARTBEAT_URL:?missing HEARTBEAT_URL}"

fail=0
hosts=$(find "$SITES_DIR" -type f -name '*.caddy' -exec awk '
  /^[[:space:]]*#/ { next }
  /^[[:space:]]*[[:alnum:]-]+(\.[[:alnum:]-]+)+[[:space:]]*\{/ { print $1 }
' {} + | sort -u)

[ -n "$hosts" ] || { echo "no public hosts found" >&2; exit 1; }

while IFS= read -r host; do
  [ -n "$host" ] || continue
  code=$(curl -sS --max-time 15 --resolve "$host:443:127.0.0.1" \
    -o /dev/null -w '%{http_code}' "https://$host" 2>/dev/null || true)
  case "$code" in
    2*|3*|401) ;;
    *) echo "FAIL $code https://$host" >&2; fail=1 ;;
  esac
done <<EOF
$hosts
EOF

for port in 64738 52000 3478 25565; do
  if ! timeout 5 bash -c ":</dev/tcp/10.44.0.2/$port" 2>/dev/null; then
    echo "FAIL tcp 10.44.0.2:$port" >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "edge check failed; heartbeat withheld" >&2
  exit 1
fi

curl -fsS --max-time 10 --retry 3 "$HEARTBEAT_URL" >/dev/null
echo "edge healthy; heartbeat sent"
