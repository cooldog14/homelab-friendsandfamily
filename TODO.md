# TODO

Open work only. Record incidents and drill results via [RUNBOOK.md](RUNBOOK.md).
Completed work and detailed verification: [2026-11-25 snapshot](docs/history/2026-11-25-backlog.md).

## Safety and recovery

- [ ] Finish disk retirement (on-site access required). Stage local restic and
  VM dumps before pulling `sdc` + `sda`; keep `sdb` (`/mnt/vault`). Require a
  byte-verified `/mnt/pool/.diskmove`, rebuilt mounts, readable dumps/restic,
  and green public checks after reboot. `sda` remains mounted; `sdc` is offlined.
- [ ] Refresh malice's EFI boot menu with console access. `7.0.14-29-pve` is
  installed but `7.0.14-26-pve` boots; ESP `sde2` is not mounted at `/boot/efi`.
  Mount it, persist `vfat umask=0077`, run `grub-install` and `update-grub`.
  Verify the intended kernel and guest autostart after reboot.
- [ ] Confirm Healthchecks delivery channel and 5m period / 15m grace;
  prove a real `/fail` notifies and a recovery ping clears it.
- [ ] Exercise a harmless real failure and confirm both `notify@` → Gotify
  and `HomelabJobFailed` → bridge → Gotify. A synthetic POST is insufficient.
- [ ] Repeat the restore drill quarterly; record scope, timing and result.

## Instrumentation and hygiene

- [ ] Add app-level health instrumentation where Docker has none: Caddy admin,
  Jellyseerr, Navidrome, Radarr/Sonarr/Bazarr.
- [ ] Alert on Sonarr/Radarr `importBlocked`/`importPending` items older than
  24h and executable payloads under `/mnt/data/downloads`.
- [ ] Narrow the eight broad `/mnt/data` mounts; add Filebrowser proxy-header handling.
- [ ] Add HSTS/baseline headers, CAA, DNSSEC and null MX; document IPv4-only public service.
- [ ] Remove chill-01's old build cache and DB `.bak` files only after checking
  the latest restic snapshot.
- [ ] Decide whether to disable Tailscale key expiry for chill-01 and malice
  before March 2027. Keep existing offline admin devices registered unless
  explicitly revoked.
- [ ] Resolve remaining documentation drift: `vps/README.md` missing
  `vps/firewall.nft`, edge bootstrap comments, photos/games “mirror disk” comments.

## Accepted risks and decisions

These are policy/hardware constraints, not unfinished deployments.

- No UPS/NUT; revisit power-loss mitigation when hardware is available.
- VPS retains two unrestricted root authorized keys and private-key copies;
  secret rotation/root-key restrictions remain an accepted policy risk.
- Minecraft remains public without a whitelist, with RCON enabled; revisit as
  the player base grows.
- Decide whether to accept or separate P2P egress on the public edge IP:
  an abuse complaint could suspend the whole edge.
- Confirm whether rebuild-from-git plus offsite application data is sufficient,
  or full VM images also need offsite retention.
