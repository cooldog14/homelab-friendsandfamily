# games

Game servers on chill-01.

## data

World + server config: `/mnt/data/apps/minecraft` (mirror disk, restic-backed).
No DB dumps needed; restic copies the world directory as-is.

## network

Raw TCP `25565`, not HTTP — Caddy never sees it. The VPS DNATs
`eth0:25565/tcp` to `10.44.0.2:25565` in `vps/nftables.conf`
(same pattern as Mumble `64738`). The container binds `${WG_IP}`
only, never `0.0.0.0`.

Clients connect to `mc.malice.biz:25565` (or the raw VPS IP:25565).
There is no web UI; RCON is enabled for admin via
`docker exec -i games-mc-1 rcon-cli` (password in stack `.env` on
chill-01, never in git).

## secrets

Use `../defaults.env` plus this stack's `.env` on chill-01.
Copy `.env.example` to `.env` and fill `RCON_PASSWORD` there.
Never commit .env.

## notes

Paper 26.2 server (latest stable Paper; 26.3 is alpha-only), version
pinned via `VERSION` + release-pinned image tag (renovate bumps it).
Players use a 26.2 launcher profile until Paper headlines 26.3 stable,
then bump `VERSION` (+ `java25` image). Same world, no reset. `MEMORY`
caps the Java heap — tune to the VM before adding a second server or
a map sidecar.

## plugins

Server-side only — players join with a stock 26.2 launcher, nothing to
install. `PLUGINS` in the compose pins jar URLs (bump them with
`VERSION`); jars persist in `/data/plugins` and a removed URL is
auto-deleted on next start. spark ships inside Paper 1.21+ already
(`/spark` just works). Chunky pre-generates the world before launch
day so exploration never lags the server — via console/RCON once live:

```
chunky radius 2500
chunky start
```

then `chunky progress` until done (a few thousand chunks; run it the
night before, it pins CPU while generating).
