#!/bin/sh
# Backup watchdog: the backup timer failing silently (disabled, masked) is the
# one hole OnFailure can't cover. This fails (=> notify@) when the nightly
# backup hasn't succeeded in 48h or its timer isn't active.
set -eu
STAMP=/var/lib/homelab-backup.last-ok
if ! systemctl is-active --quiet homelab-backup.timer; then
  echo "watchdog: homelab-backup.timer not active" >&2
  exit 1
fi
if [ ! -f "$STAMP" ]; then
  echo "watchdog: no successful backup yet ($STAMP missing)" >&2
  exit 1
fi
# find -mmin avoids date(1) parsing portability issues.
if [ -n "$(find "$STAMP" -mmin +2880 2>/dev/null)" ]; then
  echo "watchdog: last successful backup older than 48h" >&2
  exit 1
fi
echo "watchdog: backup timer active, last success within 48h"
