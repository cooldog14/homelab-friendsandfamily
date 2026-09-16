#!/bin/sh
# Black-box public check: Beszel sees green containers, not 502s from Caddy.
# Curl each public vhost over the internet (hairpin); any non-2xx/3xx fails
# the unit (=> notify@). No Uptime Kuma container by design.
set -eu
# /etc/homelab.env lives on the host, not in git (only needed for nothing here;
# kept for symmetry in case ALERT handling moves in-script later).
FAIL=0
# Keep in sync with the reverse_proxy lines in vps/sites/chill.caddy.
for url in https://files.1x8.me https://photos.1x8.me https://gotify.1x8.me https://paperless.1x8.me https://stirling.1x8.me https://kavita.1x8.me https://neko.1x8.me https://screego.1x8.me; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null || echo 000)
  case "$code" in
    2*|3*) echo "ok $code $url" ;;
    *) echo "FAIL $code $url" >&2; FAIL=1 ;;
  esac
done
exit $FAIL
