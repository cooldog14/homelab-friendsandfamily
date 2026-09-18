HOST ?= deploy@10.44.0.2
# VPS via the vps-ingress SSH alias (port 4522 + key in ~/.ssh/config); 22 is closed.
VPS_SSH ?= ssh vps-ingress
STACKS = apps comms docs edge media observability photos

# git is the source of truth; Dockge is for logs and restarts, not for editing YAML behind git's back.
# Ship the local working tree (commit + push first). No git pull on the host,
# so no deploy-key scoping issue when splitting repos.
deploy: sync-public-sites
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'sudo rsync -a --delete --exclude .env --exclude state/ /tmp/chill-stacks/ /opt/stacks/ && sudo mkdir -p /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /opt/stacks/media/state /opt/stacks/media/state/gluetun /opt/stacks/media/state/jellyfin-config /opt/stacks/media/state/jellyfin-cache /opt/stacks/media/state/qbittorrent /opt/stacks/media/state/prowlarr /opt/stacks/media/state/radarr /opt/stacks/media/state/sonarr /opt/stacks/media/state/bazarr /opt/stacks/media/state/jellyseerr /opt/stacks/media/state/navidrome /opt/stacks/media/state/wrtag /opt/stacks/media/state/octo-fiesta /opt/stacks/media/state/suwayomi /opt/stacks/media/state/slskd /mnt/data/photos /mnt/data/downloads/uploads /mnt/data/downloads/slskd/complete /mnt/data/downloads/slskd/incomplete && sudo chown -R 1000:1000 /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /mnt/data/photos /mnt/data/downloads/uploads /mnt/data/downloads/slskd /opt/stacks/media/state && for s in $(STACKS); do (cd /opt/stacks/$$s && sudo docker compose -p $$s up -d --pull missing --remove-orphans); done'
	# NOTE: --pull missing (not always): the CLI flag overrides compose pull_policy, and redlib is a
	# local source build (pull_policy: never) that --pull always would try to fetch from a registry.

host:
	rsync -a bootstrap.sh host $(HOST):/tmp/chill/
	ssh $(HOST) 'cd /tmp/chill && sudo sh bootstrap.sh'

vps:
	# Git owns all public Caddy sites now; bootstrap.sh validates + reloads Caddy.
	# NOTE: no rsync on the VPS — ship via tar over ssh.
	tar -c -C vps . | $(VPS_SSH) 'rm -rf /tmp/chill-vps && mkdir -p /tmp/chill-vps && tar -x -C /tmp/chill-vps'
	$(VPS_SSH) 'cd /tmp/chill-vps && sh bootstrap.sh'
	tar -c -C vps/sites . | ssh $(HOST) 'sudo rm -rf /opt/homelab-public-sites && sudo mkdir -p /opt/homelab-public-sites && sudo tar -x -C /opt/homelab-public-sites'

sync-public-sites:
	tar -c -C vps/sites . | ssh $(HOST) 'sudo rm -rf /opt/homelab-public-sites && sudo mkdir -p /opt/homelab-public-sites && sudo tar -x -C /opt/homelab-public-sites'

backup-now:
	ssh $(HOST) 'sudo systemctl start homelab-backup && journalctl -u homelab-backup -n 30 --no-pager'

# The only backup test that counts: get files back out and validate them.
# Checks dumps, key config, VPS pull, and cheap photo-tree presence.
restore-test:
	ssh $(HOST) 'sudo sh -c '\''set -eu; set -a; . /etc/homelab.env; set +a; rt=/opt/restore-test; cleanup() { rm -rf "$$rt"; }; trap cleanup EXIT; rm -rf "$$rt"; mkdir -p "$$rt"; chill_include=; if restic ls latest /opt/vps-backup/wireguard/chill0.conf >/dev/null 2>&1; then chill_include="--include /opt/vps-backup/wireguard/chill0.conf"; fi; restic restore latest --target "$$rt" --include /opt/dumps/immich.sql --include /opt/dumps/paperless.sql --include /opt/dumps/gotify.db --include /etc/homelab.env --include /etc/wireguard/wg0.conf --include /opt/vps-backup/Caddyfile --include /opt/vps-backup/nftables.conf $$chill_include; test -s "$$rt/opt/dumps/immich.sql"; grep -q "PostgreSQL database dump" "$$rt/opt/dumps/immich.sql"; test -s "$$rt/opt/dumps/paperless.sql"; grep -q "PostgreSQL database dump" "$$rt/opt/dumps/paperless.sql"; test -s "$$rt/opt/dumps/gotify.db"; sqlite3 "$$rt/opt/dumps/gotify.db" "PRAGMA integrity_check;" | grep -qx ok; test -s "$$rt/etc/homelab.env"; grep -Eq "^[A-Z0-9_]+=" "$$rt/etc/homelab.env"; test -s "$$rt/etc/wireguard/wg0.conf"; grep -q "^\[Interface\]" "$$rt/etc/wireguard/wg0.conf"; test -s "$$rt/opt/vps-backup/Caddyfile"; grep -q "import /etc/caddy/sites/[*].caddy" "$$rt/opt/vps-backup/Caddyfile"; test -s "$$rt/opt/vps-backup/nftables.conf"; grep -q "homelab_nat" "$$rt/opt/vps-backup/nftables.conf"; if [ -n "$$chill_include" ]; then test -s "$$rt/opt/vps-backup/wireguard/chill0.conf"; grep -q "^\[Interface\]" "$$rt/opt/vps-backup/wireguard/chill0.conf"; fi; restic ls latest /mnt/fast/photos >/dev/null; echo "restore-test ok"'\'''

# Is the VPS<->chill-01 link alive? "latest handshake" older than a couple of
# minutes means trouble. Phones are on Tailscale, not here — use `tailscale status`.
# Static kernel link on chill0:51824 (stage 2); `sudo wg show` also covers the
tunnel:
	$(VPS_SSH) 'sudo wg show chill0'

check:
	for s in $(STACKS); do (cd stacks/$$s && docker compose config -q); done
	shellcheck bootstrap.sh host/backup.sh host/backup-watchdog.sh host/public-check.sh vps/bootstrap.sh vps/traffic-report.sh stacks/media/config/slskd/autotag.sh

# The private Caddyfile is a bind mount, so `make deploy` copies it but the
# running container never re-reads it. Restart (not `caddy reload`, which was
# observed silently keeping the old config on 2026-09-16): a stale file looks
# like "my edit did nothing". Validate first for a loud failure instead.
edge-reload:
	ssh $(HOST) 'cd /opt/stacks/edge && sudo docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile && sudo docker compose -p edge restart caddy'

traffic:
	$(VPS_SSH) 'sudo systemctl start homelab-traffic-report.service && sudo systemctl status homelab-traffic-report.service --no-pager --lines=5'
	@echo "Traffic report refreshed at https://home.h.malice.biz/status/traffic.html"

.PHONY: deploy host vps sync-public-sites backup-now restore-test tunnel check edge-reload traffic
