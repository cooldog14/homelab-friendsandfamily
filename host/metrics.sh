#!/bin/sh
set -eu
DIR=${TEXTFILE_DIR:-/var/lib/node_exporter/textfile}
mkdir -p "$DIR"
tmp="$DIR/homelab.prom.$$"
trap 'rm -f "$tmp"' EXIT
{
  echo '# HELP homelab_backup_last_success_timestamp_seconds Derniere sauvegarde restic reussie'
  echo '# TYPE homelab_backup_last_success_timestamp_seconds gauge'
  if [ -s /var/lib/homelab-backup.last-ok ]; then
    ts=$(date -d "$(cat /var/lib/homelab-backup.last-ok)" +%s)
    echo "homelab_backup_last_success_timestamp_seconds $ts"
  fi
  echo '# HELP homelab_wireguard_latest_handshake_seconds Dernier handshake WireGuard par pair'
  echo '# TYPE homelab_wireguard_latest_handshake_seconds gauge'
  if command -v wg >/dev/null 2>&1; then
    wg show wg0 latest-handshakes 2>/dev/null | while read -r peer ts; do
      [ -n "$peer" ] || continue
      echo "homelab_wireguard_latest_handshake_seconds{peer=\"$peer\"} $ts"
    done
  fi
} > "$tmp"
mv "$tmp" "$DIR/homelab.prom"
