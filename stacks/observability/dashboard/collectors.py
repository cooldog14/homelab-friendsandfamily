"""Background refresh loops.

One daemon thread per source group writes into a `Store`; the HTTP handler only
reads the last complete object. A failed refresh keeps the previous data and
records the error, so a dead integration degrades one panel instead of the page.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import clients
import parsers
from config import DashboardConfig, Settings

DISK_MOUNTS = ("/", "/mnt/data", "/mnt/pool", "/mnt/fast", "/mnt/vault", "/mnt/backup")
NETWORK_DEVICE = "eth0"
LOG_CAPACITY = 500
LOG_TAIL = 30
TITLE_TTL_SECONDS = 6 * 3600
# Only unhealthy/stopped containers are inspected: the detail answers "why is
# it down", and 43 extra API calls per 10 s would be pointless noise.
MAX_INSPECT = 40

_HEALTH_RE = re.compile(r"\((healthy|unhealthy|starting)\)")


def iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _cpu_query(job: str) -> str:
    return (
        "100 * (1 - avg(rate("
        f'node_cpu_seconds_total{{job="{job}",mode="idle"}}[2m]'
        ")))"
    )


def _mem_query(job: str) -> str:
    return (
        "100 * (1 - "
        f'node_memory_MemAvailable_bytes{{job="{job}"}}'
        " / "
        f'node_memory_MemTotal_bytes{{job="{job}"}}'
        ")"
    )


def _net_query(direction: str) -> str:
    return (
        f'rate(node_network_{direction}_bytes_total'
        f'{{job="node",device="{NETWORK_DEVICE}"}}[1m])'
    )


_FS_FILTER = 'fstype!~"tmpfs|overlay|squashfs|ramfs|autofs"'
DISK_USED_Q = (
    "max by (mountpoint) (100 * (1 - "
    f'node_filesystem_avail_bytes{{job="node",{_FS_FILTER}}}'
    " / "
    f'node_filesystem_size_bytes{{job="node",{_FS_FILTER}}}'
    "))"
)
DISK_SIZE_Q = (
    f'max by (mountpoint) (node_filesystem_size_bytes{{job="node",{_FS_FILTER}}})'
)
DISK_AVAIL_Q = (
    f'max by (mountpoint) (node_filesystem_avail_bytes{{job="node",{_FS_FILTER}}})'
)

SERIES = {
    "cpu": (_cpu_query("node"), "percent"),
    "mem": (_mem_query("node"), "percent"),
    "net_rx": (_net_query("receive"), "bytes_per_second"),
    "net_tx": (_net_query("transmit"), "bytes_per_second"),
}


class Store:
    """Last complete value for one refresh group, plus its error state."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._lock = threading.Lock()
        self._data: Any = None
        self._error: str | None = None
        self._updated: float | None = None

    def get(self) -> Any:
        with self._lock:
            return self._data

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "data": self._data,
                "updated_at": iso(self._updated),
                "error": self._error,
            }

    def set_ok(self, data: Any) -> None:
        with self._lock:
            self._data = data
            self._error = None
            self._updated = time.time()

    def set_error(self, message: str) -> None:
        with self._lock:
            # Previous data is deliberately kept: a stale panel with an error
            # banner beats an empty panel.
            self._error = message or "refresh failed"


class Refresher(threading.Thread):
    def __init__(self, name: str, store: Store, fetch: Callable[[], Any]) -> None:
        super().__init__(name=f"refresh-{name}", daemon=True)
        self.store = store
        self.fetch = fetch
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.store.set_ok(self.fetch())
            except Exception as exc:  # noqa: BLE001 - one group must never kill the server
                self.store.set_error(str(exc) or exc.__class__.__name__)
                print(f"dashboard: {self.name} refresh failed: {exc}", file=sys.stderr)
            elapsed = time.monotonic() - started
            self._stop.wait(max(1.0, self.store.interval - elapsed))


class LogRing:
    """De-duplicated ring of log events, newest first on read."""

    def __init__(self, capacity: int = LOG_CAPACITY) -> None:
        self.capacity = capacity
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._seen: set[tuple] = set()
        self._sequence = 0

    def add(self, events: list[dict]) -> None:
        with self._lock:
            for event in events:
                key = (event.get("service"), event.get("ts"), event.get("message"))
                if key in self._seen:
                    continue
                self._seen.add(key)
                self._sequence += 1
                stored = dict(event)
                stored["_seq"] = self._sequence
                self._items.append(stored)
            overflow = len(self._items) - self.capacity
            if overflow > 0:
                for event in self._items[:overflow]:
                    self._seen.discard(
                        (event.get("service"), event.get("ts"), event.get("message"))
                    )
                del self._items[:overflow]

    def recent(self, limit: int = 250) -> list[dict]:
        with self._lock:
            ordered = sorted(
                self._items, key=lambda item: (item.get("ts") or "", item["_seq"])
            )
            newest = ordered[-limit:][::-1]
        return [{k: v for k, v in item.items() if k != "_seq"} for item in newest]


class Collectors:
    def __init__(self, settings: Settings, config: DashboardConfig) -> None:
        self.settings = settings
        self.config = config
        self.prometheus = clients.Prometheus(settings.prometheus_url)
        self.docker = clients.Docker(settings.docker_socket)
        self.tailscale = clients.Tailscale(settings.tailscale_socket)
        jellyfin = settings.integration("jellyfin")
        self.jellyfin = clients.Jellyfin(jellyfin.url, jellyfin.key)
        seerr = settings.integration("jellyseerr")
        self.seerr = clients.Seerr(seerr.url, seerr.key)
        prowlarr = settings.integration("prowlarr")
        self.prowlarr = clients.Arr("prowlarr", prowlarr.url, prowlarr.key, api="v1")
        sonarr = settings.integration("sonarr")
        self.sonarr = clients.Arr("sonarr", sonarr.url, sonarr.key)
        radarr = settings.integration("radarr")
        self.radarr = clients.Arr("radarr", radarr.url, radarr.key)

        self.telemetry = Store(10)
        self.infra = Store(15)
        self.containers = Store(10)
        self.routes = Store(60)
        self.integrations = Store(60)
        self.network = Store(30)
        self.inventory = Store(60)
        self.logs = LogRing()

        self._title_cache: dict[tuple, tuple[str, float]] = {}
        self._threads: list[Refresher] = []

    # -- lifecycle -------------------------------------------------------- #

    def start(self) -> None:
        groups = (
            ("telemetry", self.telemetry, self._fetch_telemetry),
            ("infra", self.infra, self._fetch_infra),
            ("docker", self.containers, self._fetch_docker),
            ("routes", self.routes, self._fetch_routes),
            ("integrations", self.integrations, self._fetch_integrations),
            ("tailscale", self.network, self._fetch_tailscale),
            ("inventory", self.inventory, self._fetch_inventory),
        )
        for name, store, fetch in groups:
            thread = Refresher(name, store, fetch)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        for thread in self._threads:
            thread.stop()

    # -- Prometheus ------------------------------------------------------- #

    def _fetch_telemetry(self) -> dict:
        prom = self.prometheus
        nodes = []
        for name, job in (("chill-01", "node"), ("malice", "malice")):
            nodes.append(
                {
                    "name": name,
                    "up": (prom.value(f'up{{job="{job}"}}') or 0.0) == 1.0,
                    "cpu_pct": prom.value(_cpu_query(job)),
                    "mem_pct": prom.value(_mem_query(job)),
                }
            )

        used = {row["metric"].get("mountpoint"): row["value"] for row in prom.query(DISK_USED_Q)}
        size = {row["metric"].get("mountpoint"): row["value"] for row in prom.query(DISK_SIZE_Q)}
        avail = {row["metric"].get("mountpoint"): row["value"] for row in prom.query(DISK_AVAIL_Q)}
        disks = [
            {
                "mountpoint": mount,
                "used_pct": used.get(mount),
                "size_bytes": int(size.get(mount) or 0),
                "avail_bytes": int(avail.get(mount) or 0),
            }
            for mount in DISK_MOUNTS
            if mount in used
        ]

        series: dict[str, dict] = {}
        for key, (expression, unit) in SERIES.items():
            rows = prom.query_range(expression)
            points = rows[0]["points"] if rows else []
            series[key] = {"unit": unit, "points": points}

        return {"nodes": nodes, "disks": disks, "series": series}

    def _fetch_infra(self) -> dict:
        prom = self.prometheus

        def index(expression: str, keys: tuple[str, ...]) -> dict[tuple, float]:
            table: dict[tuple, float] = {}
            for row in prom.query(expression):
                metric = row["metric"]
                table[tuple(metric.get(key) for key in keys)] = row["value"]
            return table

        timer = index("homelab_job_timer_active", ("host", "task"))
        last_run = index("homelab_job_last_run_timestamp_seconds", ("host", "task"))
        next_run = index("homelab_job_next_run_timestamp_seconds", ("host", "task"))
        exit_code = index("homelab_job_last_exit_code", ("host", "task"))
        failed = index("homelab_job_failed", ("host", "task"))
        missed = index("homelab_job_missed", ("host", "task"))

        tasks = sorted(set(timer) | set(last_run) | set(next_run) | set(failed) | set(missed))
        jobs = [
            {
                "host": host,
                "task": task,
                "timer_active": timer.get((host, task)) == 1.0,
                "last_run": last_run.get((host, task)),
                "next_run": next_run.get((host, task)),
                "exit_code": exit_code.get((host, task)),
                "failed": failed.get((host, task)) == 1.0,
                "missed": missed.get((host, task)) == 1.0,
            }
            for host, task in tasks
        ]

        markers = [
            {
                "host": row["metric"].get("host"),
                "source": row["metric"].get("source"),
                "last_success": row["value"],
            }
            for row in prom.query("homelab_backup_last_success_timestamp_seconds")
        ]

        wireguard = [
            {"peer": row["metric"].get("peer"), "handshake": row["value"]}
            for row in prom.query("homelab_wireguard_latest_handshake_seconds")
        ]

        durations = {
            row["metric"].get("instance"): row["value"]
            for row in prom.query('probe_duration_seconds{job=~"blackbox-http|blackbox-tcp"}')
        }
        expiries = {
            row["metric"].get("instance"): row["value"]
            for row in prom.query('probe_ssl_earliest_cert_expiry{job="blackbox-http"}')
        }
        http_probes = [
            {
                "instance": row["metric"].get("instance"),
                "success": row["value"] == 1.0,
                "duration": durations.get(row["metric"].get("instance")),
                "expires_ts": expiries.get(row["metric"].get("instance")),
            }
            for row in prom.query('probe_success{job="blackbox-http"}')
        ]
        tcp_probes = [
            {
                "instance": row["metric"].get("instance"),
                "success": row["value"] == 1.0,
                "duration": durations.get(row["metric"].get("instance")),
            }
            for row in prom.query('probe_success{job="blackbox-tcp"}')
        ]

        repo_keys = ("host", "repository")
        repo_success = index("homelab_backup_stats_success", repo_keys)
        repo_size = index("homelab_backup_repo_size_bytes", repo_keys)
        repo_count = index("homelab_backup_snapshot_count", repo_keys)
        repo_latest = index("homelab_backup_latest_snapshot_timestamp_seconds", repo_keys)
        repo_latest_bytes = index("homelab_backup_latest_snapshot_bytes", repo_keys)
        repo_stamp = index("homelab_backup_stats_timestamp_seconds", repo_keys)
        repos = [
            {
                "host": host,
                "repository": repository,
                "success": repo_success.get((host, repository)) == 1.0,
                "size_bytes": int(repo_size.get((host, repository)) or 0),
                "snapshot_count": (
                    int(repo_count[(host, repository)])
                    if (host, repository) in repo_count
                    else None
                ),
                "latest_snapshot": repo_latest.get((host, repository)),
                "latest_snapshot_bytes": (
                    int(repo_latest_bytes[(host, repository)])
                    if (host, repository) in repo_latest_bytes
                    else None
                ),
                "stats_timestamp": repo_stamp.get((host, repository)),
            }
            for host, repository in sorted(
                set(repo_success) | set(repo_count) | set(repo_latest) | set(repo_stamp)
            )
        ]

        hosts_up = {
            row["metric"].get("job"): row["value"] == 1.0
            for row in prom.query('up{job=~"node|malice"}')
        }

        return {
            "up": hosts_up,
            "jobs": jobs,
            "backup_markers": markers,
            "wireguard": wireguard,
            "http_probes": http_probes,
            "tcp_probes": tcp_probes,
            "repos": repos,
            "prometheus_alerts": parsers.normalize_prometheus_alerts(prom.alerts()),
        }

    # -- Docker ----------------------------------------------------------- #

    def _fetch_docker(self) -> dict:
        raw = self.docker.containers()
        rows: list[dict] = []
        by_key: dict[str, dict] = {}
        for container in raw:
            labels = container.get("Labels") or {}
            project = labels.get("com.docker.compose.project")
            service = labels.get("com.docker.compose.service")
            status = str(container.get("Status") or "")
            health_match = _HEALTH_RE.search(status)
            row = {
                "id": str(container.get("Id") or "")[:12],
                "name": str(container.get("Names", [""])[0] if container.get("Names") else "").lstrip("/"),
                "stack": project,
                "service": service,
                "state": str(container.get("State") or "unknown"),
                "status": status,
                "health": health_match.group(1) if health_match else None,
                "image": container.get("Image"),
                "image_id": container.get("ImageID"),
                "created": container.get("Created"),
            }
            rows.append(row)
            if project and service:
                by_key[f"{project}/{service}"] = row

        self._inspect_problems(rows)
        self._collect_logs(by_key)
        return {"containers": rows, "by_key": by_key}

    def _inspect_problems(self, rows: list[dict]) -> None:
        inspected = 0
        for row in rows:
            if inspected >= MAX_INSPECT:
                return
            if row["state"] == "running" and row["health"] != "unhealthy":
                continue
            try:
                payload = self.docker.inspect(row["id"])
            except clients.ClientError:
                continue
            row["detail"] = parsers.normalize_container_detail(payload)
            inspected += 1

    def _collect_logs(self, by_key: dict[str, dict]) -> None:
        secrets = self.settings.secrets
        for service_id, meta in self.config.services.items():
            if not meta.get("logs"):
                continue
            container = by_key.get(service_id)
            if not container:
                continue
            try:
                raw = self.docker.logs(container["id"], tail=LOG_TAIL)
            except clients.ClientError:
                continue
            except (OSError, ValueError):
                continue
            events = parsers.parse_docker_logs(
                raw, service_id.partition("/")[2], secrets
            )
            self.logs.add(events)

    # -- Caddy routes ----------------------------------------------------- #

    def _fetch_routes(self) -> dict:
        root = Path(self.settings.stacks_root)
        private_file = root / "edge" / "Caddyfile"
        try:
            private_routes = parsers.parse_private_caddy(
                private_file.read_text(encoding="utf-8")
            )
        except OSError as exc:
            raise clients.ClientError(f"{private_file}: {exc}") from exc

        public_routes: list[dict] = []
        public_error = None
        public_dir = Path(self.settings.public_caddy_dir)
        try:
            for site in sorted(public_dir.glob("*.caddy")):
                public_routes.extend(
                    parsers.parse_public_caddy(site.read_text(encoding="utf-8"))
                )
        except OSError as exc:
            public_error = f"{public_dir}: {exc}"

        for route in private_routes:
            try:
                probe = clients.probe_tls(self.settings.private_edge, route["host"])
            except clients.ClientError as exc:
                probe = {
                    "ok": False,
                    "code": None,
                    "latency_ms": None,
                    "expires_at": None,
                    "expires_ts": None,
                    "error": str(exc),
                }
            route["probe"] = probe

        return {
            "private": private_routes,
            "public": public_routes,
            "public_error": public_error,
        }

    # -- Integrations ----------------------------------------------------- #

    def _fetch_integrations(self) -> dict:
        result: dict[str, dict] = {"jellyfin": {}, "jellyseerr": {}, "prowlarr": {},
                                  "sonarr": {}, "radarr": {}}

        jellyfin = self.jellyfin
        if not jellyfin.configured:
            result["jellyfin"] = {"configured": False, "error": None}
        else:
            entry: dict = {"configured": True, "error": None}
            errors: list[str] = []
            for key, call in (
                ("session_payload", jellyfin.sessions),
                ("info_payload", jellyfin.system_info),
                ("recent_payload", jellyfin.recent),
            ):
                try:
                    entry[key] = call()
                except clients.ClientError as exc:
                    errors.append(f"{key.split('_')[0]}: {exc}")
            if errors:
                entry["error"] = "; ".join(errors)
            result["jellyfin"] = entry

        seerr = self.seerr
        if not seerr.configured:
            result["jellyseerr"] = {"configured": False, "error": None}
        else:
            entry = {"configured": True, "error": None}
            errors = []
            payloads: dict[str, Any] = {}
            for key, call in (
                ("pending_payload", lambda: seerr.requests("pending")),
                ("available_payload", lambda: seerr.requests("available")),
                ("status_payload", seerr.status),
            ):
                try:
                    payloads[key] = call()
                except clients.ClientError as exc:
                    errors.append(f"{key.split('_')[0]}: {exc}")
            entry.update(payloads)
            entry["titles"] = self._seerr_titles(payloads)
            if errors:
                entry["error"] = "; ".join(errors)
            result["jellyseerr"] = entry

        for name, client, kind in (
            ("prowlarr", self.prowlarr, "prowlarr"),
            ("sonarr", self.sonarr, "sonarr"),
            ("radarr", self.radarr, "radarr"),
        ):
            if not client.configured:
                result[name] = {"configured": False, "error": None}
                continue
            entry = {"configured": True, "error": None}
            errors = []
            for key, call in (
                ("health_payload", client.health),
                ("status_payload", client.status),
            ):
                try:
                    entry[key] = call()
                except clients.ClientError as exc:
                    errors.append(f"{key.split('_')[0]}: {exc}")
            if kind in ("sonarr", "radarr"):
                try:
                    entry["queue_payload"] = client.queue(kind)
                except clients.ClientError as exc:
                    errors.append(f"queue: {exc}")
            if errors:
                entry["error"] = "; ".join(errors)
            result[name] = entry

        return result

    def _seerr_titles(self, payloads: dict[str, Any]) -> dict[str, str]:
        """Resolve TMDB ids to titles, cached for six hours."""
        now = time.time()
        titles: dict[str, str] = {}
        for key in ("pending_payload", "available_payload"):
            for row in parsers.normalize_seerr_requests(payloads.get(key)):
                media_type = row["type"]
                tmdb_id = row["tmdb_id"]
                if tmdb_id is None:
                    titles[self._title_key(row)] = f"TMDB #{row['tvdb_id'] or row['id']}"
                    continue
                cache_key = (media_type, int(tmdb_id) if str(tmdb_id).isdigit() else tmdb_id)
                cached = self._title_cache.get(cache_key)
                if cached and now - cached[1] < TITLE_TTL_SECONDS:
                    titles[self._title_key(row)] = cached[0]
                    continue
                try:
                    title = self.seerr.title(media_type, tmdb_id)
                except clients.ClientError:
                    title = None
                if title:
                    self._title_cache[cache_key] = (title, now)
                    titles[self._title_key(row)] = title
                else:
                    titles[self._title_key(row)] = f"TMDB #{tmdb_id}"
        return titles

    @staticmethod
    def _title_key(row: dict) -> str:
        return f"{row['type']}:{row['tmdb_id']}"

    # -- Tailscale -------------------------------------------------------- #

    def _fetch_tailscale(self) -> dict:
        status = self.tailscale.status()
        self_info = status.get("Self") or {}
        peers = []
        for peer in (status.get("Peer") or {}).values():
            if not isinstance(peer, dict):
                continue
            addresses = peer.get("TailscaleIPs") or []
            peers.append(
                {
                    "id": peer.get("ID"),
                    "name": peer.get("HostName") or peer.get("DNSName"),
                    "dns_name": peer.get("DNSName"),
                    "ip": addresses[0] if addresses else None,
                    "os": peer.get("OS"),
                    "online": bool(peer.get("Online")),
                    "direct": bool(peer.get("CurAddr")),
                    "relay": peer.get("Relay"),
                    "last_seen": peer.get("LastSeen"),
                    "tx_bytes": peer.get("TxBytes"),
                    "rx_bytes": peer.get("RxBytes"),
                }
            )
        peers.sort(key=lambda row: (not row["online"], (row["name"] or "").lower()))
        self_addresses = self_info.get("TailscaleIPs") or []
        return {
            "available": True,
            "error": None,
            "self": {
                "name": self_info.get("HostName"),
                "dns_name": self_info.get("DNSName"),
                "ip": self_addresses[0] if self_addresses else None,
                "online": bool(self_info.get("Online")),
                "os": self_info.get("OS"),
            },
            "peers": peers,
        }

    # -- Inventory and deployed git state --------------------------------- #

    def _fetch_inventory(self) -> dict:
        root = Path(self.settings.stacks_root)
        compose: dict[str, dict] = {}
        for path in sorted(root.glob("*/docker-compose.yml")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                compose[path.parent.name] = parsers.parse_compose(text, path.parent.name)
            except Exception as exc:  # noqa: BLE001 - one bad file must not blank the table
                print(f"dashboard: cannot parse {path}: {exc}", file=sys.stderr)
                continue

        meta_path = root / ".deployed-meta"
        commit_path = root / ".deployed-commit"
        git: dict = {
            "commit": None,
            "short": None,
            "branch": None,
            "subject": None,
            "dirty": None,
            "deployed_at": None,
        }
        try:
            meta = parsers.parse_deployed_meta(meta_path.read_text(encoding="utf-8"))
        except OSError:
            meta = {}
        if meta.get("commit"):
            git.update(
                {
                    "commit": meta.get("commit"),
                    "short": meta.get("short") or meta["commit"][:12],
                    "branch": meta.get("branch"),
                    "subject": meta.get("subject"),
                    "dirty": meta.get("dirty") == "1" if meta.get("dirty") else None,
                    "deployed_at": meta.get("deployed_at"),
                }
            )
        else:
            try:
                commit = commit_path.read_text(encoding="utf-8").strip()
            except OSError:
                commit = ""
            if commit:
                git["commit"] = commit
                git["short"] = commit[:12]

        return {"compose": compose, "git": git}
