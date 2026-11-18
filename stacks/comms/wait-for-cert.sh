#!/bin/sh
# The upstream -acme image starts Mumble immediately; on a fresh volume the
# first certificate does not exist yet and Mumble exhausts supervisord's
# startretries before lego finishes. Wait for the deploy hook, then start.
set -eu

while [ ! -s /data/acme/mumble.crt ] || [ ! -s /data/acme/mumble.key ]; do
	sleep 2
done

exec /entrypoint.sh /usr/bin/mumble-server
