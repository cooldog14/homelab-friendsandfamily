#!/usr/bin/env bash
# Black-box public check: Beszel sees green containers, not 502s from Caddy.
# Curl each public vhost over the internet (hairpin); any non-2xx/3xx fails
# the unit (=> notify@). No Uptime Kuma container by design.
set -euo pipefail

PUBLIC_CADDY_SITES_DIR=${PUBLIC_CADDY_SITES_DIR:-/opt/homelab-public-sites}
FAIL=0

list_http_hosts() {
  find "$PUBLIC_CADDY_SITES_DIR" -type f -name '*.caddy' -exec awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*[[:alnum:]-]+(\.[[:alnum:]-]+)+[[:space:]]*\{/ { print $1 }
  ' {} + | sort -u
}

if [[ ${1:-} == "--self-check" ]]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  cat > "$tmp/routes.caddy" <<'CADDY'
# ignored.malice.biz {
photos.malice.biz {
	reverse_proxy 10.44.0.2:2283
}
upload.malice.biz {
	reverse_proxy 10.44.0.2:8087
}
CADDY
  PUBLIC_CADDY_SITES_DIR=$tmp
  expected=$(printf '%s\n' photos.malice.biz upload.malice.biz)
  actual=$(list_http_hosts)
  [[ $actual == "$expected" ]]
  echo "public-check self-check ok"
  exit 0
fi

if [[ ! -d $PUBLIC_CADDY_SITES_DIR ]]; then
  echo "FAIL public Caddy sites dir missing: $PUBLIC_CADDY_SITES_DIR" >&2
  exit 1
fi

hosts=$(list_http_hosts)
if [[ -z $hosts ]]; then
  echo "FAIL no public Caddy hosts found in $PUBLIC_CADDY_SITES_DIR" >&2
  exit 1
fi

check_http() {
  local host=$1 code url
  url="https://$host"
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null || true)
  case "$code" in
    2*|3*|401) echo "ok $code $url" ;;
    *) echo "FAIL $code $url" >&2; FAIL=1 ;;
  esac
}

check_tcp() {
  local host=$1 port=$2
  if timeout 5 bash -c ":</dev/tcp/$host/$port" 2>/dev/null; then
    echo "ok tcp $host:$port"
  else
    echo "FAIL tcp $host:$port" >&2
    FAIL=1
  fi
}

first_host=
while IFS= read -r host; do
  [[ -n $host ]] || continue
  [[ -n $first_host ]] || first_host=$host
  check_http "$host"
done <<< "$hosts"

# UDP forwards exist too, but there is no cheap connect-only UDP smoke.
for port in 64738 52000 3478; do
  check_tcp "$first_host" "$port"
done
exit "$FAIL"
