#!/usr/bin/env python3
"""Queue staged Octo-Fiesta albums through wrtag and publish review counts.

The daily timer runs this after downloads have settled. Successful imports are
moved out of staging by wrtag; directories that need a human stay put and are
counted in the JSON snapshot the home dashboard reads.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STAGING = Path("/mnt/data/media/downloads/octo-fiesta")
BACKLOG = Path("/mnt/data/media/downloads/_to-review")
WRTAG_DB = Path("/opt/stacks/media/state/wrtag/wrtag.db")
STATUS_FILE = Path("/opt/stacks/observability/state/music-review.json")
ENV_FILE = Path("/opt/stacks/media/.env")
WRTAG_MOVE_URL = "https://wrtag.h.malice.biz/op/move"
WRTAG_JOB_URL = "https://wrtag.h.malice.biz"
AUDIO_EXTS = {
    ".aif",
    ".aiff",
    ".ape",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wv",
}
WAIT_SECONDS = 900
POLL_SECONDS = 10


def iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).isoformat()


def has_audio(path: Path) -> bool:
    for _, _, files in os.walk(path):
        if any(Path(name).suffix.lower() in AUDIO_EXTS for name in files):
            return True
    return False


def newest_mtime(path: Path) -> float | None:
    newest = None
    for root, _, files in os.walk(path):
        for name in files:
            try:
                stamp = (Path(root) / name).stat().st_mtime
            except OSError:
                continue
            newest = stamp if newest is None else max(newest, stamp)
    return newest


def album_dirs() -> list[Path]:
    if not STAGING.is_dir():
        return []
    found: list[Path] = []
    for artist in sorted(STAGING.iterdir()):
        if not artist.is_dir() or artist.name.startswith(".") or artist.name == "playlists":
            continue
        albums = [
            child
            for child in sorted(artist.iterdir())
            if child.is_dir() and has_audio(child)
        ]
        if albums:
            found.extend(albums)
        elif has_audio(artist):
            found.append(artist)
    return found


def backlog_count() -> int:
    if not BACKLOG.is_dir():
        return 0
    return sum(1 for entry in BACKLOG.iterdir() if entry.is_dir())


def read_api_key() -> str:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if line.startswith("WRTAG_WEB_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    try:
        output = subprocess.run(
            [
                "docker",
                "inspect",
                "media-wrtag-1",
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("cannot read WRTAG_WEB_API_KEY") from exc
    for line in output.splitlines():
        if line.startswith("WRTAG_WEB_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("WRTAG_WEB_API_KEY not found")


def open_jobs() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{WRTAG_DB}?mode=ro", uri=True, timeout=10)


def job_status(con: sqlite3.Connection, path: Path) -> str | None:
    row = con.execute(
        "select status from jobs where source_path=? order by id desc limit 1",
        (str(path),),
    ).fetchone()
    return row[0] if row else None


def count_statuses(con: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    prefix = f"{STAGING}/%"
    for status, count in con.execute(
        "select status, count(*) from jobs where source_path like ? group by status",
        (prefix,),
    ):
        counts[status or "enqueued"] = int(count)
    return counts


def queue(path: Path, key: str) -> None:
    body = urllib.parse.urlencode({"path": str(path)}).encode("utf-8")
    auth = base64.b64encode(f":{key}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        WRTAG_MOVE_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        raise RuntimeError(f"wrtag HTTP {exc.code}: {detail}") from exc


def wait_for(con: sqlite3.Connection, paths: list[Path], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    pending = list(paths)
    while pending and time.monotonic() < deadline:
        pending = [
            path
            for path in pending
            if path.exists()
            and has_audio(path)
            and job_status(con, path) in ("", "in-progress", None)
        ]
        if pending:
            time.sleep(POLL_SECONDS)


def write_status(payload: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATUS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, STATUS_FILE)


def run(dry_run: bool, no_wait: bool, min_age: int) -> int:
    started = time.time()
    key = "" if dry_run else read_api_key()
    con = open_jobs() if WRTAG_DB.is_file() else None
    if con is None:
        raise RuntimeError(f"wrtag database missing: {WRTAG_DB}")

    staged = album_dirs()
    candidates: list[Path] = []
    too_new: list[Path] = []
    for path in staged:
        if job_status(con, path) in ("", "in-progress", "needs-input", "error"):
            continue
        newest = newest_mtime(path)
        if newest is None:
            continue
        if started - newest < min_age:
            too_new.append(path)
            continue
        candidates.append(path)

    if dry_run:
        print(
            json.dumps(
                {
                    "staged": len(staged),
                    "candidates": [str(path) for path in candidates],
                    "too_new": [str(path) for path in too_new],
                },
                indent=2,
            )
        )
        return 0

    queued: list[Path] = []
    for path in candidates:
        try:
            queue(path, key)
        except RuntimeError as exc:
            print(f"music-import: queue failed: {path}: {exc}", file=sys.stderr)
            continue
        queued.append(path)
        print(f"music-import: queued: {path}")

    if queued and not no_wait:
        wait_for(con, queued, WAIT_SECONDS)

    staged_after = album_dirs()
    staged_set = set(staged_after)
    imported = sum(1 for path in queued if path not in staged_set)
    counts = count_statuses(con)
    processing = counts.get("enqueued", 0) + counts.get("in-progress", 0)
    needs_input = counts.get("needs-input", 0)
    errors = counts.get("error", 0)

    managed: set[str] = set()
    for (source,) in con.execute(
        "select source_path from jobs where source_path like ? and status in ('','in-progress','needs-input','error')",
        (f"{STAGING}/%",),
    ):
        managed.add(source)
    unmanaged = [path for path in staged_after if str(path) not in managed]
    unmanaged = [path for path in unmanaged if path not in too_new]

    needs_review = needs_input + errors + len(unmanaged)
    payload = {
        "schema": 1,
        "generated_at": iso(),
        "generated_ts": time.time(),
        "staging": str(STAGING),
        "staged": len(staged_after),
        "queued": len(queued),
        "imported": imported,
        "processing": processing,
        "needs_input": needs_input,
        "errors": errors,
        "too_new": len(too_new),
        "unmanaged": len(unmanaged),
        "needs_review": needs_review,
        "manual_backlog": backlog_count(),
        "job_url": WRTAG_JOB_URL,
        "error": None,
    }
    write_status(payload)
    print(
        "music-import: "
        f"staged={payload['staged']} queued={payload['queued']} "
        f"imported={payload['imported']} needs_review={payload['needs_review']} "
        f"needs_input={payload['needs_input']} errors={payload['errors']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list candidates only")
    parser.add_argument("--no-wait", action="store_true", help="do not wait for jobs")
    parser.add_argument(
        "--min-age",
        type=int,
        default=3600,
        help="skip directories modified within this many seconds (default: 3600)",
    )
    args = parser.parse_args()
    try:
        return run(args.dry_run, args.no_wait, args.min_age)
    except Exception as exc:  # noqa: BLE001 - journal the failure and publish it
        payload = {
            "schema": 1,
            "generated_at": iso(),
            "generated_ts": time.time(),
            "staging": str(STAGING),
            "staged": 0,
            "queued": 0,
            "imported": 0,
            "processing": 0,
            "needs_input": 0,
            "errors": 0,
            "too_new": 0,
            "unmanaged": 0,
            "needs_review": 0,
            "manual_backlog": backlog_count(),
            "job_url": WRTAG_JOB_URL,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
        try:
            write_status(payload)
        except OSError as write_exc:
            print(f"music-import: cannot write status: {write_exc}", file=sys.stderr)
        print(f"music-import: {payload['error']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
