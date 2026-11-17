#!/bin/sh
# Deploy an exact committed tree. Local uncommitted changes are deliberately
# not shipped; application .env and state never leave the host.
set -eu

host=${1:-chill-01}
repo=$(git rev-parse --show-toplevel)
cd "$repo"

if ! git diff --quiet -- stacks || ! git diff --cached --quiet -- stacks; then
  echo "deploy: stacks/ has tracked changes; commit them first" >&2
  exit 1
fi
if [ -n "$(git ls-files --others --exclude-standard -- stacks)" ]; then
  echo "deploy: untracked files exist under stacks/; commit or remove them" >&2
  git ls-files --others --exclude-standard -- stacks >&2
  exit 1
fi

commit=$(git rev-parse HEAD)
echo "deploy: $commit -> $host"

# Stage only files tracked at HEAD. /tmp is not a secret destination.
git archive --format=tar HEAD stacks |
  ssh "$host" 'set -e; rm -rf /tmp/chill-stacks; mkdir -p /tmp/chill-stacks; tar -xf - --strip-components=1 -C /tmp/chill-stacks'

ssh "$host" 'set -e
  mountpoint -q /mnt/data
  [ "$(stat -c %d:%i /mnt/data)" = "$(stat -c %d:%i /mnt/pool/takeover-primary/r1/mnt/data)" ]
  mountpoint -q /mnt/pool
  mountpoint -q /mnt/fast
  sudo rsync -a --delete --exclude .env --exclude state/ --exclude docs/config/stirling/ --exclude media/suwayomi-auth-password /tmp/chill-stacks/ /opt/stacks/
  sudo install -d -o 1000 -g 1000 \
    /opt/stacks/apps/state/filebrowser-quantum \
    /opt/stacks/apps/state/filebrowser-upload \
    /opt/stacks/apps/state/filebrowser-family \
    /opt/stacks/comms/state/screego \
    /opt/stacks/media/state \
    /opt/stacks/media/state/gluetun \
    /opt/stacks/media/state/jellyfin-config \
    /opt/stacks/media/state/qbittorrent \
    /opt/stacks/media/state/prowlarr \
    /opt/stacks/media/state/radarr \
    /opt/stacks/media/state/sonarr \
    /opt/stacks/media/state/bazarr \
    /opt/stacks/media/state/jellyseerr \
    /opt/stacks/media/state/navidrome \
    /opt/stacks/media/state/wrtag \
    /opt/stacks/media/state/octo-fiesta \
    /opt/stacks/media/state/slskd \
    /mnt/fast/jellyfin-cache \
    /mnt/fast/scratch \
    /mnt/fast/imports \
    /mnt/data/family \
    /mnt/data/photos \
    /mnt/data/apps/minecraft \
    /mnt/data/apps/paperless \
    /mnt/data/apps/paperless/data \
    /mnt/data/apps/paperless/media \
    /mnt/data/apps/paperless/export \
    /mnt/data/apps/paperless/consume \
    /mnt/data/apps/stirling \
    /mnt/data/apps/stirling/tessdata \
    /mnt/data/apps/stirling/config \
    /mnt/data/apps/stirling/logs \
    /mnt/data/apps/stirling/customFiles \
    /mnt/data/apps/stirling/pipeline \
    /mnt/data/apps/suwayomi \
    /mnt/data/media/music/inbox \
    /mnt/data/media/music/inbox/user \
    /mnt/data/media/music/inbox/slskd/complete \
    /mnt/data/media/music/inbox/slskd/incomplete
  sudo install -d -m 0700 /mnt/fast/dumps
  sudo install -d -m 0755 -o 65534 -g 65534 /opt/stacks/observability/state/prometheus /opt/stacks/observability/state/alertmanager
  sudo install -d -m 0755 -o 472 -g 472 /opt/stacks/observability/state/grafana
  sudo docker network inspect homelab-edge >/dev/null 2>&1 ||
    sudo docker network create --driver bridge --internal homelab-edge
  for s in apps comms docs edge games media observability photos; do
    (cd /opt/stacks/$s && sudo docker compose -p $s up -d --pull missing --remove-orphans)
  done
  sudo /usr/local/bin/homelab-firewall-neko'

printf '%s\n' "$commit" |
  ssh "$host" 'sudo install -m 0644 /dev/stdin /opt/stacks/.deployed-commit'
echo "deploy: complete"
