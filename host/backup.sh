#!/bin/sh
# Nightly restic. Dump live DBs first, else a restore is a coin flip.
# Says nothing when it works; systemd OnFailure handles the other case.
set -eu
# systemd oneshot has no HOME/XDG_CACHE_HOME; restic needs a cache dir.
export HOME="${HOME:-/root}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/root/.cache}"
# /etc/homelab.env lives on the host, not in git
set -a
# shellcheck source=/dev/null
. /etc/homelab.env
set +a
mountpoint -q /mnt/data
mountpoint -q /mnt/fast
DUMP_DIR=/mnt/fast/dumps
mkdir -p "$DUMP_DIR"
chmod 700 "$DUMP_DIR"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
alert() {
  curl -fsS -X POST -F "message=$1" -F "priority=5" "${ALERT_URL:-}" > /dev/null 2>&1 || true
}

# VPS pull (Caddy, nftables, WireGuard identity) so restic carries it to cloud.
# Fail-open: a dark VPS must not kill the home backup. Data never lands in git.
VPS_BAK=/opt/vps-backup
mkdir -p "$VPS_BAK"
VPS_SSH="ssh -i /root/.ssh/vps-backup -p 4522 -o BatchMode=yes -o ConnectTimeout=15 root@194.58.47.21"
if $VPS_SSH "sudo cat /etc/caddy/Caddyfile" > "$VPS_BAK/Caddyfile" 2>/dev/null \
&& $VPS_SSH "sudo cat /etc/nftables.conf" > "$VPS_BAK/nftables.conf" 2>/dev/null \
&& rm -rf "$VPS_BAK/wireguard" \
&& scp -i /root/.ssh/vps-backup -P 4522 -o BatchMode=yes -o ConnectTimeout=15 -r "root@194.58.47.21:/etc/wireguard" "$VPS_BAK/wireguard" 2>/dev/null; then
  chmod 700 "$VPS_BAK"; chmod 600 "$VPS_BAK/Caddyfile" "$VPS_BAK/nftables.conf" 2>/dev/null
  chmod 700 "$VPS_BAK/wireguard" 2>/dev/null; chmod 600 "$VPS_BAK/wireguard/"* 2>/dev/null
  log "vps pull ok"
else
  log "vps pull FAILED (continuing backup without it)"
  # Fail-open for data, fail-loud for awareness: a config drift during a VPS outage
  # would otherwise vanish silently. Never fail the backup over this.
  alert "vps pull FAILED on $(hostname) (backup continuing without VPS config)"
fi

pg_dump_container() {
  container=$1
  out=$2
  if ! docker exec "$container" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$out.new"; then
    rm -f "$out.new"
    log "postgres dump FAILED: $container"
    return 1
  fi
  mv "$out.new" "$out"
}
pg_dump_container photos-immich-db-1 "$DUMP_DIR/immich.sql"
pg_dump_container docs-paperless-db-1 "$DUMP_DIR/paperless.sql"
# SQLite hot-backup: raw restic copies of live sqlite files can be corrupt.
# .backup takes a consistent snapshot; failures must not fail the backup.
SQLITE_FAILED=
sql_backup() {
  if [ -f "$1" ]; then
    if sqlite3 "$1" ".backup '$2'" 2>/dev/null; then
      log "sqlite dump ok: $2"
    else
      log "sqlite dump FAILED (continuing): $1"
      rm -f "$2"
      SQLITE_FAILED="${SQLITE_FAILED}${SQLITE_FAILED:+, }$1"
    fi
  fi
}
# NOTE: filebrowser.db is NOT sqlite (Filebrowser v2 uses bbolt) — raw restic
# copy of /opt covers it; do not add it here.
sql_backup /opt/stacks/docs/state/kavita/kavita.db "$DUMP_DIR/kavita.db"
sql_backup /opt/stacks/observability/state/gotify/gotify.db "$DUMP_DIR/gotify.db"
sql_backup /opt/stacks/observability/state/beszel/data.db "$DUMP_DIR/beszel.db"
if [ -n "$SQLITE_FAILED" ]; then
  alert "sqlite backup FAILED on $(hostname): $SQLITE_FAILED (backup continuing)"
fi

backup_important() {
  # /mnt/data covers /mnt/data/photos (mirror disk) — single path only.
  restic backup /opt "$DUMP_DIR" /mnt/data /etc /root/.ssh \
    --exclude /mnt/data/downloads \
    --exclude /mnt/data/media/downloads \
    --exclude /mnt/data/media/music/messy \
    --exclude /mnt/data/media/music/inbox/slskd/incomplete \
    --exclude /mnt/data/media/movies \
    --exclude /mnt/data/media/tv
}

backup_important
# DELIBERATE OMISSIONS: downloads, movies, and TV are re-downloadable bulk media.
# /mnt/data/media/downloads is a manual music review queue: kept on the mirror
# by choice, excluded from restic so 100G+ of staging never rides the backup.
# /mnt/data/media/music/messy is a 65G raw-intake archive: kept, never delete,
# excluded from restic for the same reason.
# RESTIC_PRUNE=0 for an append-only remote: a popped host then cannot delete its own backups.
case "${RESTIC_PRUNE:-1}" in 1) restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6 ;; esac

# Local restic drive (1TB, host /mnt/backup, guest via pve1-backup virtiofs).
# Never mkdir past this point unguarded: a repo on the root disk would fill it.
if ! mountpoint -q /mnt/backup; then
  log "local restic mount missing: /mnt/backup"
  alert "local restic mount missing on $(hostname): /mnt/backup (cloud backup completed)"
  exit 1
fi
cloud_repo=$RESTIC_REPOSITORY
export RESTIC_REPOSITORY=/mnt/backup/restic
mkdir -p "$RESTIC_REPOSITORY"
restic snapshots >/dev/null 2>&1 || restic init
backup_important
case "${RESTIC_PRUNE:-1}" in 1) restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6 ;; esac
export RESTIC_REPOSITORY="$cloud_repo"
# Success marker for the watchdog timer (a disabled timer fails silently otherwise).
mkdir -p /var/lib && date -Is > /var/lib/homelab-backup.last-ok
