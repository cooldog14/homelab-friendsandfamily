# Case study: the restore drill, not just the backup

This is the sampled drill run on `chill-01` on 2026-11-17. For independent
offsite recovery and application-level tests, use the
[recovery runbook](../../RUNBOOK.md#recovery-expectations).

## Problem

A nightly `restic backup` that exits 0 proves the client uploaded something. It
does not prove the repository contains a usable database, a readable
configuration, or anything at all outside the paths that happen to exist today.
Backup jobs fail quietly in known ways: a dump step that wrote a zero-byte file,
a repository that was never initialised because the mount was missing, a
retention policy that pruned the only good snapshot.

The platform is a single application VM with no replica of the live data and no
high availability. The backup is the recovery story. It therefore has to be
tested the same way the public edge is tested — by pulling bytes back out and
checking them, not by trusting the exit status of the job that wrote them.

## Design

### What the repository holds

restic writes to two repositories: an offsite S3 bucket and a local disk on the
hypervisor. Both receive the same snapshot set, so the offsite copy survives the
loss of the house and the local copy survives a slow or unavailable network.

Each repository keeps the **latest three snapshots**, and only snapshots taken
with the five current paths. `host/restic-retention.py` enforces both rules
after every snapshot: it aborts when a snapshot carries a different path set
instead of treating it as old history, so a future path edit cannot quietly
delete the only snapshot of an earlier layout. Removing a legacy layout is a
deliberate `--cleanup-legacy` run, one per repository.

The snapshot covers:

- `/opt` — the compose stacks and their application state.
- `/mnt/fast/dumps` — the database dumps described below.
- `/mnt/data` — user documents and the photo tree (minus re-downloadable bulk).
- `/etc` — host configuration, including the environment file that holds the
  repository and notification credentials.
- `/root/.ssh` — the keys needed to rebuild access.
- A pull of the VPS configuration: public Caddyfile, nftables export and the
  WireGuard identity. The VPS is stateless by design, and losing its keys would
  mean rebuilding the tunnel from scratch.

Two kinds of data are deliberately excluded. Movies and television are bulk
media, re-downloadable and far larger than the rest of the platform combined;
the Prometheus time-series database is a local cache whose value decays within
days. Retaining either would dominate storage cost and restore time for no
recovery benefit. Curated archives — hand-made music intake, review queues —
are kept, because they are irreplaceable even though they are large.

### Why databases are dumped first

Copying a live database file with a file-level backup tool is a coin flip. A
write can land while the file is being read, and the result is a file that opens
but fails integrity checks — or worse, opens and is quietly inconsistent.

So the job dumps before it snapshots:

- `pg_dump` inside the container for the two PostgreSQL applications (photos and
  documents), using the container's own credentials.
- `sqlite3 .backup` for active SQLite state: Filebrowser, Kavita, Mumble,
  Navidrome, Prowlarr, Radarr, Sonarr, Bazarr, Jellyseerr, slskd, wrtag,
  Jellyfin, Gotify and Grafana.
- Paused copies for Filebrowser's bbolt files, and a short Suwayomi pause while
  its H2 store is archived. Minecraft saves are disabled and flushed for the
  snapshot, then re-enabled.

Every database dump is written to a `.new` path, validated, and moved into
place only on success. A failed dump alerts and the rest of the backup still
runs, but the job exits non-zero after both snapshots so `OnFailure` fires and
the success marker is not advanced.

### The drill

`make restore-test` ran from `chill-01` against the offsite repository. It
proved a curated set was retrievable, not that the entire repository could
rebuild the lab. It restored to a separate directory, not over live data:

- Both PostgreSQL dumps are non-empty and contain a real `pg_dump` header.
- Every SQLite dump is non-empty and `PRAGMA integrity_check` returns `ok`.
- All three Filebrowser bbolt copies have valid Bolt headers.
- The Suwayomi archive is non-empty and readable as a tar stream.
- The host environment file and the WireGuard interface file are present and
  structurally valid.
- The VPS configuration pull is present: the public Caddyfile still imports the
  sites directory, and the nftables export still contains the NAT table.
- A representative photo path exists, which is a cheap presence check on the
  large tree.
- The pulled VPS WireGuard peer file is restored when the snapshot contains it.

The temporary directory is removed on exit, whether the run passed or failed.
The target prints `restore-test ok` and exits 0 only when every assertion holds.

## Verification

Measured on 2026-11-17 against the offsite repository:

```
files/dirs: 40 restored of 33 selected paths
size:       1.63 GiB
databases:  21 SQLite + 3 Bolt snapshots
result:     restore-test ok
cold run:   6m45s
warm run:   1m22s
```

## Limits

- **Nightly backup is the target, not a guaranteed RPO.** Confirm the latest
  successful snapshot before estimating how much data could be lost.
- **There is no high availability.** A host failure means restoring to
  replacement hardware, not failing over. The drill duration is the sampled
  artifact restore, not the time to rebuild a host.
- **Shared backup producer.** One application-host job writes both guest
  repositories; its failures can affect both. The hypervisor has a separate backup.
- **The drill restores critical artifacts, not the platform.** The full media
  tree is over 300 GiB and is intentionally out of scope for the drill. A real
  recovery would restore the dumps and configuration first, then let bulk media
  re-download in the background.
- **A passing sample is not application recovery.** It neither tests independent
  access to escrow nor imports the databases into working applications.
