#!/bin/sh
# Black-box public check: Beszel sees green containers, not 502s from Caddy.
# Curl each public vhost over the internet (hairpin); any non-2xx/3xx fails
# the unit (=> notify@). No Uptime Kuma container by design.
set -eu
# /etc/homelab.env lives on the host, not in git (only needed for nothing here;
# kept for symmetry in case ALERT handling moves in-script later).
FAIL=0
# Keep in sync with the reverse_proxy lines in vps/sites/*.caddy.
for host in \
  files.malice.biz \
  photos.malice.biz \
  gotify.malice.biz \
  paperless.malice.biz \
  stirling.malice.biz \
  kavita.malice.biz \
  neko.malice.biz \
  screego.malice.biz \
  jellyfin.malice.biz \
  requests.malice.biz \
  player.malice.biz \
  fiesta.malice.biz \
  upload.malice.biz \
  nvdr.malice.biz; do
  url="https://$host"
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null || echo 000)
  case "$code" in
    2*|3*|401) echo "ok $code $url" ;;
    *) echo "FAIL $code $url" >&2; FAIL=1 ;;
  esac
done
exit $FAIL
