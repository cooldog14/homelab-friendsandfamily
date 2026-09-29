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
- VM 103 `debian-01` (running, 8G/16G+64G disks), VM 102 `alpine-01`
  (stopped), LXC 204 `hermes-01` (running), LXC 200 `friend` (stopped
  but `onboot: 1`, 100G rootfs on `fast` SSD). VM 100 + LXC 888
  destroyed 2026-09-21 (last images in `/mnt/vault/backup-old-vm-lxc`).
- VPS `debian-13` (`194.58.47.21:4522`): public edge, Caddy TLS +
  nftables NAT. No apps.

## tailnet + links (UndauntedGeiger replaces frasseberry)

- Authority: UndauntedGeiger (`taila725ed.ts.net`).
  `malice .109`, `chill-01 .71`, `fedora` moved 2026-09-27.
  Retire leftovers per `TODO.md` (shared `malice.taila725ed.ts.net`
  `.64` copy, old machines, remaining leaves).
- WireGuard infra only: `chill0` (`chill-01 10.44.0.2` <-> `VPS:51824`)
  carries all public backends. Legacy `wg0` (`malice 10.30.0.3` <->
  `VPS:51820`) still handshaking, retirement owed.
- LAN `192.168.1.0/24` (`vmbr0`): host `.2`, chill `.28`.
  SSH malice<->chill over LAN currently `No route`; use Tailscale.

## storage (Proxmox paths and virtiofs tags never change)

| Host disk | Mount | Shared as | Guest sees | Holds |
|---|---|---|---|---|
| sdd 4TB | `/mnt/bulk` -> `/mnt/pool` (bind) | `pve1-pool` | `/mnt/pool` | movies, tv, downloads (re-downloadable, no backup) |
| sdc 2TB | `/mnt/primary` | `pve1-mirror` | `/mnt/data` | photos, family, apps data, clean music (backed up) |
| sdf 466G SSD | `/mnt/fast` | `pve1-fast` | `/mnt/fast` | jellyfin-cache, dumps staging, scratch (disposable) |
| sdb 466G | `/mnt/vault` | `pve1-archive` | `/mnt/archive` (rename to `/mnt/vault` owed) | vzdump target + pre-migration keeps (backup-only) |
| sda 1TB | `/mnt/backup` (host-only) | — | not visible in guest | future local restic (`restic init` owed) |
| sde SSD | Proxmox + `local-lvm` | — | VM disks | Data% ~38%, VFree ~16G |

Notes: `/mnt/primary/media/music` is bind-mounted ro onto
`/mnt/bulk/media/music` (same files counted twice by `du`).
`weekly-vault` vzdump job: all guests, snapshot, zstd, Sun 03:30,
keep-last 8, writes `/mnt/vault/dump` (verified 2026-09-27).

## app stacks (all on chill-01, `/opt/stacks`, `make deploy` ships git)

- `apps`: Filebrowser Quantum (`:8085`), family (`:8086`,
  public `files.malice.biz`), upload drop (`:8087`,
  public `upload.malice.biz`).
- `photos`: Immich (`:2283`, public + private). Library empty as of
  2026-09-27 (`/photos` 4K); uploads land on mirror.
- `docs`: Paperless (`:8092`), Stirling (`:8091`), Kavita (`:8094`),
  Gotenberg, Tika.
- `comms`: Mumble (`:64738/tcp+udp`), Neko (`:8097` + `:52000`),
  Screego (`:5050`, `network_mode: host` — documented exception).
- `media`: Jellyfin (`:8096` WG + LAN bind for TVs),
  qBittorrent/Prowlarr/FlareSolverr/slskd behind gluetun (VPN egress),
  Radarr/Sonarr/Bazarr/Jellyseerr, Navidrome (`:4533` WG + localhost),
  Feishin/player (`:9180`), Octo-fiesta (`:5274`), Suwayomi (`:4567`),
  wrtag (`:7373`). Jellyfin `/cache` -> `/mnt/fast/jellyfin-cache`;
  `/pool/movies|tv` ro. GPU `renderD128` present, QSV->VAAPI flip open.
- `observability`: Gotify (`:8070`, private only), Dockge (`:5001`),
  Beszel (`:8090`) + beszel-agent (`network_mode: host` — undocumented,
  see `TODO.md`).
- `edge`: private Caddy (`*.h.malice.biz`, DNS-01 wildcard, Tailscale
  bind) + homepage. Exact-host matchers; never duplicate a public name.
- Stale: `/opt/stacks/privacy` state+volume only, no compose, not in
  `Makefile STACKS` — decide add vs remove.

## public edge (VPS, git-owned `vps/sites/*.caddy`)

- `chill.caddy`: photos, files, paperless, stirling, kavita, neko, screego.
- `media.caddy`: jellyfin, requests, player, fiesta, upload, nvdr.
  All backends `reverse_proxy 10.44.0.2:<port>`.
- nftables NAT: `52000` (Neko), `3478` + `52100-52200` (Screego) both
  forwarded; Mumble `64738` documented but DNAT missing (verify);
  old `10.30` rules removal owed. CrowdSec blacklist active.
- Live incident 2026-09-27: `files.malice.biz` TLS error — VPS
  `chill.caddy` missing the `files` block present in git.
  Fix = `make vps`. `public-check` FAILs `000` since 09-26.

## backups + checks

- Nightly `homelab-backup` (restic offsite, ~509G, 36 snaps as of
  09-27): `/opt` (incl. `/opt/dumps`), `/mnt/data`, `/etc`,
  `/root/.ssh`. Excludes downloads/movies/tv. Dumps fresh for
  immich/paperless/gotify/kavita/beszel/dockge; dead-app dumps
  (bookstack/gonic/navidrome/vaultwarden/joplin/...) still shipped.
  Docs say dumps in `/mnt/fast/dumps`, script uses `/opt/dumps`.
- `homelab-backup-watchdog` (48h) green; `homelab-public-check`
  red (files). Gotify is the alert path; Beszel covers disks
  (>85% alert + weekly prune still owed, images back at 31G).

## access matrix

| Target | Primary (Tailscale) | Fallback |
|---|---|---|
| malice | `ssh malice` | `ssh vps` -> `ssh 10.30.0.3` (WG, only while fallback key kept) |
| chill-01 | `ssh <chill-01-tail-IP>` | `qm guest exec 101 -- <cmd>` via malice (JSON wrapper, no rsync/scp) |
| VPS | never via Tailscale | `ssh vps` (public `:4522`) |
| other guests | via malice (`qm`/`pct`) | Proxmox console |

Prefer direct SSH (deploys need rsync). Keep one proven shell open
while changing tailnets; verify both directions; keep fallback 24h.

## secrets

Never print/commit: `/etc/homelab.env`, stack `.env` files, WireGuard
privkeys, Tailscale auth keys. Pre-migration Proxmox auth backup:
`/root/authorized_keys.bak-2026-09-27` on malice; temporary
`root@debian-13` line in `/etc/pve/priv/authorized_keys` removed per
`TODO.md`.
