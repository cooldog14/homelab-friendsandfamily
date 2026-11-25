# agents.md — homelab infrastructure reference for automation

Read `AGENTS.md` first. Its hard rules apply to every session:
git is source of truth, never print/commit secrets, Tailscale is the
only people entry point, WireGuard is VPS<->chill-01 only, never touch
`/etc/wireguard` contents, never flush VPS nftables, no `0.0.0.0`
binds unless documented. Open work lives in `TODO.md`, procedures in
`RUNBOOK.md`, dated incidents and maintenance in `docs/history/`.

## topology

- `malice`: Proxmox VE bare metal, the only hypervisor.
  PVE firewall disabled. No ZFS pools.
- VM 101 `chill-01` (running): 4 vCPU, 16G RAM, 80G `local-lvm` disk
  (`scsi0`, `virtio-scsi-single`, `iothread=1`),
  `hostpci0 00:02.0` Intel iGPU passthrough (UHD 630, vfio-pci).
  Runs all Docker Compose apps. IP LAN `192.168.1.200`,
  WG `10.44.0.2`, Tailscale `100.92.173.71`.
- VM 103 `debian-01`: remote-site hub, 16G+64G `scsi` disks.
  Retired guests and their final backups are recorded in operations history;
  do not treat historical guests as live infrastructure.
- VPS `debian-13` (`194.58.47.21:4522`): public edge, Caddy TLS +
  nftables NAT. No apps. SSH is key-only (`PermitRootLogin
  prohibit-password`, `PasswordAuthentication no` via
  `/etc/ssh/sshd_config.d/00-homelab-hardening.conf`, written by the
  `vps_edge` Ansible role); root still has a console password for the
  provider, but SSH never accepts it.
- Host state is Ansible-managed: `ansible/chill.yml`, `ansible/vps.yml` and
  `ansible/malice.yml` with roles under `ansible/roles/`. `make host`,
  `make vps` and `make hypervisor` are the only host entry points, and a second
  run reports `changed=0`. `make deploy` archives the committed `stacks/` tree,
  re-applies container isolation and records `/opt/stacks/.deployed-commit`.
- OpenTofu (`tofu/`) codifies VM 101 import-only: `prevent_destroy`,
  plan-only policy, never apply. Credentials live outside the repo at
  `~/.config/homelab/tofu.env` (a least-privilege Proxmox API token).
  `make tofu-check` is offline (CI); `make tofu-plan` needs the token.

## tailnet + links

- Authority: UndauntedGeiger (`tail61489d.ts.net`). `malice .109`,
  `chill-01 .71`, workstation `fedora .28`. The tailnet is intentional and
  clean: every registered device is a live admin device the owner keeps
  (offline phones/laptops stay registered on purpose, they are not
  leftovers). Do not "audit and revoke" devices without asking.
- WireGuard backends: `chill0` on the VPS <-> `wg0` on `chill-01`
  (`10.44.0.1` <-> `10.44.0.2`, VPS `:51824`) carries public web backends.
- WireGuard P2P exit: VPS `wg0` (`10.30.0.1:51820`) <-> gluetun on
  `chill-01` (`10.30.0.4/32`, its tun0). qBittorrent/slskd/prowlarr/
  flaresolverr egress via the VPS (verified public IP `194.58.47.21`);
  inbound `6881`/`50300` DNAT to `10.30.0.4`. This is the only live peer
  on VPS `wg0`; `10.30.0.5-7` are dead config. The malice peer
  (`10.30.0.3` + `192.168.1.0/24`) was removed 2026-10-30.
- f&f remote site terminates on `debian-01` (VM 103), which runs its own
  hub `10.10.0.0/24` with peers at `109.0.200.185`. It is not on the VPS.
  People/admin access is Tailscale only.
- LAN `192.168.1.0/24` (`vmbr0`): host `.2`, chill `.200` (outside the
  Livebox DHCP pool `.10-.150`). Chill SSH works from the workstation over the
  LAN (`ssh -i ~/.ssh/homelab-ansible-bootstrap deploy@192.168.1.200`) or via
  Tailscale; from malice only `qm guest exec` works (the deploy key is not in
  `/root/.ssh` there). A guest stop/start rotates the
  cloud-init host key, so verify the new fingerprint with
  `qm guest exec 101 -- ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
  before updating known_hosts.
## storage
| Host disk | Mount | Shared as | Guest sees | Holds |
|---|---|---|---|---|
| sdd 4TB | `/mnt/bulk` -> `/mnt/pool` (bind) | `pve1-pool` | `/mnt/pool` | movies, tv, downloads + `takeover-primary` (sole primary-data copy, backed up) |
| sdc 2TB | RETIRED (in slot, kernel-offlined) | — | — | former `/mnt/primary`; pull pending disk-swap |
| sdf 466G SSD | `/mnt/fast` | `pve1-fast` | `/mnt/fast` | jellyfin-cache, imports, scratch, DB dumps (disposable) |
| sdb 466G | `/mnt/vault` | `pve1-vault` (was `pve1-archive`) | `/mnt/vault` | vzdump target + pre-migration keeps (backup-only) |
| sda 1TB | `/mnt/backup` | `pve1-backup` | `/mnt/backup` | local restic repo (backup-only) |
| sde SSD | Proxmox + `local-lvm` | — | VM disks | Measure live usage before capacity decisions |

chill-01 root disk holds Docker images and `/opt/stacks/*/state`;
keep bulk files off it.
Notes: sdc unmounted 2026-11-02 (NFS export dropped, debian-01
automount stopped, fstab commented, `virtiofs0` deleted from 101,
device offlined); takeover `media/music` (301G) ro-bound over
`/mnt/pool/media/music` (fstab-persisted; `/mnt/bulk/media/music` follows). `weekly-vault` vzdump job: all
guests, snapshot, zstd, Sun 03:30, keep-last 8, writes
`/mnt/vault/dump`.
## services

Compose definitions in `stacks/*/docker-compose.yml` own the app inventory,
ports and mounts; Caddy files own routes. Do not duplicate those inventories here.
All stacks run on chill-01 under `/opt/stacks`; `make deploy` ships git.

- `apps`, `photos`, `docs`, `comms`, `media`, `games`: user-facing services.
  Screego uses host networking (documented exception).
- Media P2P services share gluetun's VPS egress. Keep
  `FIREWALL_OUTBOUND_SUBNETS=172.16.0.0/12`: Compose bridge subnets can change
  after recreation. Jellyfin binds WG + LAN for TVs, with `/cache` on
  `/mnt/fast/jellyfin-cache` and movies/TV read-only.
- Octo-Fiesta stages in `/mnt/data/media/downloads/octo-fiesta`; review/import
  with `homelab-wrtag-import` or the daily music-import timer.
- slskd (`:5030`) requires authentication; wrtag (`:7373`) deliberately
  does not (`WRTAG_WEB_AUTH=disabled`), while its `/op/` API still needs the
  key. Both are reachable only through the private `*.h.malice.biz` Caddy
  over Tailscale (`slskd.h` / `wrtag.h`), never public and never from the
  VPS tunnel. The tailnet remains the outer auth boundary.
- `observability`: Prometheus is the only alert engine; Grafana owns metrics,
  trends and capacity, while `home.h` owns live state, inventory, routes, logs
  and authenticated app APIs. Blackbox probes public/private HTTP and DNAT TCP.
  Prometheus publishes only on `127.0.0.1:9091` (Cockpit owns `:9090`);
  cAdvisor is privileged (documented exception). Private admin UIs use Caddy's
  internal `homelab-edge` network, not published WireGuard ports.
- Host admin: Cockpit (`cockpit.h.malice.biz` / `:9090`, includes web
  terminal) is Tailscale/private Caddy only; no public route and blocked
  from the VPS WireGuard tunnel.
- `edge`: private Caddy (`*.h.malice.biz`, DNS-01 wildcard, Tailscale
  bind). Exact-host matchers; never duplicate a public name. Caddy reads
  its config at start, so a route edit needs `make edge-reload` — a
  deploy of an unchanged compose file is a no-op.

## public edge

Git-owned `vps/sites/*.caddy` defines public routes to `10.44.0.2:<port>`.
`health.malice.biz` is a read-only status bit on `10.44.0.2:8098`, not an app;
its `homelab_alert_path_healthy` result lets the WAN Worker detect a failed
notification pipeline even when public applications still answer.

- nftables NAT: Mumble `64738`, Neko `52000`, Screego `3478` +
  `52100-52200`, and Minecraft `25565` are forwarded to `10.44.0.2`.
  CrowdSec blacklist active. `vps/firewall.nft` is the effective
  input/forward policy: DNAT-only forwarding plus the P2P return path.
- If public-check goes red, compare git-owned `vps/sites/*.caddy`
  against VPS live config before changing apps.

## backups + checks

- Nightly `homelab-backup` (restic offsite + local
  `/mnt/backup/restic`): `/opt`, `/mnt/fast/dumps`, `/mnt/data`,
  `/etc`, `/root/.ssh`. Excludes downloads, movies, TV, and raw music
  staging. Dumps fresh for Immich, Paperless and active SQLite databases;
  copies Filebrowser bbolt state and a Suwayomi archive consistently.
  Weekly hosted and hypervisor timers read 5% of pack data.
- Retention is **the latest three snapshots per repository**, enforced by
  `/usr/local/bin/homelab-restic-retention` (`host/restic-retention.py`)
  after each snapshot. The helper refuses to prune a snapshot whose path
  set differs from the five current paths, so changing the backup paths
  fails the job instead of silently deleting history; a deliberate
  layout change needs one `--cleanup-legacy` run.
- Prometheus → Alertmanager → bridge → Gotify is the alert pipeline.
  Use numeric `priority` annotations (critical 8 / warning 5); the bridge
  does not read `severity`. Prometheus retains 15 days.
- `homelab-backup-watchdog` alerts after 48h. Public checks run every 15m;
  `notify@` must log failed delivery, never silently accept missing `ALERT_URL`.
- Daily `homelab-alert-check` tests delivery; five-minute
  `homelab-pipeline-check` checks all four pipeline components and triggers
  `notify@` once per outage. Ansible asserts `ALERT_URL` and PVE's Gotify target.
  Verify live timers after host deployments.
- Weekly Docker prune must keep stopped-container images: `prune -f`, never `-a`.

- `malice-restic-backup` (git-owned `host/malice-restic-backup*`,
  nightly 04:45 → Hetzner S3, retention + `restic check`) covers the
  hypervisor (`/etc`, `/etc/pve`, `/root`, `/usr/local/sbin`).
  `OnFailure=notify@` live and tested (tailnet Gotify POST 200);
  `/etc/homelab.env` on malice uses the `gotify.h` URL (public
  `gotify.malice.biz` has no VPS route). PVE notifications target
  `gotify` (matcher `default-matcher` includes `mail-to-root` and `gotify`);
  weekly `malice-restic-check.timer` reads 5% of pack data.
  `prometheus-node-exporter` listens only on the malice Tailscale address
  and is scraped by Prometheus on `chill-01`.
- `workers/wan-heartbeat` is a Cloudflare Worker on a five-minute cron. It
  probes the 13 public vhosts plus `health.malice.biz` from the internet and
  pings the Healthchecks check only when all answer; the check is configured
  for a 5m period / 15m grace. This is the only notification channel that
  survives chill-01 or Gotify being down. The Worker has no public route
  (`workers_dev = false`) and stores the ping URL as a write-only Worker
  secret. Raw TCP DNAT is checked by `homelab-public-check.timer` on
  chill-01.

## access matrix
| Target | Primary (Tailscale) | Fallback |
|---|---|---|
| malice | `ssh malice` | local/Proxmox console |
| chill-01 | `ssh <chill-01-tail-IP>` | `qm guest exec 101 -- <cmd>` via malice (JSON wrapper, no rsync/scp) |
| VPS | never via Tailscale | `ssh vps` (public `:4522`) |
| other guests | via malice (`qm`/`pct`) | Proxmox console |

Prefer direct SSH (deploys need rsync). Keep one proven shell open
while changing tailnets; verify both directions; keep fallback 24h.

## secrets

Never print/commit: `/etc/homelab.env`, stack `.env` files, WireGuard
privkeys, Tailscale auth keys.
