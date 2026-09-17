HOST ?= deploy@10.44.0.2
# VPS via the vps-ingress SSH alias (port 4522 + key in ~/.ssh/config); 22 is closed.
VPS_SSH ?= ssh vps-ingress
TRAFFIC_REPORT ?= traffic-report.html
STACKS = apps comms docs edge media observability photos
RETIRED_STACKS = privacy

# git is the source of truth; Dockge is for logs and restarts, not for editing YAML behind git's back.
# Ship the local working tree (commit + push first). No git pull on the host,
# so no deploy-key scoping issue when splitting repos.
deploy:
	rsync -a --delete stacks/ $(HOST):/tmp/chill-stacks/
	ssh $(HOST) 'for s in $(RETIRED_STACKS); do if [ -f /opt/stacks/$$s/docker-compose.yml ]; then (cd /opt/stacks/$$s && sudo docker compose -p $$s down --remove-orphans); fi; done && sudo rsync -a --delete --exclude .env --exclude state/ /tmp/chill-stacks/ /opt/stacks/ && sudo mkdir -p /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/edge/state/home /opt/stacks/media/state && sudo chown -R 1000:1000 /opt/stacks/apps/state/filebrowser-quantum /opt/stacks/media/state && for s in $(STACKS); do (cd /opt/stacks/$$s && sudo docker compose -p $$s up -d --pull missing --remove-orphans); done'
	# NOTE: --pull missing (not always): the CLI flag overrides compose pull_policy, and redlib is a
	# local source build (pull_policy: never) that --pull always would try to fetch from a registry.
	# Retired stack state/.env survives; only containers and git-owned config are removed.

host:
	rsync -a bootstrap.sh host $(HOST):/tmp/chill/
	ssh $(HOST) 'cd /tmp/chill && sudo sh bootstrap.sh'

vps:
	# Git owns all public Caddy sites now; bootstrap.sh validates + reloads Caddy.
	# NOTE: no rsync on the VPS — ship via tar over ssh.
	tar -c -C vps . | $(VPS_SSH) 'rm -rf /tmp/chill-vps && mkdir -p /tmp/chill-vps && tar -x -C /tmp/chill-vps'
	$(VPS_SSH) 'cd /tmp/chill-vps && sh bootstrap.sh'

backup-now:
	ssh $(HOST) 'sudo systemctl start homelab-backup && journalctl -u homelab-backup -n 30 --no-pager'

# The only backup test that counts: get files back out and look at them.
# Covers a pg_dump (immich) and a sqlite .backup (gotify).
restore-test:
	ssh $(HOST) "sudo sh -c 'set -a; . /etc/homelab.env; restic restore latest --target /tmp/rt --include /opt/dumps/immich.sql --include /opt/dumps/gotify.db; head -c 300 /tmp/rt/opt/dumps/immich.sql; echo; sqlite3 /tmp/rt/opt/dumps/gotify.db \"PRAGMA integrity_check;\"; rm -rf /tmp/rt'"

# Is the VPS<->chill-01 link alive? "latest handshake" older than a couple of
# minutes means trouble. Phones are on Tailscale, not here — use `tailscale status`.
# Static kernel link on chill0:51824 (stage 2); `sudo wg show` also covers the
tunnel:
	$(VPS_SSH) 'sudo wg show chill0'

check:
	for s in $(STACKS); do (cd stacks/$$s && docker compose config -q); done
	shellcheck bootstrap.sh host/backup.sh host/backup-watchdog.sh host/disk-usage.sh host/public-check.sh host/proxmox-backup.sh vps/bootstrap.sh stacks/media/scripts/ingest-music.sh stacks/media/config/slskd/autotag.sh

# The private Caddyfile is a bind mount, so `make deploy` copies it but the
# running container never re-reads it. Restart (not `caddy reload`, which was
# observed silently keeping the old config on 2026-09-16): a stale file looks
# like "my edit did nothing". Validate first for a loud failure instead.
edge-reload:
	ssh $(HOST) 'cd /opt/stacks/edge && sudo docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile && sudo docker compose -p edge restart caddy'

traffic:
	$(VPS_SSH) 'sudo sh -c '\''geo=; [ -f /var/lib/GeoIP/GeoLite2-City.mmdb ] && geo="--geoip-database=/var/lib/GeoIP/GeoLite2-City.mmdb"; zcat -f /var/log/caddy/access.log* 2>/dev/null | goaccess - --log-format=CADDY --no-progress $$geo -o -'\''' > $(TRAFFIC_REPORT)
	rsync -a $(TRAFFIC_REPORT) $(HOST):/tmp/homelab-traffic-report.html
	ssh $(HOST) 'sudo mkdir -p /opt/stacks/edge/state/home && sudo install -m 644 /tmp/homelab-traffic-report.html /opt/stacks/edge/state/home/traffic.html && rm -f /tmp/homelab-traffic-report.html'
	@echo "Report written to $(TRAFFIC_REPORT) and published to https://home.h.malice.biz/status/traffic.html"

.PHONY: deploy host vps backup-now restore-test tunnel check edge-reload traffic
