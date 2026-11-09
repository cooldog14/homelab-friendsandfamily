# agents.md — homelab infrastructure reference for automation

Read `AGENTS.md` first. Its hard rules apply to every session:
git is source of truth, never print/commit secrets, Tailscale is the
only people entry point, WireGuard is VPS<->chill-01 only, never touch
`/etc/wireguard` contents, never flush VPS nftables, no `0.0.0.0`
binds unless documented. Transient work lives in `TODO.md`,
incidents in `RUNBOOK.md`.

## topology

- `malice`: Proxmox VE 9.2.25 (kernel 7.0.14-26) bare metal, the only
  hypervisor. PVE firewall disabled. No ZFS pools.
- VM 101 `chill-01` (running): 4 vCPU, 16G RAM, 80G `local-lvm` disk
  (`scsi0`, `virtio-scsi-single`, `iothread=1`),
  `hostpci0 00:02.0` Intel iGPU passthrough (UHD 630, vfio-pci).
  Runs all Docker Compose apps (~45 containers). IP LAN `192.168.1.200`,
  WG `10.44.0.2`, Tailscale `100.92.173.71`.
- VM 103 `debian-01` (running, 16G+64G `scsi` disks). VM 102 `alpine-01` +
  LXC 200 `friend` destroyed 2026-09-30 (final vzdumps
  `vzdump-qemu-102-2026_09_30*`, `vzdump-lxc-200-2026_09_30*` on
  `/mnt/vault/dump`, keep-last 8). LXC 204 `hermes-01` destroyed 2026-09-30
  (persona/config saved to `/mnt/primary/users/francis/hermes`, final
  `vzdump-lxc-204-2026_09_30*` 2.4G retained).
- VPS `debian-13` (`194.58.47.21:4522`): public edge, Caddy TLS +
  nftables NAT. No apps. SSH is key-only (`PermitRootLogin
  prohibit-password`, `PasswordAuthentication no` via
  `/etc/ssh/sshd_config.d/00-homelab-hardening.conf`, written by the
  `vps_edge` Ansible role); root still has a console password for the
  provider, but SSH never accepts it.
- Host state is Ansible-managed: `ansible/chill.yml` and
  `ansible/vps.yml` with roles under `ansible/roles/`. `bootstrap.sh`
  and `vps/bootstrap.sh` were deleted; `make host` / `make vps` are the
  only host entry points, and a second run reports `changed=0`.
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
## storage (Proxmox paths stable; virtiofs tags renamed 2026-09-30)
| Host disk | Mount | Shared as | Guest sees | Holds |
|---|---|---|---|---|
| sdd 4TB | `/mnt/bulk` -> `/mnt/pool` (bind) | `pve1-pool` | `/mnt/pool` | movies, tv, downloads + `takeover-primary` (sole primary-data copy, backed up) |
| sdc 2TB | RETIRED (in slot, kernel-offlined) | — | — | former `/mnt/primary`; pull pending disk-swap |
| sdf 466G SSD | `/mnt/fast` | `pve1-fast` | `/mnt/fast` | jellyfin-cache, imports, scratch, DB dumps (disposable) |
| sdb 466G | `/mnt/vault` | `pve1-vault` (was `pve1-archive`) | `/mnt/vault` | vzdump target + pre-migration keeps (backup-only) |
| sda 1TB | `/mnt/backup` | `pve1-backup` | `/mnt/backup` | local restic repo (backup-only) |
| sde SSD | Proxmox + `local-lvm` | — | VM disks | Data% ~36%, VFree ~16G |

chill-01 root disk holds Docker images and `/opt/stacks/*/state`;
keep bulk files off it.
Notes: sdc unmounted 2026-11-02 (NFS export dropped, debian-01
automount stopped, fstab commented, `virtiofs0` deleted from 101,
device offlined); takeover `media/music` (301G) ro-bound over
`/mnt/pool/media/music` (fstab-persisted; `/mnt/bulk/media/music` follows). `weekly-vault` vzdump job: all
guests, snapshot, zstd, Sun 03:30, keep-last 8, writes
`/mnt/vault/dump`.
## app stacks (all on chill-01, `/opt/stacks`, `make deploy` ships git)

- `apps`: Filebrowser Quantum (`:8085`), family (`:8086`,
  public `files.malice.biz`), upload drop (`:8087`,
  public `upload.malice.biz`).
- `photos`: Immich (`:2283`, public + private); uploads land on mirror.
- `docs`: Paperless (`:8092`), Stirling (`:8091`, private only),
  Kavita (`:8094`), Gotenberg, Tika.
- `comms`: Mumble (`:64738/tcp+udp`), Neko (`:8097` + `:52000`),
  Screego (`:5050`, `network_mode: host` — documented exception).
- `media`: Jellyfin (`:8096` WG + LAN bind for TVs),
  qBittorrent/Prowlarr/FlareSolverr/slskd behind gluetun (egress via
  VPS `wg0`, inbound `6881`/`50300` DNAT to `10.30.0.4`),
  Radarr/Sonarr/Bazarr/Jellyseerr, Navidrome (`:4533` WG),
  Feishin/player (`:9180`), Octo-fiesta (`:5274`), Suwayomi (`:4567`,
  public `mg.malice.biz` + private), wrtag (`:7373`). Jellyfin
  `/cache` -> `/mnt/fast/jellyfin-cache`;
  `/pool/movies|tv` ro. GPU `renderD128` present, QSV->VAAPI flip open.
  slskd (`:5030`) and wrtag (`:7373`) web UIs run with authentication
  **disabled on purpose**: they are reachable only through the private
  `*.h.malice.biz` Caddy over Tailscale (`slskd.h` / `wrtag.h`), never
  public and never from the VPS tunnel. The tailnet is the auth boundary.
- `observability`: Gotify (`:8070`, private only),
  prometheus (published only on `127.0.0.1:9091` — Cockpit owns
  `*:9090`), alertmanager, alertmanager-gotify-bridge, node-exporter,
  cadvisor (privileged — documented exception), blackbox-exporter,
  grafana. Grafana is private-only via `grafana.h.malice.biz` ->
  `10.44.0.2:3000`. Roughly 43 containers in total on the host.
- Host admin: Cockpit (`cockpit.h.malice.biz` / `:9090`, includes web
  terminal) is Tailscale/private Caddy only; no public route and blocked
  from the VPS WireGuard tunnel.
- `edge`: private Caddy (`*.h.malice.biz`, DNS-01 wildcard, Tailscale
  bind). Exact-host matchers; never duplicate a public name. Caddy reads
  its config at start, so a route edit needs `make edge-reload` — a
  deploy of an unchanged compose file is a no-op.

## public edge (VPS, git-owned `vps/sites/*.caddy`)

- `chill.caddy`: photos, files, paperless, kavita, neko, screego.
- `media.caddy`: jellyfin, requests, player, fiesta, upload, nvdr, mg.
  All backends `reverse_proxy 10.44.0.2:<port>`.
- nftables NAT: Mumble `64738`, Neko `52000`, Screego `3478` +
  `52100-52200`, and Minecraft `25565` are forwarded to `10.44.0.2`.
  CrowdSec blacklist active.
- If public-check goes red, compare git-owned `vps/sites/*.caddy`
  against VPS live config before changing apps.

## backups + checks

- Nightly `homelab-backup` (restic offsite + local
  `/mnt/backup/restic`): `/opt`, `/mnt/fast/dumps`, `/mnt/data`,
  `/etc`, `/root/.ssh`. Excludes downloads, movies, TV, and raw music
  staging. Dumps fresh for immich/paperless/gotify/kavita.
- `homelab-backup-watchdog` (48h), `homelab-public-check`, Gotify, and
  Prometheus are the alert path. Prometheus rules (host down, target
  down, public endpoint down, TLS expiring, disk above 85% for 5
  minutes, stale/missing backup metric, stale WireGuard handshake,
  container restart loop) route through Alertmanager and the
  `alertmanager-gotify-bridge` into Gotify. Prometheus keeps 15 days
  of metrics. The public check runs every 15 minutes;
  `notify@.service` logs delivery failures to the journal instead of
  failing silently when `ALERT_URL` is unset.
  Weekly Docker prune keeps images of stopped containers (`prune -f`,
  no `-a`). Verify the live timers after host deploys.

- `malice-restic-backup` (git-owned `host/malice-restic-backup*`,
  nightly 04:45 → Hetzner S3, retention + `restic check`) covers the
  hypervisor (`/etc`, `/etc/pve`, `/root`, `/usr/local/sbin`).
  `OnFailure=notify@` live and tested (tailnet Gotify POST 200);
  `/etc/homelab.env` on malice uses the `gotify.h` URL (public
  `gotify.malice.biz` has no VPS route). No PVE notification target yet.

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
