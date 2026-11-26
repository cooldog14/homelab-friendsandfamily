# Serving apps from home

Friends and family needed public HTTPS without opening ports on the home
router. The apps stay on a home server. A small cloud server runs Caddy for
HTTPS and reaches the apps over WireGuard. Other public services, such as
voice chat and Minecraft, have explicit port forwards. Private web interfaces
stay on Tailscale.

## What broke

An early deploy copied the new Caddy file but left the old routes running.
Docker Compose had nothing to recreate because the service definition had
not changed. The deploy now restarts private Caddy when its file changes.

After a power cut, the VM and containers came back but network traffic did
not. A packet capture showed the router was still sending replies to an old
MAC address for the VM.

## What gets checked

Scheduled checks cover public and private sites, forwarded TCP ports, and
expiring certificates. Public checks also run from outside the lab. An
expected sign-in response counts as reachable. It does not prove sign-in
or the rest of the app works.

[Power cut incident](../history/2026-11-02-to-09-operations.md#incident-2026-11-02-power-cut-then-chill-egress-dead-from-stale-router-arp)
