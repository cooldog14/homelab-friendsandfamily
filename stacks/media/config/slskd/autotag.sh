#!/bin/bash
set -euo pipefail

WRTAG_API_KEY="${SLSKD_WRTAG_API_KEY:-}"
download_path=$(printf '%s' "${SLSKD_SCRIPT_DATA:-}" | jq -r '.localDirectoryName // empty' 2>/dev/null || true)

if [ -z "$download_path" ]; then
  echo "[autotag] ERROR: no localDirectoryName in SLSKD_SCRIPT_DATA" >&2
  exit 1
fi

# slskd sees the library at /data (compose: ${DATA_LOCATION}:/data);
# wrtag sees it at /mnt/data (compose: ${DATA_LOCATION}:/mnt/data).
wrtag_path="${download_path/#/data//mnt/data}"
encoded_path=$(printf '%s' "$wrtag_path" | jq -sRr @uri)
auth_header="Authorization: Basic $(printf ':%s' "$WRTAG_API_KEY" | base64 -w0)"

wget -q -O- -S \
  --header "$auth_header" \
  --post-data "path=$encoded_path" \
  http://wrtag:7373/op/move >/dev/null

echo "[autotag] Done: $download_path"
