# comms

Mumble, Neko, Screego on chill-01.

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
