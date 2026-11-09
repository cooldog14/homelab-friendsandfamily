# Case study: observability blind spot, and the alerts that came after

## Impact

A monitoring dashboard showed the only monitored host as `down`. The last metric
was from a reboot, seven days earlier. The documentation claimed a disk-usage
alert existed; the alert table was empty, and the notification settings had an
email address with no mail transfer agent behind it on that machine. If the disk
had filled during those seven days, exactly nobody would have found out from
monitoring.

Two separate failures stacked:

1. **The check was blind** and said nothing, because nothing was watching the
   watcher.
2. **There were no alert rules.** A dashboard is not an alert.

## Diagnosis

The symptom (`status: down`, stale timestamps) narrowed it to the agent/hub link,
not the applications. The hub and the agent run in different network namespaces —
the agent on the host network, the hub on a container bridge — so "the container
is up" proves nothing.

The useful move was to join the hub's namespace and try the connection as the hub
itself:

```sh
nsenter -t "$(pidof hub-process)" -n sh -c 'nc -vz <agent-listen-address> 45876'
```

That failed while the agent's own listen socket was healthy. The firewall was the
suspect, and the live rules showed it: the only allowance for the agent port was
scoped to an **IPv6** interface name of a specific bridge. The IPv4 path was
default-denied.

Why it broke on reboot, and why it was invisible before: Docker assigns bridge
subnets dynamically. A rule pinned to one bridge interface name — or to one
`/16` — survives until that network is recreated, then silently stops matching
anything.

## Repair

- Replace the pinned allowance with the whole Docker address range
  (`172.16.0.0/12`), because the bridge subnet is not stable.
- Add a second, explicit rule for the hub's path to the agent's listen address.
- Never use positional deletes (`ufw delete 3`); delete by rule specification.
- Create the missing alert and wire it to the existing notification service, then
  prove it fires: set a threshold of 1 for a minute, watch the message arrive,
  restore the real threshold.

## Prevention

The repair removed the immediate cause. The prevention is that this class of
failure now pages:

- `HostDown` — the node exporter is unreachable for 2 minutes.
- `TargetDown` — any monitored component has been un-scrappable for 5 minutes.
- `DiskUsageHigh` — any real filesystem above 85% for 10 minutes (the alert the
  documentation had claimed for months).
- `BackupStale` / `BackupMetricMissing` — a backup older than 48 hours, or the
  backup metric disappearing entirely. The second one is deliberate: "the metric
  is absent" and "the metric is old" are different failures, and a missing metric
  used to mean silence.
- `WireGuardHandshakeStale` — the public edge's tunnel has not handshaked in
  10 minutes.
- `ContainerRestartLoop` — a container restarted more than twice in 15 minutes.

The metric pipeline also had to survive its own absence: the backup and tunnel
metrics are exported through the node exporter's textfile collector by a timer,
so a stalled collector shows up as a missing series rather than a stale value.

## What this changed about the operating model

- A dashboard without an alert is decoration. Every panel that matters has a
  corresponding rule.
- Alerts are tested by breaking the thing on purpose: stop the exporter, wait for
  the rule to fire, confirm delivery, restore, confirm resolution.
- The alert path is one hop: rule → alert router → webhook bridge → the
  notification app the owner already reads. No second inbox.
- Post-reboot checks are part of the runbook: after any host reboot, confirm the
  system reports `up` and a metric younger than five minutes, and keep the
  monitoring allowance scoped to the Docker range, never one bridge.
