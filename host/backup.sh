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
# Pull into a temp dir and swap only on full success: deleting the old
# WireGuard copy first left no rollback identity if the scp then failed.
VPS_BAK=/opt/vps-backup
mkdir -p "$VPS_BAK"
VPS_SSH="ssh -i /root/.ssh/vps-backup -p 4522 -o BatchMode=yes -o ConnectTimeout=15 root@194.58.47.21"
VPS_TMP=$(mktemp -d "$VPS_BAK/.pull.XXXXXX")
chmod 700 "$VPS_TMP"
if $VPS_SSH "sudo cat /etc/caddy/Caddyfile" > "$VPS_TMP/Caddyfile" 2>/dev/null \
&& $VPS_SSH "sudo cat /etc/nftables.conf" > "$VPS_TMP/nftables.conf" 2>/dev/null \
&& scp -i /root/.ssh/vps-backup -P 4522 -o BatchMode=yes -o ConnectTimeout=15 -r "root@194.58.47.21:/etc/wireguard" "$VPS_TMP/wireguard" 2>/dev/null; then
  chmod 700 "$VPS_BAK" "$VPS_TMP"; chmod 600 "$VPS_TMP/Caddyfile" "$VPS_TMP/nftables.conf" 2>/dev/null
  chmod 700 "$VPS_TMP/wireguard" 2>/dev/null; chmod 600 "$VPS_TMP/wireguard/"* 2>/dev/null
  rm -rf "$VPS_BAK/wireguard"
  mv "$VPS_TMP/Caddyfile" "$VPS_TMP/nftables.conf" "$VPS_BAK"/
  mv "$VPS_TMP/wireguard" "$VPS_BAK/wireguard"
  rmdir "$VPS_TMP"
  log "vps pull ok"
else
  rm -rf "$VPS_TMP"
  log "vps pull FAILED (continuing backup without it)"
  # Fail-open for data, fail-loud for awareness: a config drift during a VPS outage
  # would otherwise vanish silently. Never fail the backup over this.
  alert "vps pull FAILED on $(hostname) (backup continuing without VPS config)"
fi

PG_FAILED=
pg_dump_container() {
  container=$1
  out=$2
  if ! docker exec "$container" sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$out.new" \
    || [ ! -s "$out.new" ] \
    || ! grep -q "PostgreSQL database dump" "$out.new"; then
    rm -f "$out.new"
    log "postgres dump FAILED (continuing): $container"
    PG_FAILED="${PG_FAILED}${PG_FAILED:+, }$container"
    return 1
  fi
  mv "$out.new" "$out"
  log "postgres dump ok: $out"
}
pg_dump_container photos-immich-db-1 "$DUMP_DIR/immich.sql" || true
pg_dump_container docs-paperless-db-1 "$DUMP_DIR/paperless.sql" || true
# SQLite hot-backup: raw restic copies of live sqlite files can be corrupt.
# Every dump is written aside, integrity-checked, then swapped only on success.
# A failure alerts and continues; the previous good dump remains untouched.
SQLITE_FAILED=
sql_backup() {
  src=$1
  out=$2
  tmp="$out.new"
  rm -f "$tmp"
  if [ ! -f "$src" ]; then
    log "sqlite dump FAILED (missing): $src"
    SQLITE_FAILED="${SQLITE_FAILED}${SQLITE_FAILED:+, }$src(missing)"
  elif sqlite3 "$src" ".backup '$tmp'" 2>/dev/null \
    && [ -s "$tmp" ] \
    && sqlite3 "$tmp" "PRAGMA quick_check;" 2>/dev/null | grep -qx ok; then
    mv "$tmp" "$out"
    log "sqlite dump ok: $out"
  else
    log "sqlite dump FAILED (continuing): $src"
    rm -f "$tmp"
    SQLITE_FAILED="${SQLITE_FAILED}${SQLITE_FAILED:+, }$src"
  fi
}
# NOTE: filebrowser's bbolt files are not SQLite; their raw restic copies are
# outside the SQLite dump path. Dump the SQLite side of each Filebrowser.
sql_backup /opt/stacks/apps/state/filebrowser-quantum/database.sqlite "$DUMP_DIR/filebrowser-quantum.sqlite"
sql_backup /opt/stacks/apps/state/filebrowser-family/database.sqlite "$DUMP_DIR/filebrowser-family.sqlite"
sql_backup /opt/stacks/apps/state/filebrowser-upload/database.sqlite "$DUMP_DIR/filebrowser-upload.sqlite"
sql_backup /opt/stacks/docs/state/kavita/kavita.db "$DUMP_DIR/kavita.db"
sql_backup /opt/stacks/comms/state/mumble/mumble-server.sqlite "$DUMP_DIR/mumble.sqlite"
sql_backup /opt/stacks/media/state/navidrome/navidrome.db "$DUMP_DIR/navidrome.db"
sql_backup /opt/stacks/media/state/prowlarr/prowlarr.db "$DUMP_DIR/prowlarr.db"
sql_backup /opt/stacks/media/state/radarr/radarr.db "$DUMP_DIR/radarr.db"
sql_backup /opt/stacks/media/state/sonarr/sonarr.db "$DUMP_DIR/sonarr.db"
sql_backup /opt/stacks/media/state/bazarr/db/bazarr.db "$DUMP_DIR/bazarr.db"
sql_backup /opt/stacks/media/state/jellyseerr/db/db.sqlite3 "$DUMP_DIR/jellyseerr.sqlite"
sql_backup /opt/stacks/media/state/slskd/data/transfers.db "$DUMP_DIR/slskd-transfers.db"
sql_backup /opt/stacks/media/state/slskd/data/events.db "$DUMP_DIR/slskd-events.db"
sql_backup /opt/stacks/media/state/slskd/data/messaging.db "$DUMP_DIR/slskd-messaging.db"
sql_backup /opt/stacks/media/state/slskd/data/search.db "$DUMP_DIR/slskd-search.db"
sql_backup /opt/stacks/media/state/wrtag/wrtag.db "$DUMP_DIR/wrtag.db"
sql_backup /opt/stacks/media/state/jellyfin-config/data/jellyfin.db "$DUMP_DIR/jellyfin.db"
sql_backup /opt/stacks/observability/state/gotify/gotify.db "$DUMP_DIR/gotify.db"
sql_backup /opt/stacks/observability/state/grafana/grafana.db "$DUMP_DIR/grafana.db"
if [ -n "$PG_FAILED" ] || [ -n "$SQLITE_FAILED" ]; then
  alert "database dump incomplete on $(hostname): PG=[$PG_FAILED] SQLite=[$SQLITE_FAILED] (backup continuing)"
fi

# Minecraft: disable periodic saves and flush once. Suwayomi uses H2, which
# cannot be hot-copied with sqlite3; pause only long enough for an atomic tar.
QUIESCE_FAILED=
MC_QUIESCED=
SUWAYOMI_PAUSED=
FB_PAUSED=
cleanup_live_state() {
  if [ "$FB_PAUSED" != "" ]; then
    docker unpause "$FB_PAUSED" >/dev/null 2>&1 || {
      log "FAILED to unpause $FB_PAUSED"
      alert "$FB_PAUSED remains paused on $(hostname)"
    }
  fi
  if [ "$SUWAYOMI_PAUSED" = 1 ]; then
    docker unpause media-suwayomi-1 >/dev/null 2>&1 || {
      log "FAILED to unpause media-suwayomi-1"
      alert "media-suwayomi-1 remains paused on $(hostname)"
    }
  fi
  if [ "$MC_QUIESCED" = 1 ]; then
    docker exec games-mc-1 rcon-cli save-on >/dev/null 2>&1 || {
      log "FAILED to re-enable Minecraft saves"
      alert "Minecraft save-on failed on $(hostname)"
    }
  fi
}
trap cleanup_live_state EXIT

# bbolt cannot be dumped with sqlite3. Pause each Filebrowser just long enough
# for a consistent copy, then resume it before the potentially long restic run.
filebrowser_bolt_copy() {
  container=$1
  src=$2
  out=$3
  if docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -qx true; then
    if docker pause "$container" >/dev/null 2>&1; then
      FB_PAUSED=$container
    else
      QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }${container}-pause"
      return
    fi
  fi
  if cp -a "$src" "$out.new" && [ -s "$out.new" ]; then
    mv "$out.new" "$out"
    log "filebrowser state copied: $out"
  else
    rm -f "$out.new"
    QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }${container}-copy"
  fi
  if [ "$FB_PAUSED" = "$container" ]; then
    if docker unpause "$container" >/dev/null 2>&1; then
      FB_PAUSED=
    else
      QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }${container}-resume"
    fi
  fi
}
filebrowser_bolt_copy apps-filebrowser-1 /opt/stacks/apps/state/filebrowser-quantum/database.db "$DUMP_DIR/filebrowser-quantum.boltdb"
filebrowser_bolt_copy apps-filebrowser-family-1 /opt/stacks/apps/state/filebrowser-family/database.db "$DUMP_DIR/filebrowser-family.boltdb"
filebrowser_bolt_copy apps-filebrowser-upload-1 /opt/stacks/apps/state/filebrowser-upload/database.db "$DUMP_DIR/filebrowser-upload.boltdb"

if docker inspect -f '{{.State.Running}}' games-mc-1 2>/dev/null | grep -qx true; then
  if docker exec games-mc-1 rcon-cli save-off >/dev/null 2>&1 \
    && docker exec games-mc-1 rcon-cli save-all flush >/dev/null 2>&1; then
    MC_QUIESCED=1
    sleep 2
    log "minecraft writes quiesced"
  else
    QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }minecraft"
    log "minecraft quiesce FAILED (raw snapshot may be inconsistent)"
  fi
fi

if docker inspect -f '{{.State.Running}}' media-suwayomi-1 2>/dev/null | grep -qx true; then
  if docker pause media-suwayomi-1 >/dev/null 2>&1; then
    SUWAYOMI_PAUSED=1
  else
    QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }suwayomi-pause"
  fi
fi
suwayomi_tar="$DUMP_DIR/suwayomi-state.tar"
if tar -C /mnt/data/apps/suwayomi -cf "$suwayomi_tar.new" .; then
  chmod 600 "$suwayomi_tar.new"
  mv "$suwayomi_tar.new" "$suwayomi_tar"
  log "suwayomi archive ok"
else
  rm -f "$suwayomi_tar.new"
  QUIESCE_FAILED="${QUIESCE_FAILED}${QUIESCE_FAILED:+, }suwayomi-archive"
  log "suwayomi archive FAILED (previous archive retained if present)"
fi
if [ "$SUWAYOMI_PAUSED" = 1 ]; then
  if docker unpause media-suwayomi-1 >/dev/null 2>&1; then
    SUWAYOMI_PAUSED=
    log "suwayomi resumed"
  else
    log "suwayomi unpause FAILED"
  fi
fi

if [ -n "$QUIESCE_FAILED" ]; then
  alert "live-state quiesce incomplete on $(hostname): $QUIESCE_FAILED (backup continuing)"
fi

backup_and_prune() {
  # /mnt/data covers the takeover tree; live database internals are excluded
  # because the consistent dumps above are the restore source.
  restic backup /opt "$DUMP_DIR" /mnt/data /etc /root/.ssh \
    --exclude /opt/stacks/apps/state/filebrowser-quantum/database.db \
    --exclude /opt/stacks/apps/state/filebrowser-family/database.db \
    --exclude /opt/stacks/apps/state/filebrowser-upload/database.db \
    --exclude /mnt/data/apps/suwayomi \
    --exclude /mnt/data/downloads \
    --exclude /mnt/data/media/music/inbox/slskd/incomplete \
    --exclude /mnt/data/media/movies \
    --exclude /mnt/data/media/tv \
    --exclude /opt/stacks/photos/state/immich/db \
    --exclude /opt/stacks/photos/state/immich/model-cache \
    --exclude /opt/stacks/docs/state/paperless-db \
    --exclude /opt/stacks/observability/state/prometheus
  # Retention: the latest three snapshots, and only ones taken with this exact
  # path set. The helper refuses to prune a changed layout unless explicitly
  # told to, so a future backup-path edit cannot silently delete history.
  if [ "${RESTIC_PRUNE:-1}" = 1 ]; then /usr/local/bin/homelab-restic-retention; fi
}

# DELIBERATE OMISSIONS: movies and TV are re-downloadable bulk media (and live
# on /mnt/pool, not /mnt/data, so those excludes are belt-and-braces);
# slskd/incomplete holds transient chunks; /mnt/data/downloads is empty.
# messy (65G raw-intake archive) and media/downloads (music review queue) ARE
# backed up since the 2026-10-16 sdc failure: hand-curated, irreplaceable,
# and static enough that restic dedup makes them near-free after one pass.
# (Sep 27 exclusion nearly lost both; only a retained Sep 27 cloud snapshot
# saved them. Never exclude curated archives to save one-time upload.)
# RESTIC_PRUNE=0 for an append-only remote: a popped host then cannot delete its own backups.
backup_and_prune

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
backup_and_prune
export RESTIC_REPOSITORY="$cloud_repo"
if [ -n "$PG_FAILED" ] || [ -n "$SQLITE_FAILED" ] || [ -n "$QUIESCE_FAILED" ]; then
  alert "backup completed INCOMPLETE on $(hostname): PG=[$PG_FAILED] SQLite=[$SQLITE_FAILED] quiesce=[$QUIESCE_FAILED]"
  exit 1
fi
# Success marker for the watchdog timer (a disabled timer fails silently otherwise).
mkdir -p /var/lib && date -Is > /var/lib/homelab-backup.last-ok
