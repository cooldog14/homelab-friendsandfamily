# Tailscale is the admin path (never the WG tunnel, which is VPS-only).
HOST ?= chill-01
# Bare `chill-01` needs an ssh alias (HostName 100.92.173.71, User deploy);
# override with HOST=deploy@10.44.0.2 only from a WG-connected host.
# VPS via the vps-ingress SSH alias (port 4522 + key in ~/.ssh/config); 22 is closed.
VPS_SSH ?= ssh vps-ingress
STACKS = apps comms docs edge games media observability photos

# git is the source of truth.
# Ship the local working tree (commit + push first). No git pull on the host,
# so no deploy-key scoping issue when splitting repos.
deploy:
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'set -e; sudo rsync -a --delete --exclude .env --exclude state/ --exclude docs/config/stirling/ /tmp/chill-stacks/ /opt/stacks/ && sudo install -d -o 1000 -g 1000 /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /opt/stacks/apps/state/filebrowser-family /opt/stacks/media/state /opt/stacks/media/state/gluetun /opt/stacks/media/state/jellyfin-config /opt/stacks/media/state/qbittorrent /opt/stacks/media/state/prowlarr /opt/stacks/media/state/radarr /opt/stacks/media/state/sonarr /opt/stacks/media/state/bazarr /opt/stacks/media/state/jellyseerr /opt/stacks/media/state/navidrome /opt/stacks/media/state/wrtag /opt/stacks/media/state/octo-fiesta /opt/stacks/media/state/slskd /mnt/fast/jellyfin-cache /mnt/fast/scratch /mnt/fast/imports /mnt/data/family /mnt/data/photos /mnt/data/apps/minecraft /mnt/data/apps/paperless /mnt/data/apps/paperless/data /mnt/data/apps/paperless/media /mnt/data/apps/paperless/export /mnt/data/apps/paperless/consume /mnt/data/apps/stirling /mnt/data/apps/stirling/tessdata /mnt/data/apps/stirling/config /mnt/data/apps/stirling/logs /mnt/data/apps/stirling/customFiles /mnt/data/apps/stirling/pipeline /mnt/data/apps/suwayomi /mnt/data/media/music/inbox /mnt/data/media/music/inbox/user /mnt/data/media/music/inbox/slskd/complete /mnt/data/media/music/inbox/slskd/incomplete && sudo install -d -m 0700 /mnt/fast/dumps && for s in $(STACKS); do (cd /opt/stacks/$$s && sudo docker compose -p $$s up -d --pull missing --remove-orphans); done'
	# NOTE: --pull missing (not always): the CLI flag overrides compose pull_policy.

host:
	rsync -a bootstrap.sh host $(HOST):/tmp/chill/
	ssh $(HOST) 'cd /tmp/chill && sudo sh bootstrap.sh'

vps:
	# Git owns all public Caddy sites now; bootstrap.sh validates + reloads Caddy.
	# NOTE: no rsync on the VPS — ship via tar over ssh.
	tar -c -C vps . | $(VPS_SSH) 'rm -rf /tmp/chill-vps && mkdir -p /tmp/chill-vps && tar -x -C /tmp/chill-vps'
	$(VPS_SSH) 'cd /tmp/chill-vps && sh bootstrap.sh'

# The only backup test that counts: get files back out and validate them.
# Checks dumps, key config, VPS pull, and cheap photo-tree presence.
restore-test:
	ssh $(HOST) 'sudo sh -c '\''set -eu; set -a; . /etc/homelab.env; set +a; rt=/opt/restore-test; cleanup() { rm -rf "$$rt"; }; trap cleanup EXIT; rm -rf "$$rt"; mkdir -p "$$rt"; chill_include=; if restic ls latest /opt/vps-backup/wireguard/chill0.conf >/dev/null 2>&1; then chill_include="--include /opt/vps-backup/wireguard/chill0.conf"; fi; restic restore latest --target "$$rt" --include /mnt/fast/dumps/immich.sql --include /mnt/fast/dumps/paperless.sql --include /mnt/fast/dumps/kavita.db --include /mnt/fast/dumps/gotify.db --include /mnt/fast/dumps/beszel.db --include /etc/homelab.env --include /etc/wireguard/wg0.conf --include /opt/vps-backup/Caddyfile --include /opt/vps-backup/nftables.conf $$chill_include; test -s "$$rt/mnt/fast/dumps/immich.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/immich.sql"; test -s "$$rt/mnt/fast/dumps/paperless.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/paperless.sql"; for db in kavita gotify beszel; do test -s "$$rt/mnt/fast/dumps/$$db.db"; sqlite3 "$$rt/mnt/fast/dumps/$$db.db" "PRAGMA integrity_check;" | grep -qx ok; done; test -s "$$rt/etc/homelab.env"; grep -Eq "^[A-Z0-9_]+=" "$$rt/etc/homelab.env"; test -s "$$rt/etc/wireguard/wg0.conf"; grep -q "^\[Interface\]" "$$rt/etc/wireguard/wg0.conf"; test -s "$$rt/opt/vps-backup/Caddyfile"; grep -q "import /etc/caddy/sites/[*].caddy" "$$rt/opt/vps-backup/Caddyfile"; test -s "$$rt/opt/vps-backup/nftables.conf"; grep -q "homelab_nat" "$$rt/opt/vps-backup/nftables.conf"; if [ -n "$$chill_include" ]; then test -s "$$rt/opt/vps-backup/wireguard/chill0.conf"; grep -q "^\[Interface\]" "$$rt/opt/vps-backup/wireguard/chill0.conf"; fi; restic ls latest /mnt/data/photos >/dev/null; echo "restore-test ok"'\'''

check:
	set -e; for s in $(STACKS); do (cd stacks/$$s; set -a; [ ! -f .env.example ] || . ./.env.example; set +a; docker compose config >/dev/null); done
	PUBLIC_CADDY_SITES_DIR=vps/sites PRIVATE_CADDYFILE=stacks/edge/Caddyfile host/public-check.sh --config-lint
	wide_binds=$$(grep -RInE '^[[:space:]]*-[[:space:]]*"?(:|0\.0\.0\.0:)' stacks/*/docker-compose.yml || true); test -z "$$wide_binds" || { echo "Undocumented wide port bind(s):" >&2; echo "$$wide_binds" >&2; exit 1; }
	host_net=$$(grep -RInE '^[[:space:]]*network_mode:[[:space:]]*host' stacks/*/docker-compose.yml | grep -Ev 'stacks/(comms|observability)/docker-compose.yml' || true); test -z "$$host_net" || { echo "Undocumented host network service(s):" >&2; echo "$$host_net" >&2; exit 1; }
	shellcheck bootstrap.sh host/backup.sh host/backup-watchdog.sh host/public-check.sh vps/bootstrap.sh stacks/media/config/slskd/autotag.sh

.PHONY: deploy host vps restore-test check
