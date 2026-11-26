# Notification hardening — 2026-11-25

Historical evidence, not current instructions. See the [runbook](../../RUNBOOK.md)
for procedures and the [history index](README.md) for other dates.

## maintenance 2026-11-25: harden the whole notification path

Review of every alert producer found three rules that could never reach
Gotify and a delivery path that had already failed silently once (A1).
Changes, all in git (no live edits):

- Bridge contract: `alertmanager-gotify-bridge:2.3.2` builds a message from
  the `summary` + `description` annotations and reads Gotify priority from a
  numeric `priority` annotation, not the `severity` label. `DiskUsageHigh`,
  `WireGuardHandshakeStale` and `ContainerRestartLoop` had no `description`,
  so the bridge returned 400 with no message. All 29 rules now carry
  `summary`/`description`/`priority`, with critical = 8 and warning = 5.
  `host/check-alert-rules.py` enforces this in `make check`; the bridge also
  gets `DISPATCH_ERRORS=true` so a future malformed alert pages instead of
  vanishing.
- Routing: `alertmanager.yml` gains two `inhibit_rules` (failed backup job
  suppresses its stale-marker page; a dead pipeline suppresses its own
  dispatch-noise alerts). New rules consume the bridge metrics that were
  scraped but unused: `AlertmanagerBridgeDroppingAlerts` (received minus
  processed minus failed, since `alerts_invalid` is debug-gated upstream),
  `AlertmanagerBridgeDispatchFailing`, `GotifyUnhealthy`, and
  `AlertPipelineDown` (from the new textfile gauge).
- Direct path: `backup.sh` no longer sends three Gotify messages for one
  failed backup — hard failures are owned by `OnFailure=notify@`, and
  `alert()` is left only for fail-open partial failures. Its curl stderr is
  no longer swallowed. `homelab-firewall-neko` and `homelab-music-import`
  get `OnFailure`; the latter also joins the `metrics.sh` job guard.
- Self-test: `homelab-alert-check` (daily, priority 1) POSTs through
  `ALERT_URL` and fails if delivery breaks, so a dead token is caught by
  `HomelabJobFailed` (a different Gotify token) even though its own POST
  cannot deliver. `homelab-pipeline-check` (every 5 min) verifies
  Prometheus/Alertmanager/bridge/Gotify independently, writes
  `homelab_alert_path_healthy`, and fails once per outage via `notify@`.
  Both are installed by `ansible/roles/chill_units`.
- Drift: `chill_units` and `malice_monitoring` now assert that
  `/etc/homelab.env` is 0600 with an `ALERT_URL` on `gotify.h`, and malice
  asserts the PVE `gotify` endpoint + matcher. `host/check-probe-targets.py`
  makes `vps/sites/*.caddy` the authority for the Worker's
  `DEFAULT_TARGETS` and Prometheus `blackbox-http`, and the edge Caddyfile
  the authority for `blackbox-private`.
- Bugs: `WireGuardHandshakeStale` used `max()` so one fresh peer masked a
  stale one; it is now per-peer. `malice` `homelab-backup-stats` sourced
  `/etc/homelab.env` (chill's repo) because both env files exist there; a
  systemd drop-in now points it at `/etc/restic/malice.env` and skips
  chill's local repo. `smartd.conf` long tests are staggered Thu instead of
  a second Saturday; `-m root` was kept deliberately — it is required to
  enable warnings even with `-M exec`.
- Verify: `host/check-alert-rules.py`, `host/check-probe-targets.py`,
  shellcheck on the two new scripts, `py_compile`, dashboard unit tests and
  `make ansible-check` pass locally. Docker-backed `promtool`/`amtool`/
  `caddy validate` run in CI (no Docker socket on the workstation).
- External dead-man's switch (closes the Gotify single-sink gap): reuse the
  existing `wan-heartbeat` -> Healthchecks check instead of adding a second
  one. `vps/sites/health.caddy` publishes `health.malice.biz` to a read-only
  `pipeline-health` container bound only on `10.44.0.2:8098`; it answers 200
  with `{"ok": ...}` derived from `homelab_alert_path_healthy` (freshness
  guarded, 15 min). The Worker adds it as a 14th target and is the only
  reader of that body, so it stays the single decider for the Healthchecks
  status: a dead Gotify/Alertmanager/bridge/Prometheus sends `/fail` even
  though all 13 real public vhosts still answer. The health endpoint always
  returns 200 so `homelab-public-check` and `blackbox-http` do not page on a
  deliberate "pipeline down" signal. No new secret and no new Healthchecks
  check: the Worker's `HEARTBEAT_URL` is unchanged.
- Deploy order used 2026-11-25: `make vps` (publishes `health.caddy`) →
  `make hypervisor` → `host/deploy.sh chill-01` (brings up `pipeline-health`)
  → `make host` (starts `homelab-pipeline-check.timer`, creating the gauge)
  → start `homelab-pipeline-check`/`homelab-alert-check` once →
  `wrangler deploy`. VPS-first avoids `homelab-public-check` probing a vhost
  that does not exist yet; stack-first means the container is up before host
  timers fire. `host/deploy.sh` was invoked directly because `make deploy`'s
  `check` prerequisite needs a local Docker daemon the workstation lacks; all
  checks were run locally or on the live hosts. The Worker deploy needs the
  Cloudflare token from `~/.config/homelab/cloudflare-workers.env`;
  `HEARTBEAT_URL` is unchanged.
- Verify: `pipeline-health.py` logic (fresh/broken/missing-component/stale/
  missing gauge) and its HTTP 200 + JSON response, Worker `scheduled()` with
  a mocked fetch (healthy -> success ping, broken pipeline -> `/fail`),
  `caddy validate` on the VPS, `promtool check config` on chill-01,
  `check-probe-targets.py` (14 public / 16 private / 4 TCP agree), and
  `docker compose config` all pass. Healthchecks' own notification channel
  is external config, not in git, so it cannot be verified from here.

## maintenance 2026-11-25: live verification after deploy

All commits were deployed on 2026-11-25; no live config was hand-edited.
`make vps` (ok=53 changed=5), `make hypervisor` (ok=22 changed=6),
and `make host` (ok=54 changed=6) reported `failed=0`; `host/deploy.sh` completed successfully.
`wrangler deploy` published version `1f1055b5` with the `*/5 * * * *` cron.

- Observability: 29 Prometheus rules loaded, 2 inhibit rules,
  `DISPATCH_ERRORS=true`, 10 observability containers up with
  `pipeline-health` healthy on `10.44.0.2:8098`.
- Alert path: `homelab_alert_path_healthy` = 1 for prometheus, alertmanager,
  bridge and gotify; `https://health.malice.biz` returns `{"ok": true}` from
  the public internet; `homelab-alert-check` POST returned 200 ("delivery OK");
  `homelab-public-check` exit 0 with 14 HTTP + 4 TCP green; zero firing
  alerts and zero failed units on chill-01, malice and the VPS.
- Probes: `blackbox-http` 14, `blackbox-private` 16, `blackbox-tcp` 4,
  `up{job="gotify-bridge"}` 1, `alertmanager_gotify_bridge_gotify_up` 1.
- External heartbeat: `wrangler tail` captured a scheduled run logging
  `all 14 public targets healthy` and `heartbeat 200 ok`. One transient
  `fiesta.malice.biz` timeout from the workstation did not reproduce (200 on
  three retries, from the VPS and from chill-01).
- Hypervisor: smartd long tests staggered Mon/Tue/Wed/Sat/Thu; the
  `homelab-backup-stats` drop-in is live and a manual run reports 15 snapshots
  on `/backupbackup/malice-host` with no bogus `local` series.
- Blast radius: Caddy config valid, CrowdSec + bouncer + `wg-quick@chill0`
  active, WG handshake 17 s, backup markers fresh, `.deployed-commit` =
  `3a46e12`, local git clean.
- Still open (tracked in `TODO.md`): confirm Healthchecks' own notification
  channel with a real `/fail` + recovery, and re-test one real failure path.
  Healthchecks delivery config is external and was not readable from here.
