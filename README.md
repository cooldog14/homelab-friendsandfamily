# homelab

A friends & family platform on one Proxmox hypervisor: photos, documents,
media, chat and games. One application VM runs Docker Compose; a Debian VPS
provides the public edge over WireGuard. Tailscale handles private access.

[![ci](https://github.com/cooldog14/homelab-friendsandfamily/actions/workflows/ci.yml/badge.svg)](https://github.com/cooldog14/homelab-friendsandfamily/actions/workflows/ci.yml)

Ansible manages hosts; Compose, Caddy and nftables define services and exposure.
OpenTofu tracks the application VM with a plan-only policy. Secrets and
application data stay outside git.

![High-level homelab architecture: internet, VPS edge, WireGuard backend, Proxmox host, service categories, shared storage, backups and Tailscale admin](docs/diagram/out/homelab.png)

## Selected work

- [A public edge for a host that has no public IP](docs/case-studies/01-public-edge.md)
  — three-layer design, the reload trap, and the ARP blackhole.
- [The restore drill](docs/case-studies/02-restore-drill.md)
  — what restic covers, why databases are dumped first, and what the drill
  actually asserts.
- [The observability blind spot](docs/case-studies/03-observability-blind-spot.md)
  — seven days of silence, the firewall rule behind it, and the alert rules
  that came after.

## Operations

Best effort, not HA: the hypervisor, application VM and VPS are single points
of failure. Nightly restic backups keep three snapshots per repository.
The restore drill validates sampled artifacts, not a full-platform recovery time.

Start with `make ansible-bootstrap` (Python 3.12 required). It creates the
gitignored, pinned Ansible environment; hosts use their own system Python.

| Command | What it does |
|---|---|
| `make check` | Validates compose files, both Caddy configs, the public/private host list, shell scripts, and the observability rules. This is what CI runs. |
| `make host` | Applies `ansible/chill.yml` to the application VM (idempotent; a second run reports `changed=0`). |
| `make vps` | Applies `ansible/vps.yml` to the edge VPS: Caddy sites, firewall policy, NAT and WireGuard. |
| `make hypervisor` | Applies `ansible/malice.yml`: tailnet node exporter and host backup/check timers. |
| `make deploy` | Validates, archives the committed `stacks/` tree, deploys it, re-applies container isolation, and records `.deployed-commit`. |
| `make edge-reload` | Restarts private Caddy after a route edit; an unchanged Compose file will not restart it. |
| `make restore-test` | Restores every database dump plus configuration and asserts integrity. |
| `make tofu-check` | Offline OpenTofu format and validation checks (no credentials needed). |
| `make tofu-plan` | Read-only plan of the application VM against the hypervisor. |
| `make ansible-check` | Syntax-checks all playbooks. |

## Reference

- [Runbook](RUNBOOK.md): troubleshooting and recovery.
- [TODO](TODO.md): open work and accepted risks.
- [Automation reference](AGENTS.md): safety rules, topology, storage and access.
- [VPS contract](vps/README.md) · [OpenTofu policy](tofu/README.md).
- [Operations history](docs/history/2026-09-11-operations.md):
  dated incidents, maintenance and verification.
- [Diagram source and rendering](docs/diagram).

## Credits

- Diagram generator adapted from
  [Goblinmine/homelab-diagram](https://github.com/Goblinmine/homelab-diagram)
  (MIT).
- Diagram fonts: Fira Sans and Fira Code.
