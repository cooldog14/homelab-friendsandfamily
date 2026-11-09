# Tailscale is the admin path (never the WG tunnel, which is VPS-only).
HOST ?= chill-01
# Bare `chill-01` needs an ssh alias (HostName 100.92.173.71, User deploy);
# override with HOST=deploy@10.44.0.2 only from a WG-connected host.
# VPS via the vps-ingress SSH alias (port 4522 + key in ~/.ssh/config); 22 is closed.
VPS_SSH ?= ssh vps-ingress
STACKS = apps comms docs edge games media observability photos
# Ansible installs shellcheck on the host; a dev box without it falls back
# to the container so `make check` works everywhere.
SHELLCHECK ?= $(shell command -v shellcheck 2>/dev/null || printf "docker run --rm -v %s:/mnt -w /mnt koalaman/shellcheck:stable" "$(CURDIR)")

# git is the source of truth.
# Ship the local working tree (commit + push first). No git pull on the host,
# so no deploy-key scoping issue when splitting repos.
deploy:
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'set -e; sudo rsync -a --delete --exclude .env --exclude state/ --exclude docs/config/stirling/ --exclude media/suwayomi-auth-password /tmp/chill-stacks/ /opt/stacks/ && sudo install -d -o 1000 -g 1000 /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/apps/state/filebrowser-upload /opt/stacks/apps/state/filebrowser-family /opt/stacks/comms/state/screego /opt/stacks/media/state /opt/stacks/media/state/gluetun /opt/stacks/media/state/jellyfin-config /opt/stacks/media/state/qbittorrent /opt/stacks/media/state/prowlarr /opt/stacks/media/state/radarr /opt/stacks/media/state/sonarr /opt/stacks/media/state/bazarr /opt/stacks/media/state/jellyseerr /opt/stacks/media/state/navidrome /opt/stacks/media/state/wrtag /opt/stacks/media/state/octo-fiesta /opt/stacks/media/state/slskd /mnt/fast/jellyfin-cache /mnt/fast/scratch /mnt/fast/imports /mnt/data/family /mnt/data/photos /mnt/data/apps/minecraft /mnt/data/apps/paperless /mnt/data/apps/paperless/data /mnt/data/apps/paperless/media /mnt/data/apps/paperless/export /mnt/data/apps/paperless/consume /mnt/data/apps/stirling /mnt/data/apps/stirling/tessdata /mnt/data/apps/stirling/config /mnt/data/apps/stirling/logs /mnt/data/apps/stirling/customFiles /mnt/data/apps/stirling/pipeline /mnt/data/apps/suwayomi /mnt/data/media/music/inbox /mnt/data/media/music/inbox/user /mnt/data/media/music/inbox/slskd/complete /mnt/data/media/music/inbox/slskd/incomplete && sudo install -d -m 0700 /mnt/fast/dumps && sudo install -d -m 0755 -o 65534 -g 65534 /opt/stacks/observability/state/prometheus /opt/stacks/observability/state/alertmanager && sudo install -d -m 0755 -o 472 -g 472 /opt/stacks/observability/state/grafana && for s in $(STACKS); do (cd /opt/stacks/$$s && sudo docker compose -p $$s up -d --pull missing --remove-orphans); done'
	# NOTE: --pull missing (not always): the CLI flag overrides compose pull_policy.

# Host state is Ansible-owned: bootstrap.sh is gone, and the playbook is
# idempotent (second run reports changed=0).
host:
	ansible-playbook ansible/chill.yml

vps:
	ansible-playbook ansible/vps.yml

ansible-check:
	ansible-playbook --syntax-check ansible/chill.yml ansible/vps.yml

# Offline: no Proxmox credentials needed, so CI can run it.
tofu-check:
	cd tofu && tofu fmt -check -recursive . && tofu init -backend=false -input=false >/dev/null && tofu validate

tofu-plan:
	cd tofu && tofu init -input=false && tofu plan

# The only backup test that counts: get files back out and validate them.
# Checks dumps, key config, VPS pull, and cheap photo-tree presence.
restore-test:
	ssh $(HOST) 'sudo sh -c '\''set -eu; set -a; . /etc/homelab.env; set +a; rt=/opt/restore-test; cleanup() { rm -rf "$$rt"; }; trap cleanup EXIT; rm -rf "$$rt"; mkdir -p "$$rt"; chill_include=; if restic ls latest /opt/vps-backup/wireguard/chill0.conf >/dev/null 2>&1; then chill_include="--include /opt/vps-backup/wireguard/chill0.conf"; fi; restic restore latest --target "$$rt" --include /mnt/fast/dumps/immich.sql --include /mnt/fast/dumps/paperless.sql --include /mnt/fast/dumps/kavita.db --include /mnt/fast/dumps/gotify.db --include /mnt/fast/dumps/beszel.db --include /etc/homelab.env --include /etc/wireguard/wg0.conf --include /opt/vps-backup/Caddyfile --include /opt/vps-backup/nftables.conf $$chill_include; test -s "$$rt/mnt/fast/dumps/immich.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/immich.sql"; test -s "$$rt/mnt/fast/dumps/paperless.sql"; grep -q "PostgreSQL database dump" "$$rt/mnt/fast/dumps/paperless.sql"; for db in kavita gotify beszel; do test -s "$$rt/mnt/fast/dumps/$$db.db"; sqlite3 "$$rt/mnt/fast/dumps/$$db.db" "PRAGMA integrity_check;" | grep -qx ok; done; test -s "$$rt/etc/homelab.env"; grep -Eq "^[A-Z0-9_]+=" "$$rt/etc/homelab.env"; test -s "$$rt/etc/wireguard/wg0.conf"; grep -q "^\[Interface\]" "$$rt/etc/wireguard/wg0.conf"; test -s "$$rt/opt/vps-backup/Caddyfile"; grep -q "import /etc/caddy/sites/[*].caddy" "$$rt/opt/vps-backup/Caddyfile"; test -s "$$rt/opt/vps-backup/nftables.conf"; grep -q "homelab_nat" "$$rt/opt/vps-backup/nftables.conf"; if [ -n "$$chill_include" ]; then test -s "$$rt/opt/vps-backup/wireguard/chill0.conf"; grep -q "^\[Interface\]" "$$rt/opt/vps-backup/wireguard/chill0.conf"; fi; restic ls latest /mnt/data/photos >/dev/null; echo "restore-test ok"'\'''

check:
	set -e; for s in $(STACKS); do (cd stacks/$$s; set -a; [ ! -f .env.example ] || . ./.env.example; set +a; docker compose config >/dev/null); done
	# Edge uses adapt, not validate: the cloudflare DNS plugin rejects any
	# non-real API token during provisioning, and the real token never leaves hosts.
	docker run --rm -v "$(CURDIR)/stacks/edge/Caddyfile:/etc/caddy/Caddyfile:ro" ghcr.io/caddybuilds/caddy-cloudflare:2.11.4-alpine caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
	docker run --rm -v "$(CURDIR)/vps/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$(CURDIR)/vps/sites:/etc/caddy/sites:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	PUBLIC_CADDY_SITES_DIR=vps/sites PRIVATE_CADDYFILE=stacks/edge/Caddyfile host/public-check.sh --config-lint
	wide_binds=$$(grep -RInE '^[[:space:]]*-[[:space:]]*"?(:|0\.0\.0\.0:)' stacks/*/docker-compose.yml || true); test -z "$$wide_binds" || { echo "Undocumented wide port bind(s):" >&2; echo "$$wide_binds" >&2; exit 1; }
	host_net=$$(grep -RInE '^[[:space:]]*network_mode:[[:space:]]*host' stacks/*/docker-compose.yml | grep -Ev 'stacks/(comms|observability)/docker-compose.yml' || true); test -z "$$host_net" || { echo "Undocumented host network service(s):" >&2; echo "$$host_net" >&2; exit 1; }
	$(SHELLCHECK) host/backup.sh host/backup-watchdog.sh host/public-check.sh host/metrics.sh host/firewall-neko.sh stacks/media/config/slskd/autotag.sh
	# Observability: promtool/amtool/blackbox validate the exact files the
	# containers load, so a broken rule fails here instead of silently.
	# The images set their server binary as ENTRYPOINT, hence --entrypoint.
	docker run --rm --entrypoint promtool -v "$(CURDIR)/stacks/observability/prometheus:/etc/prometheus:ro" prom/prometheus:v3.16.0 check config /etc/prometheus/prometheus.yml
	docker run --rm --entrypoint promtool -v "$(CURDIR)/stacks/observability/prometheus/rules:/rules:ro" prom/prometheus:v3.16.0 check rules /rules/homelab.yml
	docker run --rm --entrypoint amtool -v "$(CURDIR)/stacks/observability/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.34.2 check-config /etc/alertmanager/alertmanager.yml
	docker run --rm -v "$(CURDIR)/stacks/observability/blackbox/blackbox.yml:/etc/blackbox_exporter/config.yml:ro" prom/blackbox-exporter:v0.29.1 --config.file=/etc/blackbox_exporter/config.yml --config.check

# Caddy reads its Caddyfile once at start: `up -d` on an unchanged compose file
# is a no-op, so route edits need an explicit restart.
edge-reload:
	ssh $(HOST) 'cd /opt/stacks/edge && sudo docker compose -p edge restart caddy'

.PHONY: deploy host vps restore-test check edge-reload ansible-check tofu-check tofu-plan
