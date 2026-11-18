#!/bin/sh
# smartd -M exec helper. Post SMART messages through the existing Gotify
# ALERT_URL on the hypervisor. Never print the URL or the token.
set -eu

[ -r /etc/homelab.env ] || { logger -p user.err "smartd alert: /etc/homelab.env missing"; exit 1; }
# shellcheck source=/dev/null
. /etc/homelab.env
[ -n "${ALERT_URL:-}" ] || { logger -p user.err "smartd alert: ALERT_URL unset"; exit 1; }

msg=$(printf '%s\n' "$*")
if [ -n "${SMARTD_DEVICE:-}" ]; then
  msg="SMART ${SMARTD_DEVICE}: ${msg}"
fi

curl -fsS --max-time 10 -X POST \
  -F "title=SMART warning on $(hostname)" \
  -F "message=${msg}" \
  -F "priority=8" \
  "$ALERT_URL" >/dev/null || {
    logger -p user.err "smartd alert delivery failed"
    exit 1
  }
