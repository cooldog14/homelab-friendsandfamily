#!/usr/bin/env python3
"""Sample restic repository size and freshness into the node_exporter textfile.

Never prints a credential: the repository environment is sourced through
`/bin/sh` and every secret-looking value is masked before anything reaches
stdout/stderr. A per-repository failure is reported as `success 0` metrics and
still exits non-zero so `OnFailure=notify@` delivers a Gotify alert.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TEXTFILE_DIR = Path(os.environ.get("TEXTFILE_DIR", "/var/lib/node_exporter/textfile"))
OUTPUT = "homelab-backup-stats.prom"
ENV_CANDIDATES = ("/etc/homelab.env", "/etc/restic/malice.env")
LOCAL_MOUNT = Path("/mnt/backup")
LOCAL_REPO = Path("/mnt/backup/restic")
SECRET_HINTS = ("KEY", "TOKEN", "PASSWORD", "SECRET", "PASS")


class RepositoryError(RuntimeError):
    pass


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def load_environment(path: Path) -> dict[str, str]:
    """Source the env file through sh so quoting rules match the other units."""
    result = subprocess.run(
        ["/bin/sh", "-c", 'set -a; . "$1"; env -0', "sh", str(path)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RepositoryError(f"cannot source {path}")
    values: dict[str, str] = {}
    for chunk in result.stdout.split(b"\0"):
        if not chunk:
            continue
        key, _, value = chunk.partition(b"=")
        values[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return values


def secrets_of(values: dict[str, str]) -> list[str]:
    picked = [
        value
        for key, value in values.items()
        if len(value) >= 6 and any(hint in key.upper() for hint in SECRET_HINTS)
    ]
    return sorted(picked, key=len, reverse=True)


def restic(env: dict[str, str], secrets: list[str], *args: str) -> str:
    try:
        result = subprocess.run(
            ["restic", *args], env=env, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise RepositoryError(f"cannot run restic: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RepositoryError(
            redact(detail[-1] if detail else f"restic {args[0]} failed", secrets)
        )
    return result.stdout


def iso_to_epoch(value: str | None) -> float:
    if not value:
        return 0.0
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def repository_metrics(
    name: str,
    env: dict[str, str],
    host: str,
    now: float,
) -> tuple[list[str], bool]:
    """Return metric lines for one repository and whether it succeeded."""
    secrets = secrets_of(env)
    try:
        snapshots = json.loads(restic(env, secrets, "snapshots", "--json"))
        stats = json.loads(restic(env, secrets, "stats", "--json", "--mode", "raw-data"))
        if not isinstance(snapshots, list):
            raise RepositoryError("unexpected restic snapshots payload")
        if not isinstance(stats, dict):
            raise RepositoryError("unexpected restic stats payload")
    except (RepositoryError, json.JSONDecodeError) as exc:
        print(f"homelab-backup-stats: {name}: {exc}", file=sys.stderr)
        return (
            [
                f'homelab_backup_stats_success{{host="{host}",repository="{name}"}} 0',
                f'homelab_backup_stats_timestamp_seconds{{host="{host}",repository="{name}"}} {int(now)}',
            ],
            False,
        )

    repo_size = stats.get("total_size")
    if not isinstance(repo_size, (int, float)):
        repo_size = stats.get("total_bytes_processed")
    lines = [
        f'homelab_backup_stats_success{{host="{host}",repository="{name}"}} 1',
        f'homelab_backup_stats_timestamp_seconds{{host="{host}",repository="{name}"}} {int(now)}',
        f'homelab_backup_snapshot_count{{host="{host}",repository="{name}"}} {len(snapshots)}',
    ]
    if isinstance(repo_size, (int, float)):
        lines.append(
            f'homelab_backup_repo_size_bytes{{host="{host}",repository="{name}"}} {int(repo_size)}'
        )
    latest = None
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        if latest is None or iso_to_epoch(snapshot.get("time")) > iso_to_epoch(latest.get("time")):
            latest = snapshot
    if latest is not None:
        stamp = iso_to_epoch(latest.get("time"))
        if stamp > 0:
            lines.append(
                f'homelab_backup_latest_snapshot_timestamp_seconds'
                f'{{host="{host}",repository="{name}"}} {int(stamp)}'
            )
        summary = latest.get("summary") or {}
        processed = summary.get("total_bytes_processed")
        if isinstance(processed, (int, float)):
            lines.append(
                f'homelab_backup_latest_snapshot_bytes'
                f'{{host="{host}",repository="{name}"}} {int(processed)}'
            )
    return lines, True


def main() -> int:
    source = next((Path(path) for path in ENV_CANDIDATES if Path(path).is_file()), None)
    if source is None:
        print("homelab-backup-stats: no env file found", file=sys.stderr)
        return 1
    try:
        values = load_environment(source)
    except RepositoryError as exc:
        print(f"homelab-backup-stats: {exc}", file=sys.stderr)
        return 1

    host = values.get("HOST_LABEL") or os.uname().nodename
    now = datetime.now(timezone.utc).timestamp()
    base = {
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": values.get("HOME") or "/root",
        "XDG_CACHE_HOME": values.get("XDG_CACHE_HOME") or "/root/.cache",
        "RESTIC_CACHE_DIR": values.get("RESTIC_CACHE_DIR") or "/var/cache/restic",
    }
    for key in (
        "RESTIC_REPOSITORY",
        "RESTIC_PASSWORD",
        "RESTIC_PASSWORD_FILE",
        "RESTIC_PASSWORD_COMMAND",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_ENDPOINT",
    ):
        if values.get(key):
            base[key] = values[key]

    failed = False
    body: list[str] = []
    cloud_env = dict(base)
    cloud_env.setdefault("RESTIC_REPOSITORY", values.get("RESTIC_REPOSITORY", ""))
    lines, ok = repository_metrics("cloud", cloud_env, host, now)
    body.extend(lines)
    if not ok:
        failed = True

    if LOCAL_MOUNT.is_mount() and LOCAL_REPO.is_dir():
        local_env = dict(base)
        local_env["RESTIC_REPOSITORY"] = str(LOCAL_REPO)
        lines, ok = repository_metrics("local", local_env, host, now)
        body.extend(lines)
        if not ok:
            failed = True

    text = "\n".join(
        [
            "# HELP homelab_backup_stats_success Le dernier echantillonnage du depot a reussi",
            "# TYPE homelab_backup_stats_success gauge",
            "# HELP homelab_backup_repo_size_bytes Taille des donnees du depot",
            "# TYPE homelab_backup_repo_size_bytes gauge",
            "# HELP homelab_backup_snapshot_count Nombre de snapshots",
            "# TYPE homelab_backup_snapshot_count gauge",
            "# HELP homelab_backup_latest_snapshot_timestamp_seconds Date du snapshot le plus recent",
            "# TYPE homelab_backup_latest_snapshot_timestamp_seconds gauge",
            "# HELP homelab_backup_latest_snapshot_bytes Donnees traitees par le snapshot le plus recent",
            "# TYPE homelab_backup_latest_snapshot_bytes gauge",
            "# HELP homelab_backup_stats_timestamp_seconds Date de l'echantillonnage",
            "# TYPE homelab_backup_stats_timestamp_seconds gauge",
            *body,
            "",
        ]
    )

    TEXTFILE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TEXTFILE_DIR / f"{OUTPUT}.{os.getpid()}"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, TEXTFILE_DIR / OUTPUT)
    finally:
        if tmp.exists():
            tmp.unlink()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
