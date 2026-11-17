#!/bin/sh
# Weekly sampled-data verification of both application-VM restic repositories.
# Metadata-only checks still run in the nightly backup; this catches damaged
# packs that metadata alone cannot see.
set -eu
export HOME="${HOME:-/root}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-/root/.cache}"
set -a
# shellcheck source=/dev/null
. /etc/homelab.env
set +a

rc=0
echo "checking cloud repository (5% of pack data)"
restic check --read-data-subset=5% || rc=1

if ! mountpoint -q /mnt/backup; then
  echo "local restic mount missing: /mnt/backup" >&2
  exit 1
fi
echo "checking local repository (5% of pack data)"
RESTIC_REPOSITORY=/mnt/backup/restic restic check --read-data-subset=5% || rc=1

exit "$rc"
