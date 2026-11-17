#!/usr/bin/env python3
"""Enforce the backup retention contract: latest three snapshots per repository.

The backup path set is a contract, not an accident. A snapshot taken with a
different set belongs to a historical layout whose restore instructions no
longer apply (old stacks roots, /var/lib/docker/volumes, the pre-2026-09 photo
paths). Such snapshots are pruned only under --cleanup-legacy, so a future
path change fails the backup loudly instead of silently eating history.

Runs against whatever RESTIC_REPOSITORY is exported (cloud and local are
separate invocations). Credentials come from the caller's environment and are
never read or printed here.
"""

import argparse
import json
import os
import subprocess
import sys

# The only path set a restorable snapshot may have. Keep in sync with the
# `restic backup` arguments in host/backup.sh.
EXPECTED_PATHS = sorted(["/etc", "/mnt/data", "/mnt/fast/dumps", "/opt", "/root/.ssh"])

KEEP = 3


def die(message):
    print(f"restic-retention: {message}", file=sys.stderr)
    raise SystemExit(1)


def snapshots():
    """Return the repository's snapshots, or die trying."""
    if not os.environ.get("RESTIC_REPOSITORY"):
        die("RESTIC_REPOSITORY is not set")
    try:
        out = subprocess.run(
            ["restic", "snapshots", "--json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError:
        die("restic is not installed")
    except subprocess.CalledProcessError as exc:
        die(f"restic snapshots failed: {(exc.stderr or '').strip()}")
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        die(f"could not parse restic snapshots output: {exc}")
    if not isinstance(parsed, list):
        die("restic snapshots output is not a list")
    return parsed


def paths_of(snapshot):
    return sorted(snapshot.get("paths") or [])


def describe(snapshot):
    return f"{snapshot.get('short_id')} {str(snapshot.get('time'))[:19]}"


def forget(ids, dry_run):
    if not ids:
        return
    if dry_run:
        print("would forget: " + " ".join(ids))
        return
    try:
        subprocess.run(["restic", "forget", "--prune", *ids], check=True)
    except subprocess.CalledProcessError as exc:
        die(f"restic forget --prune {ids} failed with exit {exc.returncode}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleanup-legacy",
        action="store_true",
        help="also prune snapshots whose path set is not the current one",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the snapshot IDs that would be forgotten and exit",
    )
    args = parser.parse_args()

    repo = os.environ["RESTIC_REPOSITORY"]
    found = snapshots()
    legacy = [s for s in found if paths_of(s) != EXPECTED_PATHS]
    current = [s for s in found if paths_of(s) == EXPECTED_PATHS]
    # Missing or unparsable timestamps must not silently reorder retention.
    try:
        current.sort(key=lambda s: s["time"], reverse=True)
    except (KeyError, TypeError):
        die("snapshot without a usable time field")

    print(
        f"{repo}: {len(found)} snapshot(s), {len(current)} current-path, "
        f"{len(legacy)} legacy-path"
    )

    if legacy and not args.cleanup_legacy:
        for snapshot in legacy:
            print(f"  legacy {describe(snapshot)} {paths_of(snapshot)}", file=sys.stderr)
        die(
            f"{len(legacy)} snapshot(s) do not match the expected path set; "
            "rerun with --cleanup-legacy to prune them"
        )

    excess = current[KEEP:]
    if args.dry_run:
        for snapshot in legacy:
            print(f"legacy {describe(snapshot)} {paths_of(snapshot)}")
        for snapshot in excess:
            print(f"excess {describe(snapshot)}")
        forget([s["short_id"] for s in legacy] + [s["short_id"] for s in excess], True)
        return

    forget([s["short_id"] for s in legacy], False)
    forget([s["short_id"] for s in excess], False)

    # Re-read instead of trusting the forget calls: the post-condition is the
    # contract, and a partially applied prune must not pass as success.
    remaining = snapshots()
    wrong = [s for s in remaining if paths_of(s) != EXPECTED_PATHS]
    if wrong:
        die(f"{len(wrong)} snapshot(s) still carry a non-current path set after prune")
    if len(remaining) > KEEP:
        die(f"{len(remaining)} snapshots remain, expected at most {KEEP}")
    for snapshot in sorted(remaining, key=lambda s: s["time"], reverse=True):
        print(f"kept {describe(snapshot)}")
    print(f"{repo}: {len(remaining)} snapshot(s) retained")


if __name__ == "__main__":
    main()
