"""Snapshot assembly and alert derivation.

Everything the browser sees is built here from the last complete refresh of
each group, so the JSON shape is stable even while a source is failing.
"""

from __future__ import annotations

import time
from typing import Any

import parsers
from config import DashboardConfig, Settings
from collectors import Collectors

DAY = 24 * 3600.0
# One host: this dashboard is the chill-01 view. Everything else keeps its own
# Prometheus rules and Gotify alerts.
DASHBOARD_HOST = "chill-01"


def _data(store_snapshot: dict) -> Any:
    return store_snapshot.get("data") if isinstance(store_snapshot, dict) else None


def _age(now: float, stamp: float | None) -> float | None:
    if not stamp:
        return None
    return max(0.0, now - float(stamp))


def _days(now: float, stamp: float | None) -> float | None:
    """Days until `stamp`. Positive while a certificate is still valid."""
    if not stamp:
        return None
    return round((float(stamp) - now) / DAY, 2)


def _service_links(config: DashboardConfig, service_id: str) -> dict:
    links: dict[str, str] = {}
    for key, url in (
        ("private", config.private_url(service_id)),
        ("public", config.public_url(service_id)),
        ("local", config.local_url(service_id)),
    ):
        if url and parsers.safe_url(url):
            links[key] = url
    return links


def _probe_for(
    service_id: str,
    config: DashboardConfig,
    private_routes: dict,
    public_routes: dict,
    http_probes: dict,
    now: float,
) -> dict:
    meta = config.meta(service_id)
    if meta.get("internal"):
        return {"status": "internal", "source": None}

    private_host = meta.get("private_host")
    if private_host:
        host = f"{private_host}.{config.private_domain}"
        route = private_routes.get(host)
        probe = http_probes.get(f"https://{host}")
        if route and probe:
            return {
                "status": "ok" if probe.get("success") else "fail",
                "source": "private",
                "code": probe.get("code"),
                "latency_ms": round((probe.get("duration") or 0) * 1000, 1)
                if probe.get("duration") is not None
                else None,
                "tls_days": _days(now, probe.get("expires_ts")),
            }
        if route:
            return {"status": "unknown", "source": "private"}

    public_host = meta.get("public_host")
    if public_host:
        host = f"{public_host}.{config.public_domain}"
        route = public_routes.get(host)
        probe = http_probes.get(f"https://{host}")
        if route and probe:
            return {
                "status": "ok" if probe.get("success") else "fail",
                "source": "public",
                "code": None,
                "latency_ms": round((probe.get("duration") or 0) * 1000, 1)
                if probe.get("duration") is not None
                else None,
                "tls_days": _days(now, probe.get("expires_ts")),
            }
        if route:
            return {"status": "unknown", "source": "public"}
    return {"status": "unverified", "source": "docker"}


def _build_services(
    config: DashboardConfig,
    inventory: dict,
    containers: dict,
    routes: dict,
    infra: dict,
    now: float,
) -> list[dict]:
    compose = (inventory or {}).get("compose") or {}
    private_routes = {
        route["host"]: route for route in (routes or {}).get("private") or []
    }
    public_routes = {
        route["host"]: route for route in (routes or {}).get("public") or []
    }
    http_probes = {
        probe["instance"]: probe for probe in (infra or {}).get("http_probes") or []
    }
    rows: list[dict] = []
    for stack in sorted(compose):
        for service in sorted((compose[stack] or {}).get("services") or {}):
            service_id = f"{stack}/{service}"
            entry = compose[stack]["services"][service]
            meta = config.meta(service_id)
            container = containers.get(service_id) or {}
            usage = (infra.get("containers") or {}).get(container.get("name") or "")
            state = container.get("state") or "absent"
            uptime = None
            if state == "running" and container.get("created"):
                uptime = max(0, int(now - float(container["created"])))
            version = "local build" if entry.get("build") else entry.get("image_tag")
            rows.append(
                {
                    "id": service_id,
                    "label": config.label(service_id),
                    "stack": stack,
                    "service": service,
                    "image": entry.get("image"),
                    "version": version,
                    "image_id": (container.get("image_id") or "")[:19] or None,
                    "state": state,
                    "health": container.get("health"),
                    "status_text": container.get("status"),
                    "detail": container.get("detail"),
                    "usage": usage,
                    "uptime_seconds": uptime,
                    "links": _service_links(config, service_id),
                    "probe": _probe_for(
                        service_id, config, private_routes, public_routes, http_probes, now
                    ),
                    "internal": bool(meta.get("internal")),
                    "note": meta.get("note"),
                }
            )
    return rows


def _build_hosts(config: DashboardConfig, infra: dict) -> list[dict]:
    up = (infra or {}).get("up") or {}
    http_probes = (infra or {}).get("http_probes") or []
    public_ok = all(probe.get("success") for probe in http_probes) if http_probes else None
    public_latency = (
        round(max((probe.get("duration") or 0) for probe in http_probes) * 1000, 1)
        if http_probes
        else None
    )
    rows: list[dict] = []
    for entry in config.extra_services:
        service_id = str(entry.get("id") or "")
        if not service_id:
            continue
        state = "unknown"
        probe = {"status": "unknown", "source": None}
        job = entry.get("up_job")
        if job:
            value = up.get(job)
            if value is None:
                state = "unknown"
            else:
                state = "running" if value else "exited"
            probe = {
                "status": "ok" if value else ("fail" if value is not None else "unknown"),
                "source": "prometheus",
                "latency_ms": None,
            }
        if entry.get("health") == "public-probes":
            if public_ok is None:
                state = state if state != "unknown" else "unknown"
            else:
                state = "running" if public_ok else "exited"
                probe = {
                    "status": "ok" if public_ok else "fail",
                    "source": "public",
                    "latency_ms": public_latency,
                }
        rows.append(
            {
                "id": service_id,
                "label": entry.get("label") or service_id,
                "category": entry.get("category") or "infra",
                "state": state,
                "probe": probe,
                "links": {"private": entry["link"]}
                if parsers.safe_url(entry.get("link"))
                else {},
                "internal": False,
                "note": None,
            }
        )
    return rows


def _build_groups(
    config: DashboardConfig, services: list[dict], hosts: list[dict]
) -> list[dict]:
    order = config.category_order()
    buckets: dict[str, dict] = {}
    for service in services:
        category = config.category(service["stack"])
        bucket = buckets.setdefault(
            category,
            {
                "id": category,
                "label": (order.get(category) or {}).get("label", category),
                "order": int((order.get(category) or {}).get("order", 1000)),
                "services": [],
                "hosts": [],
            },
        )
        bucket["services"].append(service["id"])
    for host in hosts:
        category = host["category"]
        bucket = buckets.setdefault(
            category,
            {
                "id": category,
                "label": (order.get(category) or {}).get("label", category),
                "order": int((order.get(category) or {}).get("order", 1000)),
                "services": [],
                "hosts": [],
            },
        )
        bucket["hosts"].append(host["id"])
    return sorted(buckets.values(), key=lambda item: (item["order"], item["label"]))


# --------------------------------------------------------------------------- #
# Media, pipeline, backups, network
# --------------------------------------------------------------------------- #


def _media_section(integrations: dict, config: DashboardConfig) -> dict:
    jellyfin = integrations.get("jellyfin") or {}
    if not jellyfin.get("configured"):
        media_jellyfin = {
            "configured": False,
            "error": None,
            "version": None,
            "active": 0,
            "direct": 0,
            "transcode": 0,
            "streams": [],
            "recent": [],
        }
    else:
        sessions = parsers.normalize_jellyfin_sessions(jellyfin.get("session_payload"))
        media_jellyfin = {
            "configured": True,
            "error": jellyfin.get("error"),
            "version": parsers.jellyfin_version(jellyfin.get("info_payload")),
            "active": sessions["active"],
            "direct": sessions["direct"],
            "transcode": sessions["transcode"],
            "streams": sessions["streams"],
            "recent": parsers.normalize_jellyfin_recent(jellyfin.get("recent_payload")),
        }

    seerr = integrations.get("jellyseerr") or {}
    if not seerr.get("configured"):
        requests_section: dict = {
            "configured": False,
            "error": None,
            "version": None,
            "pending": [],
            "available": [],
        }
    else:
        titles = seerr.get("titles") or {}

        def rows(payload: Any) -> list[dict]:
            out = []
            for row in parsers.normalize_seerr_requests(payload):
                key = f"{row['type']}:{row['tmdb_id']}"
                out.append(
                    {
                        "title": titles.get(key),
                        "type": row["type"],
                        "requester": row["requester"],
                        "created": row["created"],
                        "updated": row["updated"],
                    }
                )
            return out

        status_payload = seerr.get("status_payload") or {}
        requests_section = {
            "configured": True,
            "error": seerr.get("error"),
            "version": status_payload.get("version")
            if isinstance(status_payload, dict)
            else None,
            "pending": rows(seerr.get("pending_payload")),
            "available": rows(seerr.get("available_payload")),
        }
    return {
        "jellyfin": media_jellyfin,
        "requests": requests_section,
        "hrefs": {
            "jellyfin": config.private_url("media/jellyfin"),
            "requests": config.public_url("media/jellyseerr"),
        },
    }


def _pipeline_section(integrations: dict, refresh_error: str | None = None) -> dict:
    def arr_entry(name: str, kind: str | None = None) -> dict:
        entry = integrations.get(name) or {}
        if not entry.get("configured"):
            return {"configured": False, "error": None}
        health = parsers.normalize_arr_health(entry.get("health_payload"))
        result = {
            "configured": True,
            "error": entry.get("error"),
            "version": parsers.arr_version(entry.get("status_payload")),
            "errors": health["errors"],
            "warnings": health["warnings"],
        }
        if refresh_error and not result["error"]:
            result["error"] = refresh_error
        if kind and not refresh_error and entry.get("queue_success") is True:
            queue = parsers.normalize_arr_queue(entry.get("queue_payload"), kind)
            result["queue"] = {
                "total": queue["total"],
                "stalled": queue["stalled"],
            }
        return result

    seerr = integrations.get("jellyseerr") or {}
    return {
        "prowlarr": arr_entry("prowlarr"),
        "sonarr": arr_entry("sonarr", "sonarr"),
        "radarr": arr_entry("radarr", "radarr"),
        "jellyseerr": {
            "configured": bool(seerr.get("configured")),
            "error": seerr.get("error"),
        },
    }


def _backups_section(infra: dict, now: float) -> dict:
    jobs = []
    for job in (infra or {}).get("jobs") or []:
        if job.get("host") != DASHBOARD_HOST:
            continue
        jobs.append(
            {
                "host": job.get("host"),
                "task": job.get("task"),
                "timer_active": job.get("timer_active"),
                "last_run": job.get("last_run"),
                "next_run": job.get("next_run"),
                "exit_code": job.get("exit_code"),
                "failed": job.get("failed"),
                "missed": job.get("missed"),
                "last_run_age": _age(now, job.get("last_run")),
                "next_run_in": (
                    round(job["next_run"] - now, 1) if job.get("next_run") else None
                ),
            }
        )
    markers = []
    for marker in (infra or {}).get("backup_markers") or []:
        if marker.get("host") != DASHBOARD_HOST:
            continue
        markers.append(
            {
                "host": marker.get("host"),
                "source": marker.get("source"),
                "last_success": marker.get("last_success"),
                "age": _age(now, marker.get("last_success")),
            }
        )
    repos = []
    for repo in (infra or {}).get("repos") or []:
        if repo.get("host") != DASHBOARD_HOST:
            continue
        repos.append(
            {
                "host": repo.get("host"),
                "repository": repo.get("repository"),
                "success": repo.get("success"),
                "size_bytes": repo.get("size_bytes"),
                "snapshot_count": repo.get("snapshot_count"),
                "latest_snapshot": repo.get("latest_snapshot"),
                "latest_age": _age(now, repo.get("latest_snapshot")),
                "latest_snapshot_bytes": repo.get("latest_snapshot_bytes"),
                "stats_age": _age(now, repo.get("stats_timestamp")),
            }
        )
    return {"repos": repos, "jobs": jobs, "markers": markers}


def _network_section(
    config: DashboardConfig,
    routes: dict,
    infra: dict,
    tailscale: dict,
    now: float,
) -> dict:
    http_probes = {
        probe["instance"]: probe for probe in (infra or {}).get("http_probes") or []
    }
    private_routes = []
    for route in (routes or {}).get("private") or []:
        host = route.get("host")
        probe = http_probes.get(f"https://{host}")
        private_routes.append(
            {
                "exposure": "private",
                "host": host,
                "upstream": route.get("upstream"),
                "status": "unknown"
                if probe is None
                else ("ok" if probe.get("success") else "fail"),
                "code": (probe or {}).get("code"),
                "latency_ms": round((probe.get("duration") or 0) * 1000, 1)
                if probe and probe.get("duration") is not None
                else None,
                "tls_days": _days(now, (probe or {}).get("expires_ts")),
                "error": None,
            }
        )
    public_routes = []
    for route in (routes or {}).get("public") or []:
        host = route.get("host")
        probe = http_probes.get(f"https://{host}")
        public_routes.append(
            {
                "exposure": "public",
                "host": host,
                "upstream": route.get("upstream"),
                "status": "unknown"
                if probe is None
                else ("ok" if probe.get("success") else "fail"),
                "code": (probe or {}).get("code"),
                "latency_ms": round((probe.get("duration") or 0) * 1000, 1)
                if probe and probe.get("duration") is not None
                else None,
                "tls_days": _days(now, (probe or {}).get("expires_ts")),
                "error": None,
            }
        )

    tcp_labels = {int(row.get("port") or 0): row for row in config.dnat}
    tcp_probes = []
    for probe in (infra or {}).get("tcp_probes") or []:
        instance = str(probe.get("instance") or "")
        port = None
        if ":" in instance:
            port = instance.rsplit(":", 1)[1]
        label = tcp_labels.get(int(port)) if port and port.isdigit() else None
        tcp_probes.append(
            {
                "instance": instance,
                "port": int(port) if port and port.isdigit() else None,
                "label": (label or {}).get("label"),
                "proto": (label or {}).get("proto"),
                "success": probe.get("success"),
                "latency_ms": round((probe.get("duration") or 0) * 1000, 1)
                if probe.get("duration") is not None
                else None,
            }
        )

    wireguard = []
    for peer in (infra or {}).get("wireguard") or []:
        wireguard.append(
            {
                "peer": peer.get("peer"),
                "handshake": peer.get("handshake"),
                "age": _age(now, peer.get("handshake")),
            }
        )

    return {
        "tailscale": tailscale,
        "wireguard": wireguard,
        "routes": private_routes + public_routes,
        "tcp_probes": tcp_probes,
        "public_probe_note": "public probe (hairpin)",
    }


def _inventory_section(inventory: dict, services: list[dict]) -> dict:
    compose = (inventory or {}).get("compose") or {}
    ports: list[dict] = []
    volumes: list[dict] = []
    for stack in sorted(compose):
        for service, entry in sorted(((compose[stack] or {}).get("services") or {}).items()):
            network_mode = str(entry.get("network_mode") or "")
            note = None
            if network_mode.startswith("service:"):
                note = f"shares {network_mode.split(':', 1)[1]} netns"
            elif network_mode == "host":
                note = "host network"
            for port in entry.get("ports") or []:
                ports.append(
                    {
                        "stack": stack,
                        "service": service,
                        "host_ip": port.get("host_ip"),
                        "host_port": port.get("host_port"),
                        "container_port": port.get("container_port"),
                        "proto": port.get("proto"),
                        "note": note,
                    }
                )
            for volume in entry.get("volumes") or []:
                volumes.append(
                    {
                        "stack": stack,
                        "service": service,
                        "source": volume.get("source"),
                        "target": volume.get("target"),
                        "mode": volume.get("mode"),
                        "note": note,
                    }
                )
    ports.sort(key=lambda row: (row["stack"], row["service"], str(row["host_port"] or "")))
    volumes.sort(key=lambda row: (row["stack"], row["service"], str(row["target"] or "")))
    return {
        "stacks": len(compose),
        "services": len(services),
        "ports": ports,
        "volumes": volumes,
    }


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #


def _derive_alerts(
    services: list[dict],
    pipeline: dict,
    media: dict,
    errors: dict,
    music_review: dict | None = None,
    now: float | None = None,
) -> list[dict]:
    """Checks that only this process can make.

    Thresholds belong to Prometheus: one expression, one `for:` window and one
    Gotify path. What remains here is state no metric exports (container
    lifecycle and Docker health), authenticated app reachability, and the
    dashboard's own source reads.
    """
    alerts: list[dict] = []

    def add(severity: str, identifier: str, title: str, detail: str, href: str) -> None:
        alerts.append(
            {
                "id": identifier,
                "severity": severity,
                "title": title,
                "detail": detail,
                "href": href,
            }
        )

    if errors.get("prometheus"):
        add(
            "alert",
            "prometheus-unreachable",
            "Prometheus unreachable",
            errors["prometheus"],
            "#telemetry",
        )
    if errors.get("docker"):
        add(
            "alert",
            "docker-unreachable",
            "Docker socket unreachable",
            errors["docker"],
            "#services",
        )
    if errors.get("routes"):
        add(
            "warn",
            "routes-unreadable",
            "Caddy routes could not be read",
            errors["routes"],
            "#network",
        )
    if errors.get("inventory"):
        add(
            "warn",
            "inventory-unreadable",
            "Compose inventory could not be read",
            errors["inventory"],
            "#config",
        )
    if errors.get("tailscale"):
        add(
            "warn",
            "tailscale-unavailable",
            "Tailscale LocalAPI unavailable",
            errors["tailscale"],
            "#network",
        )

    for service in services:
        if service["state"] in ("exited", "dead", "restarting", "created"):
            add(
                "alert",
                f"container:{service['id']}",
                f"{service['label']} is {service['state']}",
                f"{service['id']} ({service['image'] or 'local build'})",
                "#services",
            )
        elif service["state"] == "absent":
            add(
                "warn",
                f"container-missing:{service['id']}",
                f"{service['label']} has no container",
                f"{service['id']} is declared in Compose but absent from Docker",
                "#services",
            )
        if service["state"] == "paused":
            add(
                "warn",
                f"container:{service['id']}",
                f"{service['label']} is paused",
                f"{service['id']} is paused: it is not serving requests",
                "#services",
            )
        if service.get("health") == "unhealthy":
            add(
                "alert",
                f"health:{service['id']}",
                f"{service['label']} is unhealthy",
                f"{service['id']} healthcheck reports unhealthy",
                "#services",
            )

    for name, label in (
        ("jellyfin", "Jellyfin"),
        ("jellyseerr", "Jellyseerr"),
    ):
        key = "requests" if name == "jellyseerr" else name
        section = media.get(key) or {}
        if section.get("configured") and section.get("error"):
            add(
                "warn",
                f"integration:{name}",
                f"{label} unreachable",
                section["error"],
                "#media",
            )

    for name, label, href in (
        ("prowlarr", "Prowlarr", "#pipeline"),
        ("sonarr", "Sonarr", "#pipeline"),
        ("radarr", "Radarr", "#pipeline"),
    ):
        section = pipeline.get(name) or {}
        if not section.get("configured"):
            continue
        if section.get("error"):
            add(
                "warn",
                f"integration:{name}",
                f"{label} unreachable",
                section["error"],
                href,
            )

    review = music_review or {}
    moment = time.time() if now is None else now
    if not review.get("available"):
        add(
            "warn",
            "music-review-missing",
            "Music review status missing",
            review.get("error")
            or "homelab-music-import has not written a status file yet",
            "#media",
        )
    else:
        if review.get("error"):
            add(
                "warn",
                "music-review-error",
                "Music review pass failed",
                str(review["error"]),
                "#media",
            )
        needs_review = int(review.get("needs_review") or 0)
        if needs_review:
            parts: list[str] = []
            if review.get("needs_input"):
                parts.append(f"{int(review['needs_input'])} need input")
            if review.get("errors"):
                parts.append(f"{int(review['errors'])} error(s)")
            if review.get("unmanaged"):
                parts.append(f"{int(review['unmanaged'])} not queued")
            if review.get("imported"):
                parts.append(f"{int(review['imported'])} imported")
            add(
                "warn",
                "music-review",
                f"{needs_review} {'album needs' if needs_review == 1 else 'albums need'} review",
                ", ".join(parts) or "open wrtag to confirm",
                "#media",
            )
        age = _age(moment, review.get("generated_ts"))
        if age is None:
            add(
                "warn",
                "music-review-stale",
                "Music review status has no timestamp",
                "homelab-music-import status is incomplete",
                "#media",
            )
        elif age > 36 * 3600:
            add(
                "warn",
                "music-review-stale",
                "Music review status is stale",
                f"last pass {int(age // 3600)}h ago",
                "#media",
            )

    severity_order = {"alert": 0, "warn": 1}
    alerts.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["title"]))
    return alerts


def _top_consumers(infra: dict, name_to_service: dict, config: DashboardConfig) -> dict:
    """Five busiest containers by CPU and by resident memory."""

    def rows(key: str, limit: int = 5) -> list[dict]:
        candidates = [
            {
                "name": name,
                "service": name_to_service.get(name),
                "label": config.label(name_to_service[name])
                if name in name_to_service
                else name,
                "cpu_pct": stats.get("cpu_pct"),
                "mem_bytes": stats.get("mem_bytes"),
            }
            for name, stats in (infra.get("containers") or {}).items()
            if isinstance(stats, dict) and stats.get(key) is not None
        ]
        candidates.sort(key=lambda row: row.get(key) or 0, reverse=True)
        return candidates[:limit]

    return {"cpu": rows("cpu_pct"), "mem": rows("mem_bytes")}


def prometheus_alerts_section(infra: dict) -> list[dict]:
    """Firing/pending Prometheus alerts, verbatim.

    Prometheus is the only threshold engine; this page must not hide a rule or
    re-derive one.
    """
    rows: list[dict] = []
    for alert in (infra or {}).get("prometheus_alerts") or []:
        name = alert.get("name")
        state = alert.get("state")
        if state not in ("firing", "pending"):
            continue
        severity = "alert" if state == "firing" and alert.get("severity") == "critical" else "warn"
        rows.append(
            {
                "id": f"prometheus:{name}:{alert.get('host') or ''}",
                "severity": severity,
                "state": state,
                "title": alert.get("summary") or name or "alert",
                "detail": alert.get("description")
                or f"{name} {'firing' if state == 'firing' else 'pending'}",
                "host": alert.get("host"),
                "since": alert.get("since"),
                "source": "prometheus",
            }
        )
    rows.sort(key=lambda row: (0 if row["severity"] == "alert" else 1, row["title"]))
    return rows


def summary_counts(alerts: list[dict], prometheus_alerts: list[dict]) -> dict:
    everything = list(alerts) + list(prometheus_alerts)
    return {
        "alert": sum(1 for row in everything if row.get("severity") == "alert"),
        "warn": sum(1 for row in everything if row.get("severity") == "warn"),
        "total": len(everything),
    }


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #


def build_snapshot(
    collectors: Collectors, config: DashboardConfig, settings: Settings, now: float | None = None
) -> dict:
    moment = time.time() if now is None else now
    telemetry_store = collectors.telemetry.snapshot()
    infra_store = collectors.infra.snapshot()
    docker_store = collectors.containers.snapshot()
    routes_store = collectors.routes.snapshot()
    integrations_store = collectors.integrations.snapshot()
    network_store = collectors.network.snapshot()
    inventory_store = collectors.inventory.snapshot()
    music_review_store = collectors.music_review.snapshot()

    telemetry_data = _data(telemetry_store) or {}
    infra_data = _data(infra_store) or {}
    docker_data = _data(docker_store) or {}
    routes_data = _data(routes_store) or {}
    integrations_data = _data(integrations_store) or {}
    network_data = _data(network_store) or {}
    inventory_data = _data(inventory_store) or {}
    music_review = dict(_data(music_review_store) or {"available": False})
    if music_review_store.get("error") and not music_review.get("error"):
        music_review["error"] = music_review_store["error"]

    telemetry = {
        "nodes": telemetry_data.get("nodes") or [],
        "disks": telemetry_data.get("disks") or [],
        "updated_at": telemetry_store.get("updated_at"),
        "error": telemetry_store.get("error"),
    }

    services = _build_services(
        config, inventory_data, docker_data.get("by_key") or {}, routes_data, infra_data, moment
    )
    hosts = _build_hosts(config, infra_data)
    groups = _build_groups(config, services, hosts)
    media = _media_section(integrations_data, config)
    pipeline = _pipeline_section(integrations_data, integrations_store.get("error"))
    backups = _backups_section(infra_data, moment)
    network = _network_section(config, routes_data, infra_data, network_data, moment)
    inventory = _inventory_section(inventory_data, services)

    errors = {
        "prometheus": telemetry_store.get("error") or infra_store.get("error"),
        "docker": docker_store.get("error"),
        "routes": routes_store.get("error") or routes_data.get("public_error"),
        "inventory": inventory_store.get("error"),
        "tailscale": network_store.get("error"),
    }

    alerts = _derive_alerts(services, pipeline, media, errors, music_review, moment)
    prometheus_alerts = prometheus_alerts_section(infra_data)
    name_to_service = {
        str(row.get("name")): f"{row.get('stack')}/{row.get('service')}"
        for row in (docker_data.get("containers") or [])
        if row.get("name") and row.get("stack") and row.get("service")
    }
    top = _top_consumers(infra_data, name_to_service, config)
    telemetry["top_cpu"] = top["cpu"]
    telemetry["top_mem"] = top["mem"]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(moment)),
        "alerts": alerts,
        "prometheus_alerts": prometheus_alerts,
        "summary": summary_counts(alerts, prometheus_alerts),
        "telemetry": telemetry,
        "groups": groups,
        "services": services,
        "hosts": hosts,
        "media": media,
        "music_review": music_review,
        "pipeline": pipeline,
        "backups": backups,
        "network": network,
        "git": inventory_data.get("git")
        or {
            "commit": None,
            "short": None,
            "branch": None,
            "subject": None,
            "dirty": None,
            "deployed_at": None,
        },
        "links": {"grafana": config.private_url("observability/grafana")},
        "inventory": inventory,
        "logs": collectors.logs.recent(250),
        "errors": {key: value for key, value in errors.items() if value},
    }
