# vps

The VPS is the public edge.

Caddy terminates TLS.
nftables forwards non-HTTP ports.
WireGuard chill0 connects to chill-01.

Run make vps from the repo root.
The deploy prunes Caddy site files to match git.

## public routes

Routes live in sites.
All backends point to 10.44.0.2.

- files.malice.biz
- photos.malice.biz
- paperless.malice.biz
- stirling.malice.biz
- kavita.malice.biz
- neko.malice.biz
- screego.malice.biz
- jellyfin.malice.biz
- requests.malice.biz
- player.malice.biz
- fiesta.malice.biz
- upload.malice.biz
- nvdr.malice.biz

Gotify is private.
Use gotify.h.malice.biz.

## non-HTTP ports

- Mumble: 64738 TCP and UDP
- Neko WebRTC: 52000 TCP and UDP
- Screego TURN: 3478 TCP and UDP
- Screego TURN range: 52100 to 52200 UDP

## traffic report

Run make traffic.
It reads VPS Caddy logs and writes traffic-report.html locally.
It also publishes the report to home.h.malice.biz/status/traffic.html.
It covers HTTP routes only.
It does not cover nftables-only ports.

Geo map works when this file exists on the VPS:
/var/lib/GeoIP/GeoLite2-City.mmdb

Use a local GeoIP database.
Do not send access logs to an external API.

## old cleanup

Old 10.30 WireGuard rules are retired.
Remove them from the live VPS after deploy.
