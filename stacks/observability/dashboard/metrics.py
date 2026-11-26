"""Pure Prometheus rendering of cached dashboard observations; no I/O.

render(integrations, containers, now) accepts two Store.snapshot() dictionaries:
  {"data": ..., "error": str | None, "updated_timestamp_seconds": epoch | None}.
Integrations data is keyed by app. Entries have configured/error, status_payload,
health_checked_at (attempt completion epoch); Arr also has health_payload and
queue_payload={records: [...], totalRecords: int}, queue_success (bool), and
queue_checked_at. Queue records need unique integer/string id and optional
trackedDownloadState. Containers data has by_key["media/<app>" or "edge/caddy"]
with state and health. Only Caddy requires an explicit Docker healthy state;
other apps need running and no unhealthy/starting health state, plus valid API
responses. Both stores and each check must be <=300s old. Store errors invalidate
retained data immediately. Timestamp samples describe observations, never scrape
time; an unobserved check is 0. Failed/stale queues omit all item samples.

Metric contract: app_healthy/check_timestamp_seconds cover all APPS;
arr_queue_check_success/check_timestamp_seconds cover ARR_APPS;
arr_queue_import_blocked{app,queue_id}=1 only for importBlocked/importPending;
arr_health_issues{app} counts warning/error entries on valid fresh health checks.
All names have the homelab_ prefix. No user/library metadata is rendered.
"""

from __future__ import annotations

import math
from typing import Any

APPS = ("jellyseerr", "radarr", "sonarr", "bazarr", "navidrome", "caddy")
ARR_APPS = ("radarr", "sonarr")
MAX_AGE_SECONDS = 300


def _epoch(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return 0.0
    return float(value)


def _fresh(stamp: float, now: float) -> bool:
    return stamp > 0 and 0 <= now - stamp <= MAX_AGE_SECONDS


def _store_fresh(store: dict, now: float) -> bool:
    return not store.get("error") and _fresh(_epoch(store.get("updated_timestamp_seconds")), now)


def _label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _version(payload: Any, key: str = "version") -> bool:
    return isinstance(payload, dict) and isinstance(payload.get(key), str) and bool(payload[key].strip())


def _status_ok(app: str, entry: dict) -> bool:
    payload = entry.get("status_payload")
    if app == "navidrome":
        return payload is True
    if app == "bazarr":
        return _version(payload.get("data") if isinstance(payload, dict) else None, "bazarr_version")
    if app in ARR_APPS:
        return _version(payload) and _health(entry) is not None
    return _version(payload)


def _health(entry: dict) -> list[dict] | None:
    rows = entry.get("health_payload")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("type"), str) for row in rows
    ):
        return None
    return rows


def _queue_records(entry: dict) -> list[dict] | None:
    payload = entry.get("queue_payload")
    if not isinstance(payload, dict):
        return None
    rows, total = payload.get("records"), payload.get("totalRecords")
    if not isinstance(rows, list) or type(total) is not int or len(rows) != total:
        return None
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        identifier = row.get("id")
        if (
            isinstance(identifier, bool) or not isinstance(identifier, (int, str))
            or not str(identifier) or str(identifier) in seen
            or ("trackedDownloadState" in row and not isinstance(row["trackedDownloadState"], str))
        ):
            return None
        seen.add(str(identifier))
    return rows


def render(integrations: dict, containers: dict, now: float) -> str:
    """Render cached snapshots at an explicit time; safe to call on every scrape."""
    entries = integrations.get("data") or {}
    by_key = (containers.get("data") or {}).get("by_key") or {}
    integration_fresh = _store_fresh(integrations, now)
    docker_fresh = _store_fresh(containers, now)
    docker_stamp = _epoch(containers.get("updated_timestamp_seconds"))
    samples: list[str] = []

    def emit(name: str, value: float | int, app: str, queue_id: Any = None) -> None:
        labels = f'app="{_label(app)}"'
        if queue_id is not None:
            labels += f',queue_id="{_label(queue_id)}"'
        samples.append(f"homelab_{name}{{{labels}}} {value:g}")

    for app in APPS:
        entry = entries.get(app) or {}
        key = "edge/caddy" if app == "caddy" else f"media/{app}"
        container = by_key.get(key) or {}
        container_ok = (
            docker_fresh and container.get("state") == "running"
            and (container.get("health") == "healthy" if app == "caddy"
                 else container.get("health") in (None, "healthy"))
        )
        stamp = docker_stamp if app == "caddy" else min(
            docker_stamp, _epoch(entry.get("health_checked_at"))
        )
        healthy = bool(container_ok and _fresh(stamp, now))
        if app != "caddy":
            healthy = bool(
                healthy and integration_fresh and entry.get("configured") is True
                and not entry.get("error") and _status_ok(app, entry)
            )
        emit("app_healthy", int(healthy), app)
        emit("app_check_timestamp_seconds", stamp, app)

        if app not in ARR_APPS:
            continue
        queue_stamp = _epoch(entry.get("queue_checked_at"))
        records = _queue_records(entry)
        queue_ok = bool(
            container_ok and integration_fresh and entry.get("configured") is True
            and entry.get("queue_success") is True and _fresh(queue_stamp, now)
            and records is not None
        )
        emit("arr_queue_check_success", int(queue_ok), app)
        emit("arr_queue_check_timestamp_seconds", queue_stamp, app)
        if queue_ok:
            for row in records:
                if str(row.get("trackedDownloadState", "")).lower() in ("importblocked", "importpending"):
                    emit("arr_queue_import_blocked", 1, app, row["id"])
        health = _health(entry)
        if (
            container_ok and integration_fresh and entry.get("configured") is True
            and _fresh(_epoch(entry.get("health_checked_at")), now)
            and _version(entry.get("status_payload")) and health is not None
        ):
            emit("arr_health_issues", sum(row["type"].lower() in ("warning", "error") for row in health), app)
    return "\n".join(samples) + "\n"
