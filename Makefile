# Tailscale is the admin path (never the WG tunnel, which is VPS-only).
HOST ?= chill-01
# Bare `chill-01` needs an ssh alias (HostName 100.92.173.71, User deploy);
# override with HOST=deploy@10.44.0.2 only from a WG-connected host.
# VPS via the vps-ingress SSH alias (port 4522 + key in ~/.ssh/config); 22 is closed.
VPS_SSH ?= ssh vps-ingress
STACKS = apps comms docs edge games media observability photos

# git is the source of truth; Dockge is for logs and restarts, not for editing YAML behind git's back.
# Ship the local working tree (commit + push first). No git pull on the host,
# so no deploy-key scoping issue when splitting repos.
deploy: sync-public-sites
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'set -e; sudo rsync -a --delete --exclude .env --exclude state/ --exclude docs/config/stirling/ /tmp/chill-stacks/ /opt/stacks/ && for d in /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /opt/stacks/apps/state/filebrowser-family /opt/stacks/media/state /opt/stacks/media/state/gluetun /opt/stacks/media/state/jellyfin-config /opt/stacks/media/state/qbittorrent /opt/stacks/media/state/prowlarr /opt/stacks/media/state/radarr /opt/stacks/media/state/sonarr /opt/stacks/media/state/bazarr /opt/stacks/media/state/jellyseerr /opt/stacks/media/state/navidrome /opt/stacks/media/state/wrtag /opt/stacks/media/state/octo-fiesta /opt/stacks/media/state/slskd /mnt/fast/jellyfin-cache /mnt/fast/scratch /mnt/fast/imports /mnt/fast/build-cache /mnt/data/family /mnt/data/photos /mnt/data/apps/paperless/data /mnt/data/apps/paperless/media /mnt/data/apps/paperless/export /mnt/data/apps/paperless/consume /mnt/data/apps/stirling/tessdata /mnt/data/apps/stirling/config /mnt/data/apps/stirling/logs /mnt/data/apps/stirling/customFiles /mnt/data/apps/stirling/pipeline /mnt/data/apps/suwayomi /mnt/data/apps/minecraft /mnt/data/media/music/inbox/user /mnt/data/media/music/inbox/slskd/complete /mnt/data/media/music/inbox/slskd/incomplete; do sudo mkdir -p "$$d"; done && sudo install -d -m 0700 /mnt/fast/dumps && sudo chown -R 1000:1000 /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /opt/stacks/apps/state/filebrowser-family /mnt/fast/jellyfin-cache /mnt/fast/scratch /mnt/fast/imports /mnt/fast/build-cache /mnt/data/family /mnt/data/photos /mnt/data/apps/paperless /mnt/data/apps/stirling /mnt/data/apps/suwayomi /mnt/data/apps/minecraft /mnt/data/media/music/inbox /opt/stacks/media/state && compose_up() { cd /opt/stacks/$$1 && set -a && . ../defaults.env && set +a && sudo env WG_IP="$$WG_IP" DATA_LOCATION="$$DATA_LOCATION" TIMEZONE="$$TIMEZONE" docker compose -p $$1 up -d --pull missing --remove-orphans; }; for s in $(STACKS); do (compose_up $$s); done'
	# NOTE: --pull missing (not always): the CLI flag overrides compose pull_policy, and redlib is a
	# local source build (pull_policy: never) that --pull always would try to fetch from a registry.

storage-cleanup:
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'set -eu; sudo rsync -a --delete --exclude .env --exclude state/ --exclude docs/config/stirling/ /tmp/chill-stacks/ /opt/stacks/; compose() { stack=$$1; shift; (cd /opt/stacks/$$stack && set -a && . ../defaults.env && set +a && sudo env WG_IP="$$WG_IP" DATA_LOCATION="$$DATA_LOCATION" TIMEZONE="$$TIMEZONE" docker compose -p $$stack "$$@"); }; stop() { compose $$1 stop $$2 >/dev/null || true; }; start() { compose $$1 up -d $$2; }; move_dir() { old=$$1; new=$$2; [ -d "$$old" ] || return 0; sudo mkdir -p "$$(dirname "$$new")"; if [ -d "$$new" ] && [ -z "$$(sudo find "$$new" -mindepth 1 -print -quit)" ]; then sudo rmdir "$$new"; fi; if [ ! -e "$$new" ]; then sudo mv "$$old" "$$new"; else echo "ERROR: $$new exists; inspect before moving $$old" >&2; exit 1; fi; }; stop apps filebrowser-upload; stop docs paperless; stop docs stirling-pdf; stop media suwayomi; stop media slskd; move_dir /mnt/data/docs/paperless/data /mnt/data/apps/paperless/data; move_dir /mnt/data/docs/paperless/media /mnt/data/apps/paperless/media; move_dir /mnt/data/docs/paperless/export /mnt/data/apps/paperless/export; move_dir /mnt/data/docs/paperless/consume /mnt/data/apps/paperless/consume; move_dir /opt/stacks/docs/state/stirling/tessdata /mnt/data/apps/stirling/tessdata; move_dir /opt/stacks/docs/config/stirling /mnt/data/apps/stirling/config; move_dir /opt/stacks/media/state/suwayomi /mnt/data/apps/suwayomi; move_dir /mnt/data/downloads/uploads /mnt/data/media/music/inbox/user; move_dir /mnt/data/apps/filebrowser-upload/uploads /mnt/data/media/music/inbox/user; move_dir /mnt/data/downloads/slskd/complete /mnt/data/media/music/inbox/slskd/complete; move_dir /mnt/data/apps/slskd/downloads/complete /mnt/data/media/music/inbox/slskd/complete; move_dir /mnt/data/downloads/slskd/incomplete /mnt/data/media/music/inbox/slskd/incomplete; move_dir /mnt/data/apps/slskd/downloads/incomplete /mnt/data/media/music/inbox/slskd/incomplete; for d in /mnt/data/apps/stirling/logs /mnt/data/apps/stirling/customFiles /mnt/data/apps/stirling/pipeline; do sudo mkdir -p "$$d"; done; sudo chown -R 1000:1000 /mnt/data/apps/paperless /mnt/data/apps/stirling /mnt/data/apps/suwayomi /mnt/data/media/music/inbox; if [ -d /mnt/data/downloads ]; then sudo find /mnt/data/downloads -depth -type d -empty -delete; fi; if [ -d /mnt/data/apps/filebrowser-upload ]; then sudo find /mnt/data/apps/filebrowser-upload -depth -type d -empty -delete; fi; if [ -d /mnt/data/apps/slskd ]; then sudo find /mnt/data/apps/slskd -depth -type d -empty -delete; fi; start docs stirling-pdf; start docs paperless; start media suwayomi; start media slskd; start apps filebrowser-upload'

host:
	rsync -a bootstrap.sh host $(HOST):/tmp/chill/
	ssh $(HOST) 'cd /tmp/chill && sudo sh bootstrap.sh'

vps:
	# Git owns all public Caddy sites now; bootstrap.sh validates + reloads Caddy.
	# NOTE: no rsync on the VPS — ship via tar over ssh.
	tar --exclude='./live-backup-*' --exclude='live-backup-*' -c -C vps . | $(VPS_SSH) 'rm -rf /tmp/chill-vps && mkdir -p /tmp/chill-vps && tar -x -C /tmp/chill-vps'
	$(VPS_SSH) 'cd /tmp/chill-vps && sh bootstrap.sh'
	tar -c -C vps/sites . | ssh $(HOST) 'sudo rm -rf /opt/homelab-public-sites && sudo mkdir -p /opt/homelab-public-sites && sudo tar -x -C /opt/homelab-public-sites'

sync-public-sites:
	tar -c -C vps/sites . | ssh $(HOST) 'sudo rm -rf /opt/homelab-public-sites && sudo mkdir -p /opt/homelab-public-sites && sudo tar -x -C /opt/homelab-public-sites'

backup-now:
	ssh $(HOST) 'sudo systemctl start homelab-backup && journalctl -u homelab-backup -n 30 --no-pager'

# The only backup test that counts: get files back out and validate them.
# Checks dumps, key config, VPS pull, and cheap photo-tree presence.
restore-test:
	ssh $(HOST) 'sudo sh -c '\''set -eu; set -a; . /etc/homelab.env; set +a; rt=/opt/restore-test; cleanup() { rm -rf "$$rt"; }; trap cleanup EXIT; rm -rf "$$rt"; mkdir -p "$$rt"; chill_include=; if restic ls latest /opt/vps-backup/wireguard/chill0.conf >/dev/null 2>&1; then chill_include="--include /opt/vps-backup/wireguard/chill0.conf"; fi; restic restore latest --target "$$rt" --include /mnt/fast/dumps/immich.sql --include /mnt/fast/dumps/paperless.sql --include /mnt/fast/dumps/gotify.db --include /etc/homelab.env --include /etc/wireguard/wg0.conf --include /opt/vps-backup/Caddyfile --include /opt/vps-backup/nftables.conf $$chill_include; test -s "$$rt/mnt/fast/dumps/immich.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/immich.sql"; test -s "$$rt/mnt/fast/dumps/paperless.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/paperless.sql"; test -s "$$rt/mnt/fast/dumps/gotify.db"; sqlite3 "$$rt/mnt/fast/dumps/gotify.db" "PRAGMA integrity_check;" | grep -qx ok; test -s "$$rt/etc/homelab.env"; grep -Eq "^[A-Z0-9_]+=" "$$rt/etc/homelab.env"; test -s "$$rt/etc/wireguard/wg0.conf"; grep -q "^\[Interface\]" "$$rt/etc/wireguard/wg0.conf"; test -s "$$rt/opt/vps-backup/Caddyfile"; grep -q "import /etc/caddy/sites/[*].caddy" "$$rt/opt/vps-backup/Caddyfile"; test -s "$$rt/opt/vps-backup/nftables.conf"; grep -q "homelab_nat" "$$rt/opt/vps-backup/nftables.conf"; if [ -n "$$chill_include" ]; then test -s "$$rt/opt/vps-backup/wireguard/chill0.conf"; grep -q "^\[Interface\]" "$$rt/opt/vps-backup/wireguard/chill0.conf"; fi; restic ls latest /mnt/data/photos >/dev/null; echo "restore-test ok"'\'''

# Is the VPS<->chill-01 link alive? "latest handshake" older than a couple of
# minutes means trouble. Phones are on Tailscale, not here — use `tailscale status`.
# Static kernel link on chill0:51824 (stage 2); `sudo wg show` also covers the
tunnel:
	$(VPS_SSH) 'sudo wg show chill0'

check:
	set -e; for s in $(STACKS); do (cd stacks/$$s; set -a; . ../defaults.env; [ ! -f .env.example ] || . ./.env.example; set +a; docker compose config -q); done
	host/public-check.sh --self-check
	PUBLIC_CADDY_SITES_DIR=vps/sites PRIVATE_CADDYFILE=stacks/edge/Caddyfile host/public-check.sh --config-lint
	wide_binds=$$(grep -RInE '^[[:space:]]*-[[:space:]]*"?(:|0\.0\.0\.0:)' stacks/*/docker-compose.yml || true); test -z "$$wide_binds" || { echo "Undocumented wide port bind(s):" >&2; echo "$$wide_binds" >&2; exit 1; }
	host_net=$$(grep -RInE '^[[:space:]]*network_mode:[[:space:]]*host' stacks/*/docker-compose.yml | grep -Ev 'stacks/(comms|observability)/docker-compose.yml' || true); test -z "$$host_net" || { echo "Undocumented host network service(s):" >&2; echo "$$host_net" >&2; exit 1; }
	shellcheck bootstrap.sh host/backup.sh host/backup-watchdog.sh host/public-check.sh vps/bootstrap.sh stacks/media/config/slskd/autotag.sh

# The private Caddyfile is a bind mount, so `make deploy` copies it but the
# running container never re-reads it. Restart (not `caddy reload`, which was
# observed silently keeping the old config on 2026-09-16): a stale file looks
# like "my edit did nothing". Validate first for a loud failure instead.
edge-reload:
	ssh $(HOST) 'cd /opt/stacks/edge && sudo docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile && sudo docker compose -p edge restart caddy'

.PHONY: deploy storage-cleanup host vps sync-public-sites backup-now restore-test tunnel check edge-reload
