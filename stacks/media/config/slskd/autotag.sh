#!/bin/bash
set -euo pipefail

WRTAG_API_KEY="${SLSKD_WRTAG_API_KEY:-}"

rewrite_path() {
  case "$1" in
    /data/*) printf '/mnt/data/%s' "${1#/data/}" ;;
    *) printf '%s' "$1" ;;
  esac
}

if [ "${1:-}" = "--self-check" ]; then
  [ "$(rewrite_path /data/media/music/inbox/slskd/complete/Album)" = "/mnt/data/media/music/inbox/slskd/complete/Album" ]
  [ "$(rewrite_path /tmp/Album)" = "/tmp/Album" ]
  echo "autotag self-check ok"
  exit 0
fi

download_path=$(printf '%s' "${SLSKD_SCRIPT_DATA:-}" | jq -r '.localDirectoryName // empty' 2>/dev/null || true)

if [ -z "$download_path" ]; then
  echo "[autotag] ERROR: no localDirectoryName in SLSKD_SCRIPT_DATA" >&2
  exit 1
fi

# slskd sees the library at /data (compose: ${DATA_LOCATION}:/data);
# wrtag sees it at /mnt/data (compose: ${DATA_LOCATION}:/mnt/data).
wrtag_path=$(rewrite_path "$download_path")
encoded_path=$(printf '%s' "$wrtag_path" | jq -sRr @uri)
auth_header="Authorization: Basic $(printf ':%s' "$WRTAG_API_KEY" | base64 -w0)"

wget -q -O- -S \
  --header "$auth_header" \
  --post-data "path=$encoded_path" \
  http://wrtag:7373/op/move >/dev/null

echo "[autotag] Done: $download_path"
