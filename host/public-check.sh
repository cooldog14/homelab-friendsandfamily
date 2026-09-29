#!/usr/bin/env bash
# Black-box public check: Beszel sees green containers, not 502s from Caddy.
# Curl each public vhost over the internet (hairpin); any non-2xx/3xx fails
# the unit (=> notify@). No Uptime Kuma container by design.
set -euo pipefail

PUBLIC_CADDY_SITES_DIR=${PUBLIC_CADDY_SITES_DIR:-vps/sites}
FAIL=0

list_public_hosts() {
  cat <<'HOSTS' | sort -u
fiesta.malice.biz
files.malice.biz
jellyfin.malice.biz
kavita.malice.biz
mg.malice.biz
neko.malice.biz
nvdr.malice.biz
paperless.malice.biz
photos.malice.biz
player.malice.biz
requests.malice.biz
screego.malice.biz
upload.malice.biz
HOSTS
}

list_site_hosts() {
  find "$PUBLIC_CADDY_SITES_DIR" -type f -name '*.caddy' -exec awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*[[:alnum:]-]+(\.[[:alnum:]-]+)+[[:space:]]*\{/ { print $1 }
  ' {} + | sort -u
}

list_private_hosts() {
  awk '
    /^[[:space:]]*@[^[:space:]]+[[:space:]]+host[[:space:]]+/ {
      for (i = 3; i <= NF; i++) print $i
    }
  ' "$PRIVATE_CADDYFILE" | sort -u
}

if [[ ${1:-} == "--config-lint" ]]; then
  PRIVATE_CADDYFILE=${PRIVATE_CADDYFILE:-/opt/stacks/edge/Caddyfile}
  [[ -f $PRIVATE_CADDYFILE ]] || { echo "FAIL private Caddyfile missing: $PRIVATE_CADDYFILE" >&2; exit 1; }
  dupes=$(comm -12 <(list_public_hosts) <(list_private_hosts))
  if [[ -n $dupes ]]; then
    echo "FAIL public host duplicated in private Caddy:" >&2
    echo "$dupes" >&2
    exit 1
  fi
  [[ -d $PUBLIC_CADDY_SITES_DIR ]] || { echo "FAIL public Caddy sites dir missing: $PUBLIC_CADDY_SITES_DIR" >&2; exit 1; }
  missing=$(comm -23 <(list_public_hosts) <(list_site_hosts))
  extra=$(comm -13 <(list_public_hosts) <(list_site_hosts))
  if [[ -n $missing || -n $extra ]]; then
    echo "FAIL public host list differs from $PUBLIC_CADDY_SITES_DIR:" >&2
    [[ -z $missing ]] || printf 'missing from sites:\n%s\n' "$missing" >&2
    [[ -z $extra ]] || printf 'extra in sites:\n%s\n' "$extra" >&2
    exit 1
  fi
  echo "public-check config-lint ok"
  exit 0
fi

hosts=$(list_public_hosts)

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
for port in 64738 52000 3478 25565; do
  check_tcp "$first_host" "$port"
done
exit "$FAIL"
