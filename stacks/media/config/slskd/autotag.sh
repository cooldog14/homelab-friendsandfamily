#!/bin/sh
set -eu

WRTAG_API_KEY="${SLSKD_WRTAG_API_KEY:-}"

local_directory() {
  printf '%s' "$1" | sed -n 's/.*"localDirectoryName"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

rewrite_path() {
  case "$1" in
    /data/*) printf '/mnt/data/%s' "${1#/data/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

urlencode() {
  printf '%s' "$1" | od -An -v -tx1 | tr ' ' '\n' | while IFS= read -r byte; do
    [ -n "$byte" ] && printf '%%%s' "$(printf '%s' "$byte" | tr '[:lower:]' '[:upper:]')"
  done
}

if [ "${1:-}" = "--self-check" ]; then
  [ "$(rewrite_path /data/media/music/inbox/slskd/complete/Album)" = "/mnt/data/media/music/inbox/slskd/complete/Album" ]
  [ "$(rewrite_path /tmp/Album)" = "/tmp/Album" ]
  [ "$(local_directory '{"localDirectoryName":"/data/media/music/inbox/slskd/complete/Album Name"}')" = "/data/media/music/inbox/slskd/complete/Album Name" ]
  [ "$(urlencode "/A B")" = "%2F%41%20%42" ]
  echo "autotag self-check ok"
  exit 0
fi

download_path=$(local_directory "${SLSKD_SCRIPT_DATA:-}")

if [ -z "$download_path" ]; then
  echo "[autotag] ERROR: no localDirectoryName in SLSKD_SCRIPT_DATA" >&2
  exit 1
fi

# slskd sees the library at /data; wrtag sees the same host tree at /mnt/data.
wrtag_path=$(rewrite_path "$download_path")
encoded_path=$(urlencode "$wrtag_path")
auth_header="Authorization: Basic $(printf ':%s' "$WRTAG_API_KEY" | base64 | tr -d '\n')"

wget -q -O- \
  --header "$auth_header" \
  --post-data "path=$encoded_path" \
  http://wrtag:7373/op/move >/dev/null

echo "[autotag] Done: $download_path"
