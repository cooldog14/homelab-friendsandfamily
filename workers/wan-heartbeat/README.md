# WAN heartbeat Worker

Runs outside the homelab on a five-minute Cloudflare cron. It probes every
public vhost and pings the external Healthchecks check only when all answer.
On failure it sends the check's `/fail` endpoint. The Worker has no public
route (`workers_dev = false`); the `workers.dev` subdomain only satisfies
Cloudflare's cron requirement.

## Deploy or update

Requires a Cloudflare API token with:

- Account → Workers Scripts → Edit
- Account → Account Settings → Read

Store it outside the repo, for example
`~/.config/homelab/cloudflare-workers.env` (0600):

```sh
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ACCOUNT_ID=...
```

Then:

```sh
set -a; . ~/.config/homelab/cloudflare-workers.env; set +a
cd workers/wan-heartbeat
npx --yes wrangler@4.164.0 deploy
```

The `HEARTBEAT_URL` secret is write-only. Keep the Healthchecks ping URL in the
password manager; to set or rotate it:

```sh
printf %s "$HEARTBEAT_URL" | npx --yes wrangler@4.164.0 secret put HEARTBEAT_URL
```

## Verify

```sh
npx --yes wrangler@4.164.0 tail homelab-wan-heartbeat --format pretty
```

Require a scheduled run with:

```text
(log) all 13 public targets healthy
(log) heartbeat 200 ok
```

If the public vhost list changes, update `DEFAULT_TARGETS` in
`src/index.js` and redeploy.
