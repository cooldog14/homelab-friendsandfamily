#!/usr/bin/env bash
set -Eeuo pipefail
umask 002

if [ "${1:-}" = "--self-check" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/downloads/uploads/Old Album" "$tmp/downloads/uploads/Fresh Album" "$tmp/downloads/slskd/complete" "$tmp/media/music" "$tmp/bin"
  printf x > "$tmp/downloads/uploads/Old Album/song.flac"
  printf x > "$tmp/downloads/uploads/Fresh Album/song.flac"
  touch -d '3 minutes ago' "$tmp/downloads/uploads/Old Album" "$tmp/downloads/uploads/Old Album/song.flac"
  cat > "$tmp/bin/curl" <<'SH'
#!/bin/sh
exit 0
SH
  chmod +x "$tmp/bin/curl"
  PATH="$tmp/bin:$PATH" DATA_ROOT="$tmp" IMPORT_MIN_AGE_MINUTES=2 SUBSONIC_ADMIN_USERNAME=u SUBSONIC_ADMIN_PASSWORD=p "$0"
  [ -f "$tmp/media/music/Old Album/song.flac" ]
  [ ! -e "$tmp/downloads/uploads/Old Album" ]
  [ -f "$tmp/downloads/uploads/Fresh Album/song.flac" ]

  mkdir -p "$tmp/downloads/uploads/Blocked Album" "$tmp/media/music/clean/Blocked Album"
  printf x > "$tmp/downloads/uploads/Blocked Album/song.flac"
  touch -d '3 minutes ago' "$tmp/downloads/uploads/Blocked Album" "$tmp/downloads/uploads/Blocked Album/song.flac" "$tmp/media/music/clean/Blocked Album"
  if PATH="$tmp/bin:$PATH" DATA_ROOT="$tmp" IMPORT_MIN_AGE_MINUTES=2 SUBSONIC_ADMIN_USERNAME=u SUBSONIC_ADMIN_PASSWORD=p "$0" 2>/dev/null; then
    echo "ingest self-check failed: clean collision was imported" >&2
    exit 1
  fi
  [ -f "$tmp/downloads/uploads/Blocked Album/song.flac" ]

  echo "ingest self-check ok"
  exit 0
fi

DATA_ROOT="${DATA_ROOT:-/mnt/data}"
DEST="$DATA_ROOT/media/music"
IMPORT_MIN_AGE_MINUTES="${IMPORT_MIN_AGE_MINUTES:-2}"
NAVIDROME_HOST="${NAVIDROME_HOST:-127.0.0.1:4533}"
GOTIFY_URL="${GOTIFY_URL:-${ALERT_URL:-}}"
SOURCES=(
  "$DATA_ROOT/downloads/uploads"
  "$DATA_ROOT/downloads/slskd/complete"
)

notify() {
  [ -n "$GOTIFY_URL" ] || return 0
  curl -fsS -X POST \
    --form-string "title=$1" \
    --form-string "message=$2" \
    --form-string "priority=${3:-5}" \
    "$GOTIFY_URL" >/dev/null || true
}

on_error() {
  status=$?
  notify "Music ingest failed" "media music ingest failed on $(hostname) at line $1 (exit $status)." 5
  exit "$status"
}
trap 'on_error "$LINENO"' ERR

entry_is_stable() {
  [ "$IMPORT_MIN_AGE_MINUTES" = "0" ] && return 0
  [ -z "$(find "$1" -mmin "-$IMPORT_MIN_AGE_MINUTES" -print -quit)" ]
}

moved_names=()
for src in "${SOURCES[@]}"; do
  [ -d "$src" ] || continue
  while IFS= read -r -d '' entry; do
    entry_is_stable "$entry" || continue
    name=$(basename "$entry")
    if [ -e "$DEST/$name" ] || [ -e "$DEST/clean/$name" ]; then
      echo "ingest: destination already exists in music library: $name" >&2
      false
    fi
    mv "$entry" "$DEST/"
    moved_names+=("${entry#"$DATA_ROOT"/}")
  done < <(find "$src" -mindepth 1 -maxdepth 1 -print0)
  find "$src" -mindepth 1 -type d -empty -delete 2>/dev/null || true
done

[ "${#moved_names[@]}" -gt 0 ] || exit 0

: "${SUBSONIC_ADMIN_USERNAME:?set SUBSONIC_ADMIN_USERNAME}"
: "${SUBSONIC_ADMIN_PASSWORD:?set SUBSONIC_ADMIN_PASSWORD}"

curl -fsS -G "http://${NAVIDROME_HOST}/rest/startScan.view" \
  --data-urlencode "u=${SUBSONIC_ADMIN_USERNAME}" \
  --data-urlencode "p=${SUBSONIC_ADMIN_PASSWORD}" \
  --data-urlencode "v=1.16.1" \
  --data-urlencode "c=ingest" >/dev/null

message="Imported ${#moved_names[@]} item(s) and started Navidrome scan."
if [ "${#moved_names[@]}" -le 10 ]; then
  message="$message
$(printf ' - %s\n' "${moved_names[@]}")"
fi
notify "Music ingest complete" "$message" 3
