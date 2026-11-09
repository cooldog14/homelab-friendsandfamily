# Case study: the restore drill, not just the backup

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
- `sqlite3 .backup` for each SQLite database (documents library, notifications,
  host monitoring). `.backup` uses SQLite's online backup API, which takes a
  consistent copy while the application keeps running.

Dumps are written to a fresh path and moved into place only on success, so a
failed dump never replaces a good one. A dump failure does not fail the whole
backup: the rest of the data is still worth capturing, and the failure is sent
to the notification channel and left in the journal.

### The drill

`make restore-test` runs against the offsite repository, not the local one, so
it also proves the remote copy is reachable and complete. It restores a curated
set to a temporary directory — never over live data — and then asserts:

- Both PostgreSQL dumps are non-empty and contain a real `pg_dump` header.
- Every SQLite dump is non-empty and `PRAGMA integrity_check` returns `ok`.
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

Measured on 2026-11-09 against the offsite repository:

```
end-to-end: 15 s
objects:    18 files/directories
size:       56.5 MiB
result:     restore-test ok
```

Fifteen seconds to a validated set is fast enough that the drill runs quarterly
without a maintenance window, and fast enough to run by hand after any change to
the backup script or the retention policy.

## Limits

- **RPO is 24 hours.** The job runs nightly. Up to a day of new documents,
  photos and messages can be lost; that is accepted for this platform.
- **There is no high availability.** A host failure means restoring to
  replacement hardware, not failing over. The 15-second figure is the restore
  of the curated set, not the time to rebuild a host.
- **One host, one repository chain.** The offsite copy protects against losing
  the house, but both repositories are written by the same job from the same
  host; a bug in the script affects both.
- **The drill restores critical artifacts, not the platform.** The full media
  tree is over 300 GiB and is intentionally out of scope for the drill. A real
  recovery would restore the dumps and configuration first, then let bulk media
  re-download in the background.
- **A passing drill is a sample, not a proof.** It checks a fixed, curated set.
  A path that is in the repository but not in the drill could still be broken.
