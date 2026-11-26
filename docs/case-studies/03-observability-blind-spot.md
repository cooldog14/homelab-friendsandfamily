# When monitoring stopped reporting

After a reboot, Beszel stopped receiving metrics from the home server for
seven days. No alert rules were configured to report the monitoring failure.
The dashboard showed old data, not whether the apps were down.

## Finding the cause

The agent was listening, but a connection test from inside the monitoring
container failed. The firewall allowed traffic on one IPv6 bridge interface.
The container needed to connect over IPv4.

## What changed

The firewall rule was fixed and alerts were added. Prometheus later replaced
Beszel. It checks whether backups are late and whether their metrics are
missing. Those are separate failures.

The local alerts go to Gotify. A separate Cloudflare Worker and Healthchecks
can signal an outage when the local alert path is down. A chart or a successful
request does not prove a notification reached someone.

[Original incident](../history/2026-10-22-to-31-operations.md#incident-2026-10-30-beszel-blind-for-7-days-and-no-alert-rules-at-all)

[Notification drills](../../RUNBOOK.md#notification-drills)
