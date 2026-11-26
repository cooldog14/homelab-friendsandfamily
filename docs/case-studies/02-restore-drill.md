# Testing an offsite backup

A successful backup does not show that the files can be restored. The lab
keeps local and offsite copies. It makes database dumps or consistent
database copies before taking snapshots.

## The drill

On November 17, 2026, the application VM restored a sample from offsite into
a separate directory. It checked database dumps, the Suwayomi archive,
host and VPS configuration, and a sample photo path.

The drill restored 40 files and directories totaling 1.63 GiB, including
21 SQLite and three Filebrowser database copies. It took 6 minutes 45 seconds
on the first run and 1 minute 22 seconds on the repeat.

## What it proved

The sampled files could be retrieved and passed the checks. The drill did
not start the recovered apps, test access without the original VM, or
measure the time to rebuild the lab.

[Drill results](../history/2026-11-17-to-19-operations.md#maintenance-2026-11-17-isolation-edge-recovery-and-monitoring-hardening)

[Independent recovery procedure](../../RUNBOOK.md#recovery-expectations)
