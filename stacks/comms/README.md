# comms

Mumble, Neko, Screego on chill-01.

## mumble

The official image regenerates `/data/mumble_server_config.ini` on every
start from the `MUMBLE_CONFIG_*` variables in `docker-compose.yml`. Never
edit that generated file; change the compose environment instead. The
SQLite database in `./state/mumble` holds channels, ACLs, registered users
and bans.

The image is `v1.5.939-acme`: lego obtains and renews a Let's Encrypt
certificate for `malice.biz` and `mumble.malice.biz` over Cloudflare
DNS-01 and installs it under `./state/mumble/acme`; the let's-encrypt
account data lives in `./state/mumble/acme-lego`. Clients may connect to
either name (the DNS wildcard/apex point at the VPS), not the bare IP, or
the certificate name check fails. `supervisord.conf` + `wait-for-cert.sh`
delay Mumble on a fresh volume until the first certificate exists; the
upstream `-acme` image otherwise exhausts its start retries before lego
finishes.

Current channels are `🌐` and `👁️` under root. Mumble has no channel-icon
field; the emoji is the channel name. Hardening defaults: 100 users, no
per-channel cap, 128 kbit/s per client, 1k text / 64k image messages, no
recording, no UDP ping responses, no version disclosure, and
`channelname=.+` so emoji names are accepted.

The client renders the channel-tree root label from the server's
`registerName` value (`Root` when unset), not from the root channel row.
`registerName=MALICE` is set in the compose environment; it does not
publish the server because no `registerPassword`/`registerUrl` are set and
pings are disabled. The root channel row is also named `MALICE` for
consistency. The visible server-level message is the welcome text (MOTD),
currently `BIENVENUE CHEZ LA MALICE !`. The `all` group can
traverse/enter/speak/whisper/text/listen and create **temporary** channels;
it cannot create permanent channels, move or mute users, kick, ban,
register users, or write ACLs. SuperUser bypasses ACLs. Do not add anyone
to the `admin` group.

Secrets live only in `/opt/stacks/comms/.env` (root-only, never deployed
from git). `CF_DNS_API_TOKEN` is the same Cloudflare DNS token used by the
private edge (`CF_API_TOKEN` there); rotate both together.

```sh
sudo grep -E \
  '^(MUMBLE_SUPERUSER_PASSWORD|MUMBLE_ICE_SECRET_WRITE|CF_DNS_API_TOKEN)=' \
  /opt/stacks/comms/.env
```

The Mumble SuperUser password is the first value. Ice listens on
`127.0.0.1:6502` inside the container and is not published; use a one-off
container sharing the Mumble network namespace, or `docker exec`. All Ice
calls need the secret as the `secret` context value (read and write).

## screego users

Screego refuses to start without a users file (`/data/users` in the
container, `./state/screego/users` on the host — state, never git).
`make deploy` creates the dir; the file is yours to write.

Format: one `user:bcrypt_hash` per line (`user:pass`, plaintext, fails
closed — every login attempt just 401s). Generate a line with the
pinned image:

```sh
docker run --rm ghcr.io/screego/server:1.12.6 hash --name USER --pass PASS
```

The image runs as UID 1001 and mounts state read-only: the file must
be readable by 1001 (`chown 1001:1001 users`, `chmod 600 users`).
Changing the file needs a container restart (loaded once at boot).
