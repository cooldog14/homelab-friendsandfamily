#!/bin/sh
set -eu

out=${1:-/var/lib/homelab-traffic/traffic.html}
log_glob=${LOG_GLOB:-/var/log/caddy/access.log*}

empty_report() {
  cat > "$1" <<'HTML'
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>traffic</title></head>
<body><h1>traffic</h1><p>No public traffic logs yet.</p></body>
</html>
HTML
}

if [ "${1:-}" = "--self-check" ]; then
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  mkdir -p "$tmpdir/bin" "$tmpdir/logs" "$tmpdir/out"
  cat > "$tmpdir/bin/goaccess" <<'SH'
#!/bin/sh
out=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    shift
    out=$1
  fi
  shift || true
done
printf '<html>goaccess ok</html>\n' > "$out"
SH
  chmod +x "$tmpdir/bin/goaccess"
  printf '{"ts":"2026-09-18T09:00:00Z","request":{"host":"jellyfin.malice.biz","uri":"/"},"status":200}\n' > "$tmpdir/logs/access.log"
  PATH="$tmpdir/bin:$PATH" LOG_GLOB="$tmpdir/logs/access.log" "$0" "$tmpdir/out/traffic.html"
  grep -q 'goaccess ok' "$tmpdir/out/traffic.html"
  rm "$tmpdir/logs/access.log"
  PATH="$tmpdir/bin:$PATH" LOG_GLOB="$tmpdir/logs/access.log" "$0" "$tmpdir/out/empty.html"
  grep -q 'No public traffic logs yet' "$tmpdir/out/empty.html"
  echo "traffic-report self-check ok"
  exit 0
fi

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$(dirname "$out")"
log="$tmpdir/access.log"

for f in $log_glob; do
  [ -e "$f" ] || continue
  # Only access entries: the log file can start with Caddy process lines
  # (startup messages from the old global log block), and goaccess aborts
  # with RC=1 producing no report if unparseable lines come first.
  zcat -f "$f" 2>/dev/null | grep '"handled request"' >> "$log" 2>/dev/null || true
done

if [ ! -s "$log" ]; then
  empty_report "$tmpdir/traffic.html"
  install -m 644 "$tmpdir/traffic.html" "$out"
  exit 0
fi

set --
[ ! -f /var/lib/GeoIP/GeoLite2-City.mmdb ] || set -- --geoip-database=/var/lib/GeoIP/GeoLite2-City.mmdb
goaccess "$log" --log-format=CADDY --no-progress --anonymize-ip "$@" -o "$tmpdir/traffic.html"
install -m 644 "$tmpdir/traffic.html" "$out"
