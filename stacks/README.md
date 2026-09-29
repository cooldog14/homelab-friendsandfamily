# stacks

Docker Compose stacks for chill-01. `make deploy` syncs this folder to
`/opt/stacks`; live `.env` files and `state/` stay on the host.

See repo-root `AGENTS.md` for the app/storage/access map. Public HTTP routes
live in `vps/sites/*.caddy`; private tailnet routes live in
`stacks/edge/Caddyfile`.
