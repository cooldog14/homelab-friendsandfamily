# comms

Mumble, Neko, Screego on chill-01.

## mumble

The official image regenerates `/data/mumble_server_config.ini` on every
start from the `MUMBLE_CONFIG_*` variables in `docker-compose.yml`. Never
edit that generated file; change the compose environment instead. The
SQLite database in `./state/mumble` holds channels, ACLs, registered users
and bans.

Hardening defaults in the compose file: 25 users, 8 per channel, 128 kbit/s
per client, 1k text / 64k image messages, no recording, no UDP ping
responses, no version disclosure, and `channelname=.+` so emoji-prefixed
channel names are accepted. Mumble has no channel icons; the emoji is part
of the channel name.

The root channel is the server name shown to clients (`MALICE`). The `all`
group is limited to traverse/enter/speak/whisper/text/listen; it cannot
register, create channels, move or mute users, kick, ban, or write ACLs.
SuperUser bypasses ACLs. Do not add anyone to the `admin` group.

Secrets live only in `/opt/stacks/comms/.env` (root-only, never deployed
from git):

```sh
sudo grep -E '^(MUMBLE_SUPERUSER_PASSWORD|MUMBLE_ICE_SECRET_WRITE)=' \
  /opt/stacks/comms/.env
```

The Mumble SuperUser password is that first value. Ice listens on
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
