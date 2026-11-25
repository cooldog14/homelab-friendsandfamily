#!/bin/sh
# Daily proof that the direct Gotify path works. notify@.service, backup.sh's
# alert() and smartd-notify.sh all POST to ALERT_URL from /etc/homelab.env. A
# dead URL made every one of them silent for a whole VPS reboot (audit A1),
# because a failed curl only wrote to the journal. This unit fails => notify@
# (journal) and HomelabJobFailed (Prometheus -> bridge, a different token), so
# a broken ALERT_URL is reported even though this very POST cannot deliver.
set -eu

ENV_FILE=${HOMELAB_ENV_FILE:-/etc/homelab.env}
[ -r "$ENV_FILE" ] || { echo "alert-check: $ENV_FILE unreadable" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

# Never print the URL: it carries the Gotify app token in its query string.
case "${ALERT_URL:-}" in
  https://gotify.h.malice.biz/message*) ;;
  *)
    echo "alert-check: ALERT_URL is unset or not the private gotify.h/message endpoint" >&2
    exit 1
    ;;
esac

# Priority 1 keeps the daily proof quiet in the Gotify UI.
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 \
  -X POST \
  -F "title=homelab alert path self-test" \
  -F "message=Daily delivery proof from $(hostname); no action needed." \
  -F "priority=1" \
  "$ALERT_URL" || true)

if [ "$code" != 200 ]; then
  echo "alert-check: Gotify POST returned '${code}' (expected 200)" >&2
  exit 1
fi
echo "alert-check: delivery OK"
