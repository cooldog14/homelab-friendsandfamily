# homelab

A friends & family platform: one application VM and one edge VPS, managed in
git, on one Proxmox hypervisor.

[![ci](https://github.com/cooldog14/homelab-friendsandfamily/actions/workflows/ci.yml/badge.svg)](https://github.com/cooldog14/homelab-friendsandfamily/actions/workflows/ci.yml)

The platform serves photos, documents, media, chat and games to a small group of
people. The application VM hosts 8 Docker Compose stacks; a small Debian VPS is
the only host with a public IP and reaches the application VM over WireGuard.

Playbooks, Compose files, Caddy routes, firewall/NAT rules and an import-only
definition of the application VM live here. Secrets and application data do not.
CrowdSec setup and the Caddy package source are not yet fully codified.

![High-level homelab architecture: internet, VPS edge, WireGuard backend, Proxmox host, service categories, shared storage, backups and Tailscale admin](docs/diagram/out/homelab.png)

The public diagram is intentionally high-level: addresses, ports, hostnames,
service inventories and known gaps are omitted. Render instructions are in
[`docs/diagram`](docs/diagram).

## Numbers

| Metric | Value |
|---|---|
| Compose stacks | 8 |
| Restore point objective | 24 h |
| Backup retention | 3 snapshots per repository |
| Full-platform recovery time | Not measured |
| Managed machines | 1 application VM, 1 edge VPS |

The 2026-11-17 `make restore-test` drill restored and validated 40 paths
(1.63 GiB), including 21 SQLite dumps, three Bolt snapshots, the Suwayomi
archive and the configuration set. A cold run took 6m45s from the offsite
repository; a warm run took 1m22s. This is sampled artifact recovery, **not** an
RTO for rebuilding the platform.

## What this demonstrates

- **A public edge for a host that has no public IP.** TLS terminates on the VPS;
  the home address never appears in public DNS. Internet-originated connections
  reach the application VM only through VPS proxying or explicit port forwarding.
- **Different tunnels for backend and admin access.** WireGuard carries public
  edge traffic and the P2P exit; Tailscale is the primary human admin path.
  Private admin services are no longer published on the WireGuard address.
- **Sampled restores, not just backups.** A drill restores every database dump
  and the Suwayomi archive, validates dump integrity, and fails on corruption.
  It does not rebuild or restore the full platform.
- **Incident handling with written post-mortems.** Outages end with a dated
  runbook entry that records the symptom, the diagnosis, the repair and the
  prevention.
- **Observable, reproducible core services.** Prometheus and Alertmanager cover
  the application VM, the hypervisor and the public edge. The VPS sends a
  five-minute external heartbeat only while public checks pass, and a
  GitHub-hosted probe checks the same public edge from outside the network every
  ten minutes. Ansible manages host state; OpenTofu plans the imported
  application VM without applying changes.

## Deep dives

- [A public edge for a host that has no public IP](docs/case-studies/01-public-edge.md)
  — three-layer design, the reload trap, and the ARP blackhole.
- [The restore drill](docs/case-studies/02-restore-drill.md)
  — what restic covers, why databases are dumped first, and what the drill
  actually asserts.
- [The observability blind spot](docs/case-studies/03-observability-blind-spot.md)
  — seven days of silence, the firewall rule behind it, and the alert rules
  that came after.

## Operations

This is a best-effort personal platform, not a highly available service. The
managed platform has one hypervisor, one application VM and one VPS; each is a
single point of failure, and maintenance windows are announced rather than
avoided.

Install the Ansible collections once per workstation first, then use the Make
targets:

```sh
ansible-galaxy collection install -r ansible/requirements.yml
```

| Command | What it does |
|---|---|
| `make check` | Validates compose files, both Caddy configs, the public/private host list, shell scripts, and the observability rules. This is what CI runs. |
| `make host` | Applies `ansible/chill.yml` to the application VM (idempotent; a second run reports `changed=0`). |
| `make vps` | Applies `ansible/vps.yml` to the edge VPS: Caddy sites, firewall policy, NAT and WireGuard. |
| `make hypervisor` | Applies `ansible/malice.yml`: tailnet node exporter and host backup/check timers. |
| `make deploy` | Validates, archives the committed `stacks/` tree, deploys it, re-applies container isolation, and records `.deployed-commit`. |
| `make edge-reload` | Restarts the private Caddy after a route edit; `docker compose up -d` is a no-op when the compose file did not change. |
| `make restore-test` | Restores every database dump plus configuration and asserts integrity. |
| `make tofu-check` | Offline OpenTofu format and validation checks (no credentials needed). |
| `make tofu-plan` | Read-only plan of the application VM against the hypervisor. |
| `make ansible-check` | Syntax-checks all playbooks. |

## Security model

- The public edge accepts **key-only SSH**; password authentication and root
  password login are disabled.
- **Tailscale is the primary admin path.** VPS public-key SSH and application-VM
  LAN SSH are separate admin paths. WireGuard is not a human admin path.
- **Secrets are excluded from git.** Environment files and keys live on hosts
  with restrictive permissions; CI runs Gitleaks over full history.
- **OpenTofu is plan-only by workflow.** Credentials are stored outside the
  repository.
- **WireGuard has separate backend and P2P uses.** `chill0` links the VPS to the
  application VM; `wg0` provides P2P egress through the VPS. VPS forwarding is
  restricted to explicit DNAT flows and the P2P return path.
- **Isolation is boot-persistent.** UFW, nftables and `DOCKER-USER` rules are
  restored after Docker starts and re-applied after every deploy. Private admin
  services communicate with Caddy over a dedicated internal Docker network.

## Stack

Debian, Proxmox VE, Docker Compose, Caddy, WireGuard, Tailscale, restic,
systemd, Ansible, OpenTofu, Prometheus, Grafana, Alertmanager.
