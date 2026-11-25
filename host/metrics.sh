#!/bin/sh
# Textfile metrics for node_exporter: backup markers, WireGuard handshakes and
# the systemd job guard. Runs on chill-01 and on the hypervisor; units that do
# not exist on a host are skipped, so one script serves both.
set -eu
DIR=${TEXTFILE_DIR:-/var/lib/node_exporter/textfile}
mkdir -p "$DIR"
tmp="$DIR/homelab.prom.$$"
trap 'rm -f "$tmp"' EXIT

# systemd prints LastTriggerUSec/NextElapseUSecRealtime in the C locale, which
# is the only format `date -d` parses predictably.
LC_ALL=C
export LC_ALL

HOST=${HOST_LABEL:-$(hostname)}
now=$(date +%s)

marker() {
  src=$1
  file=$2
  [ -s "$file" ] || return 0
  ts=$(date -d "$(cat "$file")" +%s 2>/dev/null || true)
  [ -n "${ts:-}" ] || return 0
  echo "homelab_backup_last_success_timestamp_seconds{host=\"$HOST\",source=\"$src\"} $ts"
}

to_epoch() {
  case "${1:-}" in
    ''|n/a) echo 0; return 0 ;;
  esac
  date -d "$1" +%s 2>/dev/null || echo 0
}

job_metrics() {
  timer=$1
  service=$2
  task=$3
  load=$(systemctl show "$timer" -p LoadState --value 2>/dev/null || true)
  [ "$load" = "loaded" ] || return 0

  active=0
  if systemctl is-active --quiet "$timer"; then active=1; fi

  show=$(systemctl show "$timer" -p LastTriggerUSec -p NextElapseUSecRealtime 2>/dev/null || true)
  last_run=$(to_epoch "$(printf '%s\n' "$show" | sed -n 's/^LastTriggerUSec=//p')")
  next_run=$(to_epoch "$(printf '%s\n' "$show" | sed -n 's/^NextElapseUSecRealtime=//p')")

  svc_show=$(systemctl show "$service" -p Result -p ExecMainStatus 2>/dev/null || true)
  result=$(printf '%s\n' "$svc_show" | sed -n 's/^Result=//p')
  code=$(printf '%s\n' "$svc_show" | sed -n 's/^ExecMainStatus=//p')
  [ -n "$code" ] || code=0

  failed=0
  case "$result" in
    ''|success) ;;
    *) failed=1 ;;
  esac
  if [ "$code" != "0" ]; then failed=1; fi

  missed=0
  if [ "$active" = 1 ] && [ "$next_run" -gt 0 ] && [ $((now - next_run)) -gt 900 ]; then
    missed=1
  fi

  echo "homelab_job_timer_active{host=\"$HOST\",task=\"$task\"} $active"
  echo "homelab_job_last_run_timestamp_seconds{host=\"$HOST\",task=\"$task\"} $last_run"
  echo "homelab_job_next_run_timestamp_seconds{host=\"$HOST\",task=\"$task\"} $next_run"
  echo "homelab_job_last_exit_code{host=\"$HOST\",task=\"$task\"} $code"
  echo "homelab_job_failed{host=\"$HOST\",task=\"$task\"} $failed"
  echo "homelab_job_missed{host=\"$HOST\",task=\"$task\"} $missed"
}

{
  echo '# HELP homelab_backup_last_success_timestamp_seconds Derniere sauvegarde restic reussie'
  echo '# TYPE homelab_backup_last_success_timestamp_seconds gauge'
  marker homelab /var/lib/homelab-backup.last-ok
  marker malice /var/lib/malice-restic-backup.last-ok

  echo '# HELP homelab_wireguard_latest_handshake_seconds Dernier handshake WireGuard par pair'
  echo '# TYPE homelab_wireguard_latest_handshake_seconds gauge'
  if command -v wg >/dev/null 2>&1; then
    wg show wg0 latest-handshakes 2>/dev/null | while read -r peer ts; do
      [ -n "$peer" ] || continue
      echo "homelab_wireguard_latest_handshake_seconds{peer=\"$peer\"} $ts"
    done
  fi

  echo '# HELP homelab_job_timer_active Timer systemd arme (1) ou non (0)'
  echo '# TYPE homelab_job_timer_active gauge'
  echo '# HELP homelab_job_last_run_timestamp_seconds Date du dernier declenchement'
  echo '# TYPE homelab_job_last_run_timestamp_seconds gauge'
  echo '# HELP homelab_job_next_run_timestamp_seconds Date du prochain declenchement'
  echo '# TYPE homelab_job_next_run_timestamp_seconds gauge'
  echo '# HELP homelab_job_last_exit_code Code de sortie du service'
  echo '# TYPE homelab_job_last_exit_code gauge'
  echo '# HELP homelab_job_failed Le dernier run a echoue'
  echo '# TYPE homelab_job_failed gauge'
  echo '# HELP homelab_job_missed Le timer est actif mais son echeance est passee'
  echo '# TYPE homelab_job_missed gauge'
  job_metrics homelab-backup.timer homelab-backup.service backup
  job_metrics homelab-backup-watchdog.timer homelab-backup-watchdog.service backup-watchdog
  job_metrics homelab-public-check.timer homelab-public-check.service public-check
  job_metrics homelab-docker-prune.timer homelab-docker-prune.service docker-prune
  job_metrics homelab-metrics.timer homelab-metrics.service metrics
  job_metrics homelab-restic-check.timer homelab-restic-check.service restic-check
  job_metrics homelab-backup-stats.timer homelab-backup-stats.service backup-stats
  job_metrics malice-restic-backup.timer malice-restic-backup.service malice-backup
  job_metrics malice-restic-check.timer malice-restic-check.service malice-restic-check
  job_metrics homelab-music-import.timer homelab-music-import.service music-import
  job_metrics homelab-alert-check.timer homelab-alert-check.service alert-check
  job_metrics homelab-pipeline-check.timer homelab-pipeline-check.service pipeline-check
} > "$tmp"
mv "$tmp" "$DIR/homelab.prom"
