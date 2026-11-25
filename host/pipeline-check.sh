#!/bin/sh
# Local watchdog for the notification pipeline. Prometheus, Alertmanager, the
# Gotify bridge and Gotify all run on chill-01, so if any of them dies nothing
# above it can evaluate or deliver. This check is independent of Prometheus:
# it uses loopback health endpoints and fails a systemd unit whose OnFailure
# goes straight to Gotify. A state file makes it page once per outage, not
# every five minutes, while the textfile gauge keeps the state visible.
set -eu

TEXTFILE_DIR=${TEXTFILE_DIR:-/var/lib/node_exporter/textfile}
STATE=${HOMELAB_ALERT_PATH_STATE:-/var/lib/homelab-alert-path.state}
OUT="$TEXTFILE_DIR/homelab-alert-path.prom"
BRIDGE=observability-alertmanager-gotify-bridge-1

p=0; a=0; b=0; g=0
curl -fsS --max-time 5 http://127.0.0.1:9091/-/healthy >/dev/null 2>&1 && p=1 || true
curl -fsS --max-time 5 http://127.0.0.1:9093/-/healthy >/dev/null 2>&1 && a=1 || true
[ "$(docker inspect -f '{{.State.Running}}' "$BRIDGE" 2>/dev/null || printf false)" = true ] && b=1 || true
curl -fsS --max-time 5 https://gotify.h.malice.biz/health >/dev/null 2>&1 && g=1 || true

mkdir -p "$TEXTFILE_DIR"
tmp="$OUT.$$"
trap 'rm -f "$tmp"' EXIT
{
  echo '# HELP homelab_alert_path_healthy Local alert pipeline component health (1=ok, 0=down)'
  echo '# TYPE homelab_alert_path_healthy gauge'
  printf 'homelab_alert_path_healthy{component="prometheus"} %s\n' "$p"
  printf 'homelab_alert_path_healthy{component="alertmanager"} %s\n' "$a"
  printf 'homelab_alert_path_healthy{component="bridge"} %s\n' "$b"
  printf 'homelab_alert_path_healthy{component="gotify"} %s\n' "$g"
} > "$tmp"
mv "$tmp" "$OUT"

if [ "$p" = 1 ] && [ "$a" = 1 ] && [ "$b" = 1 ] && [ "$g" = 1 ]; then
  printf 'ok\n' > "$STATE"
  echo "pipeline-check: prometheus/alertmanager/bridge/gotify healthy"
  exit 0
fi

echo "pipeline-check: unhealthy prometheus=$p alertmanager=$a bridge=$b gotify=$g" >&2

# First failure of an outage pages via OnFailure=notify@; later runs stay
# silent so a broken pipeline does not flood Gotify every five minutes.
if [ ! -f "$STATE" ] || grep -qx ok "$STATE"; then
  printf 'broken\n' > "$STATE"
  exit 1
fi
exit 0
