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

# git is the source of truth. `make deploy` archives HEAD, never the dirty
# working tree, and records the deployed commit on the host.
deploy: check
	host/deploy.sh "$(HOST)"

# Host state is Ansible-owned: bootstrap.sh is gone, and the playbook is
# idempotent (second run reports changed=0).
host:
	ansible-playbook ansible/chill.yml

vps:
	ansible-playbook ansible/vps.yml

hypervisor:
	ansible-playbook ansible/malice.yml

ansible-check:
	ansible-playbook --syntax-check ansible/chill.yml ansible/vps.yml ansible/malice.yml

# Offline: no Proxmox credentials needed, so CI can run it.
tofu-check:
	cd tofu && tofu fmt -check -recursive . && tofu init -backend=false -input=false >/dev/null && tofu validate

tofu-plan:
	cd tofu && tofu init -input=false && tofu plan

# The only backup test that counts: get files back out and validate them.
# Checks every database dump, key config, VPS pull, and photo-tree presence.
restore-test:
	ssh $(HOST) 'sudo sh -s' < host/restore-test.sh

check:
	set -e; for s in $(STACKS); do (cd stacks/$$s; set -a; [ ! -f .env.example ] || . ./.env.example; set +a; docker compose config >/dev/null); done
	# Edge uses adapt, not validate: the cloudflare DNS plugin rejects any
	# non-real API token during provisioning, and the real token never leaves hosts.
	docker run --rm -v "$(CURDIR)/stacks/edge/Caddyfile:/etc/caddy/Caddyfile:ro" ghcr.io/caddybuilds/caddy-cloudflare:2.11.9-alpine caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
	docker run --rm -v "$(CURDIR)/vps/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$(CURDIR)/vps/sites:/etc/caddy/sites:ro" caddy:2.11.9 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	PUBLIC_CADDY_SITES_DIR=vps/sites PRIVATE_CADDYFILE=stacks/edge/Caddyfile host/public-check.sh --config-lint
	wide_binds=$$(grep -RInE '^[[:space:]]*-[[:space:]]*"?(:|0\.0\.0\.0:)' stacks/*/docker-compose.yml || true); test -z "$$wide_binds" || { echo "Undocumented wide port bind(s):" >&2; echo "$$wide_binds" >&2; exit 1; }
	host_net=$$(grep -RInE '^[[:space:]]*network_mode:[[:space:]]*host' stacks/*/docker-compose.yml | grep -Ev 'stacks/comms/docker-compose.yml' || true); test -z "$$host_net" || { echo "Undocumented host network service(s):" >&2; echo "$$host_net" >&2; exit 1; }
	$(SHELLCHECK) host/backup.sh host/backup-watchdog.sh host/public-check.sh host/metrics.sh host/firewall-neko.sh host/restic-check.sh host/restore-test.sh host/deploy.sh host/edge-heartbeat.sh stacks/media/config/slskd/autotag.sh
	PYTHONPYCACHEPREFIX=/tmp/homelab-pycache python3 -m py_compile host/restic-retention.py
	# Observability: promtool/amtool/blackbox validate the exact files the
	# containers load, so a broken rule fails here instead of silently.
	# The images set their server binary as ENTRYPOINT, hence --entrypoint.
	docker run --rm --entrypoint promtool -v "$(CURDIR)/stacks/observability/prometheus:/etc/prometheus:ro" prom/prometheus:v3.16.0 check config /etc/prometheus/prometheus.yml
	docker run --rm --entrypoint promtool -v "$(CURDIR)/stacks/observability/prometheus/rules:/rules:ro" prom/prometheus:v3.16.0 check rules /rules/homelab.yml
	docker run --rm --entrypoint amtool -v "$(CURDIR)/stacks/observability/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.34.2 check-config /etc/alertmanager/alertmanager.yml
	docker run --rm -v "$(CURDIR)/stacks/observability/blackbox/blackbox.yml:/etc/blackbox_exporter/config.yml:ro" prom/blackbox-exporter:v0.29.1 --config.file=/etc/blackbox_exporter/config.yml --config.check
	# Grafana provisions these files verbatim: invalid JSON must fail here.
	set -e; for f in stacks/observability/grafana/dashboards/*.json; do python3 -m json.tool "$$f" >/dev/null; done

# Caddy reads its Caddyfile once at start: `up -d` on an unchanged compose file
# is a no-op, so route edits need an explicit restart.
edge-reload:
	ssh $(HOST) 'cd /opt/stacks/edge && sudo docker compose -p edge restart caddy'

.PHONY: deploy host vps hypervisor restore-test check edge-reload ansible-check tofu-check tofu-plan
