#!/bin/sh
# Queue one reviewed music directory for import through wrtagweb.
set -eu

usage() {
	printf 'usage: %s <directory>\n' "${0##*/}" >&2
	exit 2
}

[ "$#" -eq 1 ] || usage
case "$1" in
	-h | --help) usage ;;
esac

path=$(readlink -f "$1")
case "$path" in
	/mnt/data/media/downloads/* | /mnt/data/media/music/inbox/*) ;;
	*)
		printf 'refusing path outside the music review/inbox trees: %s\n' "$path" >&2
		exit 2
		;;
esac

[ -d "$path" ] || {
	printf 'not a directory: %s\n' "$path" >&2
	exit 2
}

# Read the live key without assuming /opt/stacks/media/.env is readable by
# the invoking user. Fall back to the file when run as root.
key=$(docker inspect media-wrtag-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
	sed -n 's/^WRTAG_WEB_API_KEY=//p' | head -n1 || true)
if [ -z "$key" ]; then
	key=$(sed -n 's/^WRTAG_WEB_API_KEY=//p' /opt/stacks/media/.env 2>/dev/null |
		tr -d '"' | head -n1 || true)
fi
[ -n "$key" ] || {
	printf 'WRTAG_WEB_API_KEY not found (need docker access or readable media .env)\n' >&2
	exit 1
}

curl -fsS --max-time 30 -u ":$key" \
	--data-urlencode "path=$path" \
	https://wrtag.h.malice.biz/op/move
printf 'queued: %s\n' "$path"
