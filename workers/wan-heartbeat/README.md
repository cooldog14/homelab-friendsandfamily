# WAN heartbeat Worker

Runs outside the homelab on a five-minute Cloudflare cron. It probes the 13
public vhosts plus `health.malice.biz`, and pings the external Healthchecks
check only when all answer. On failure it sends the check's `/fail` endpoint.
The Worker has no public route (`workers_dev = false`); the `workers.dev`
subdomain only satisfies Cloudflare's cron requirement.

`health.malice.biz` is a status bit, not an application: it returns 200 with
`{"ok": ...}` reflecting the local alert pipeline (`homelab-pipeline-check`).
The Worker reads that body, so a dead Gotify/Alertmanager/bridge/Prometheus
marks the check down even though all real public vhosts still answer. Ordinary
vhosts are still status-only probes.

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
(log) all 14 public targets healthy
(log) heartbeat 200 ok
```

A pipeline outage logs `FAIL https://health.malice.biz: alert pipeline
unhealthy` and `heartbeat 200 fail`.

If the public vhost list changes, update `DEFAULT_TARGETS` in `src/index.js`
and redeploy. `host/check-probe-targets.py` fails `make check` when the Worker
list, `vps/sites/*.caddy` and Prometheus `blackbox-http` drift apart.
