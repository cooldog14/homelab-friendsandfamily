# agents.md — homelab infrastructure reference for automation

Read `AGENTS.md` first. Its hard rules apply to every session:
git is source of truth, never print/commit secrets, Tailscale is the
only people entry point, WireGuard is VPS<->chill-01 only, never touch
`/etc/wireguard` contents, never flush VPS nftables, no `0.0.0.0`
binds unless documented. Transient work lives in `TODO.md`,
incidents in `RUNBOOK.md`.

## topology

- `malice`: Proxmox VE 9.2.20 (kernel 7.0.14-17) bare metal, the only
  hypervisor. PVE firewall disabled. No ZFS pools.
- VM 101 `chill-01` (running): 4 vCPU, 16G RAM, 80G `local-lvm` disk,
  `hostpci0 00:02.0` Intel iGPU passthrough (UHD 630, vfio-pci).
  Runs all Docker Compose apps (~37 containers). IP LAN `192.168.1.28`,
  WG `10.44.0.2`, Tailscale `100.92.173.71`.
- VM 103 `debian-01` (running, 8G/16G+64G disks). VM 102 `alpine-01` +
  LXC 200 `friend` destroyed 2026-09-30 (final vzdumps
  `vzdump-qemu-102-2026_09_30*`, `vzdump-lxc-200-2026_09_30*` on
  `/mnt/vault/dump`, keep-last 8). LXC 204 `hermes-01` destroyed 2026-09-30
  (persona/config saved to `/mnt/primary/users/francis/hermes`, final
  `vzdump-lxc-204-2026_09_30*` 2.4G retained).
- VPS `debian-13` (`194.58.47.21:4522`): public edge, Caddy TLS +
  nftables NAT. No apps.

## tailnet + links

- Authority: UndauntedGeiger (`taila725ed.ts.net`). `malice .109`,
  `chill-01 .71`. Retire leftovers per `TODO.md` (shared
  `malice.taila725ed.ts.net` `.64` copy, old machines, remaining leaves).
- WireGuard infra only: `chill0` on the VPS and `wg0` on `chill-01`
  (`10.44.0.1` <-> `10.44.0.2`, VPS `:51824`) carries public backends.
  The former `malice` <-> VPS `10.30` fallback is retired; people/admin
  access is Tailscale only.
- LAN `192.168.1.0/24` (`vmbr0`): host `.2`, chill `.28`.
  SSH malice<->chill over LAN currently `No route`; use Tailscale.

## storage (Proxmox paths stable; virtiofs tags renamed 2026-09-30)

| Host disk | Mount | Shared as | Guest sees | Holds |
|---|---|---|---|---|
| sdd 4TB | `/mnt/bulk` -> `/mnt/pool` (bind) | `pve1-pool` | `/mnt/pool` | movies, tv, downloads (re-downloadable, no backup) |
| sdc 2TB | `/mnt/primary` | `pve1-primary` (was `pve1-mirror`) | `/mnt/data` | photos, family, app data, music, books (backed up) |
| sdf 466G SSD | `/mnt/fast` | `pve1-fast` | `/mnt/fast` | jellyfin-cache, imports, scratch, DB dumps (disposable) |
| sdb 466G | `/mnt/vault` | `pve1-vault` (was `pve1-archive`) | `/mnt/vault` | vzdump target + pre-migration keeps (backup-only) |
| sda 1TB | `/mnt/backup` | `pve1-backup` | `/mnt/backup` | local restic repo (backup-only) |
| sde SSD | Proxmox + `local-lvm` | — | VM disks | Data% ~38%, VFree ~16G |

chill-01 root disk holds Docker images and `/opt/stacks/*/state`;
keep bulk files off it.
Notes: `/mnt/primary/media/music` is bind-mounted ro onto
`/mnt/bulk/media/music` (same files counted twice by `du`).
`weekly-vault` vzdump job: all guests, snapshot, zstd, Sun 03:30,
keep-last 8, writes `/mnt/vault/dump`.

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
  qBittorrent/Prowlarr/FlareSolverr/slskd behind gluetun (VPN egress),
  Radarr/Sonarr/Bazarr/Jellyseerr, Navidrome (`:4533` WG),
  Feishin/player (`:9180`), Octo-fiesta (`:5274`), Suwayomi (`:4567`,
  public `mg.malice.biz` + private), wrtag (`:7373`). Jellyfin
  `/cache` -> `/mnt/fast/jellyfin-cache`;
  `/pool/movies|tv` ro. GPU `renderD128` present, QSV->VAAPI flip open.
- `observability`: Gotify (`:8070`, private only), Beszel (`:8090`) +
  beszel-agent (`network_mode: host` — documented
  exception for host/container metrics; UFW still gates inbound).
- Host admin: Cockpit (`cockpit.h.malice.biz` / `:9090`, includes web
  terminal) is Tailscale/private Caddy only; no public route and blocked
  from the VPS WireGuard tunnel.
- `edge`: private Caddy (`*.h.malice.biz`, DNS-01 wildcard, Tailscale
  bind). Exact-host matchers; never duplicate a public name.

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
  staging. Dumps fresh for immich/paperless/gotify/kavita/beszel.
- `homelab-backup-watchdog` (48h), `homelab-public-check`, Gotify, and
  Beszel are the alert path. Weekly Docker prune is in git; verify the
  live timer and Beszel >85% disk alert after host deploys.

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
