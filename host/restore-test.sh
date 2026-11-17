#!/bin/sh
# Restore a sampled set from the offsite repository and verify the bytes.
# Run remotely through `make restore-test`; never writes over live data.
set -eu
set -a
# shellcheck source=/dev/null
. /etc/homelab.env
set +a

rt=/opt/restore-test
cleanup() { rm -rf "$rt"; }
trap cleanup EXIT
rm -rf "$rt"
mkdir -p "$rt"

chill_include=
if restic ls latest /opt/vps-backup/wireguard/chill0.conf >/dev/null 2>&1; then
  chill_include="--include /opt/vps-backup/wireguard/chill0.conf"
fi

# shellcheck disable=SC2086
restic restore latest --target "$rt" \
  --include /mnt/fast/dumps \
  --include /etc/homelab.env \
  --include /etc/wireguard/wg0.conf \
  --include /opt/vps-backup/Caddyfile \
  --include /opt/vps-backup/nftables.conf \
  $chill_include

dump_dir="$rt/mnt/fast/dumps"
[ -d "$dump_dir" ] || { echo "restored dump directory missing" >&2; exit 1; }
test -s "$dump_dir/immich.sql"
grep -q "PostgreSQL database dump" "$dump_dir/immich.sql"
test -s "$dump_dir/paperless.sql"
grep -q "PostgreSQL database dump" "$dump_dir/paperless.sql"

dbs=0
for f in "$dump_dir"/*.db "$dump_dir"/*.sqlite "$dump_dir"/*.sqlite3; do
  [ -e "$f" ] || continue
  test -s "$f" || { echo "empty database dump: ${f##*/}" >&2; exit 1; }
  sqlite3 "$f" "PRAGMA integrity_check;" | grep -qx ok || {
    echo "failed integrity check: ${f##*/}" >&2
    exit 1
  }
  dbs=$((dbs + 1))
done
[ "$dbs" -ge 18 ] || { echo "expected at least 18 SQLite dumps, got $dbs" >&2; exit 1; }
bolts=0
for f in "$dump_dir"/*.boltdb; do
  [ -e "$f" ] || continue
  [ "$(od -An -tx1 -N4 "$f" | tr -d ' \n')" = "ed0cdaed" ] || {
    echo "invalid Bolt snapshot: ${f##*/}" >&2
    exit 1
  }
  bolts=$((bolts + 1))
done
[ "$bolts" -eq 3 ] || { echo "expected 3 Bolt snapshots, got $bolts" >&2; exit 1; }
tar -tf "$dump_dir/suwayomi-state.tar" >/dev/null

test -s "$rt/etc/homelab.env"
grep -Eq "^[A-Z0-9_]+=" "$rt/etc/homelab.env"
test -s "$rt/etc/wireguard/wg0.conf"
grep -q "^\[Interface\]" "$rt/etc/wireguard/wg0.conf"
test -s "$rt/opt/vps-backup/Caddyfile"
grep -q "import /etc/caddy/sites/[*].caddy" "$rt/opt/vps-backup/Caddyfile"
test -s "$rt/opt/vps-backup/nftables.conf"
grep -q "homelab_nat" "$rt/opt/vps-backup/nftables.conf"
if [ -n "$chill_include" ]; then
  test -s "$rt/opt/vps-backup/wireguard/chill0.conf"
  grep -q "^\[Interface\]" "$rt/opt/vps-backup/wireguard/chill0.conf"
fi

restic ls latest /mnt/data/photos >/dev/null
echo "restore-test ok ($dbs SQLite dumps)"
