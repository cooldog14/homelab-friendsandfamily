"""Outbound read-only clients.

Every call is timeout-bounded and raises `ClientError`; the collectors keep the
previous snapshot and surface the error instead of retrying inline. Nothing here
accepts a URL or path from a browser request.
"""

from __future__ import annotations

import http.client
import json
import math
import time
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from parsers import seerr_title

USER_AGENT = "homelab-dashboard/1"


class ClientError(RuntimeError):
    """A source could not be read now."""


def _decode(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8", "replace") or "null")
    except json.JSONDecodeError as exc:
        raise ClientError("invalid JSON from upstream") from exc


def http_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> Any:
    """GET a JSON document. The API key travels in a header, never a query."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(8 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise ClientError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise ClientError(str(getattr(exc, "reason", exc))) from exc
    return _decode(body)


def _finite(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


class Prometheus:
    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _api(self, path: str, params: dict[str, str]) -> Any:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        payload = http_json(url, timeout=self.timeout)
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise ClientError(f"prometheus: {payload.get('error') if isinstance(payload, dict) else 'bad response'}")
        return payload.get("data") or {}

    def query(self, expression: str) -> list[dict]:
        data = self._api("/api/v1/query", {"query": expression})
        rows: list[dict] = []
        for series in data.get("result") or []:
            values = series.get("value") or [None, None]
            value = _finite(values[1] if len(values) > 1 else None)
            if value is None:
                continue
            rows.append(
                {
                    "metric": dict(series.get("metric") or {}),
                    "value": value,
                    "ts": _finite(values[0]),
                }
            )
        return rows

    def value(self, expression: str) -> float | None:
        rows = self.query(expression)
        return rows[0]["value"] if rows else None

    def alerts(self) -> list[dict]:
        """Alertmanager's view of Prometheus rules: firing and pending."""
        data = self._api("/api/v1/alerts", {})
        rows = data.get("alerts")
        if not isinstance(rows, list):
            raise ClientError("prometheus: unexpected alerts payload")
        return [row for row in rows if isinstance(row, dict)]


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 8.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self._socket_path)
        except OSError:
            sock.close()
            raise
        self.sock = sock


class _UnixClient:
    def __init__(self, socket_path: str, host_header: str, timeout: float = 8.0) -> None:
        self.socket_path = socket_path
        self.host_header = host_header
        self.timeout = timeout

    def _call(
        self,
        method: str,
        path: str,
        extra_headers: dict[str, str] | None = None,
        limit: int = 16 * 1024 * 1024,
    ) -> bytes:
        connection = _UnixConnection(self.socket_path, self.timeout)
        try:
            connection.request(
                method,
                path,
                headers={"Host": self.host_header, "User-Agent": USER_AGENT, **(extra_headers or {})},
            )
            response = connection.getresponse()
            body = response.read(limit)
            status = response.status
        except (OSError, http.client.HTTPException) as exc:
            raise ClientError(f"{self.socket_path}: {exc}") from exc
        finally:
            connection.close()
        if status != 200:
            raise ClientError(f"HTTP {status} from {self.socket_path}")
        return body


class Docker(_UnixClient):
    """Docker Engine API over the Unix socket. GET only, by construction."""

    def __init__(self, socket_path: str = "/var/run/docker.sock", timeout: float = 8.0) -> None:
        super().__init__(socket_path, "docker", timeout)

    def _get(self, path: str, limit: int = 16 * 1024 * 1024) -> bytes:
        return self._call("GET", path, {"Accept": "application/json"}, limit)

    def containers(self) -> list[dict]:
        payload = _decode(self._get("/containers/json?all=1"))
        if not isinstance(payload, list):
            raise ClientError("docker: unexpected container list")
        return [row for row in payload if isinstance(row, dict)]

    def logs(self, container_id: str, tail: int = 30) -> bytes:
        quoted = urllib.parse.quote(container_id, safe="")
        return self._get(
            f"/containers/{quoted}/logs"
            f"?stdout=1&stderr=1&timestamps=1&tail={int(tail)}",
            limit=2 * 1024 * 1024,
        )

    def inspect(self, container_id: str) -> dict:
        """One container's state detail. Only used for unhealthy/stopped ones."""
        quoted = urllib.parse.quote(container_id, safe="")
        payload = _decode(self._get(f"/containers/{quoted}/json", limit=1024 * 1024))
        if not isinstance(payload, dict):
            raise ClientError("docker: unexpected inspect payload")
        return payload


class Tailscale(_UnixClient):
    """Tailscale LocalAPI. Status and ping only."""

    def __init__(self, socket_path: str = "/var/run/tailscale/tailscaled.sock", timeout: float = 6.0) -> None:
        super().__init__(socket_path, "local-tailscaled.sock", timeout)

    def status(self) -> dict:
        payload = _decode(self._call("GET", "/localapi/v0/status"))
        if not isinstance(payload, dict):
            raise ClientError("tailscale: unexpected status payload")
        return payload

    def ping(self, ip: str) -> dict:
        query = urllib.parse.urlencode({"ip": ip, "type": "disco"})
        payload = _decode(
            self._call("POST", f"/localapi/v0/ping?{query}", limit=64 * 1024)
        )
        if not isinstance(payload, dict):
            raise ClientError("tailscale: unexpected ping payload")
        return payload


class Jellyfin:
    def __init__(self, url: str, key: str, timeout: float = 8.0) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _get(self, path: str) -> Any:
        return http_json(
            f"{self.url}{path}",
            headers={
                "Authorization": f'MediaBrowser Token="{self.key}"',
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )

    def sessions(self) -> Any:
        return self._get("/Sessions")

    def system_info(self) -> Any:
        return self._get("/System/Info")

    def recent(self, limit: int = 12) -> Any:
        query = urllib.parse.urlencode(
            {
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "IncludeItemTypes": "Movie,Episode",
                "Recursive": "true",
                "Limit": limit,
                "Fields": "DateCreated,SeriesName,ProductionYear",
            }
        )
        return self._get(f"/Items?{query}")


class Seerr:
    def __init__(self, url: str, key: str, timeout: float = 8.0) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _get(self, path: str) -> Any:
        return http_json(
            f"{self.url}{path}",
            headers={"X-Api-Key": self.key, "Accept": "application/json"},
            timeout=self.timeout,
        )

    def requests(self, filter_name: str, take: int = 8) -> Any:
        sort = "added" if filter_name == "pending" else "modified"
        query = urllib.parse.urlencode(
            {
                "take": take,
                "sort": sort,
                "sortDirection": "desc",
                "filter": filter_name,
            }
        )
        return self._get(f"/api/v1/request?{query}")

    def status(self) -> dict:
        payload = self._get("/api/v1/status")
        _require_version(payload, "version", "jellyseerr")
        return payload

    def title(self, media_type: str, tmdb_id: Any) -> str | None:
        try:
            identifier = int(tmdb_id)
        except (TypeError, ValueError):
            return None
        kind = "tv" if str(media_type) == "tv" else "movie"
        return seerr_title(self._get(f"/api/v1/{kind}/{identifier}"))


class Arr:
    """Sonarr/Radarr/Prowlarr share the v3/v1 REST shape."""

    def __init__(self, name: str, url: str, key: str, api: str = "v3", timeout: float = 8.0) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.key = key
        self.api = api
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _get(self, path: str) -> Any:
        return http_json(
            f"{self.url}/api/{self.api}{path}",
            headers={"X-Api-Key": self.key, "Accept": "application/json"},
            timeout=self.timeout,
        )

    def health(self) -> list[dict]:
        payload = self._get("/health")
        if not isinstance(payload, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("type"), str)
            for row in payload
        ):
            raise ClientError(f"{self.name}: unexpected health payload")
        return payload

    def status(self) -> dict:
        payload = self._get("/system/status")
        _require_version(payload, "version", self.name)
        return payload

    def queue(self, kind: str) -> dict:
        """Return one complete, consistent queue or fail without partial data."""
        flags = (
            "includeUnknownSeriesItems=true&includeSeries=true"
            if kind == "sonarr"
            else "includeUnknownMovieItems=true&includeMovie=true"
        )
        records: list[dict] = []
        identifiers: set[str] = set()
        total: int | None = None
        first: dict = {}
        page = 1
        deadline = time.monotonic() + 30
        while True:
            if time.monotonic() >= deadline:
                raise ClientError(f"{self.name}: queue collection deadline exceeded")
            payload = self._get(f"/queue?page={page}&pageSize=50&{flags}")
            if time.monotonic() >= deadline:
                raise ClientError(f"{self.name}: queue collection deadline exceeded")
            if not isinstance(payload, dict):
                raise ClientError(f"{self.name}: unexpected queue payload")
            count = payload.get("totalRecords")
            rows = payload.get("records")
            if (
                type(count) is not int or not 0 <= count <= 100_000
                or type(payload.get("page")) is not int or payload["page"] != page
                or type(payload.get("pageSize")) is not int or payload["pageSize"] != 50
                or not isinstance(rows, list)
            ):
                raise ClientError(f"{self.name}: malformed queue pagination")
            if total is None:
                total = count
                first = payload
            if count != total or len(rows) != min(50, total - len(records)):
                raise ClientError(f"{self.name}: incomplete or changing queue")
            for row in rows:
                if not isinstance(row, dict):
                    raise ClientError(f"{self.name}: malformed queue record")
                identifier = row.get("id")
                if (
                    isinstance(identifier, bool)
                    or not isinstance(identifier, (int, str))
                    or not str(identifier)
                    or str(identifier) in identifiers
                    or ("trackedDownloadState" in row and not isinstance(row["trackedDownloadState"], str))
                ):
                    raise ClientError(f"{self.name}: malformed or repeated queue record")
                identifiers.add(str(identifier))
            records.extend(rows)
            if len(records) == total:
                return {**first, "records": records, "totalRecords": total}
            page += 1


def _require_version(payload: Any, key: str, app: str) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), str) or not payload[key].strip():
        raise ClientError(f"{app}: unexpected status payload")


class Bazarr:
    def __init__(self, url: str, key: str, timeout: float = 8.0) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def status(self) -> dict:
        payload = http_json(
            f"{self.url}/api/system/status",
            headers={"X-API-KEY": self.key, "Accept": "application/json"},
            timeout=self.timeout,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        _require_version(data, "bazarr_version", "bazarr")
        return payload


class Navidrome:
    def __init__(self, url: str, timeout: float = 8.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    def ping(self) -> bool:
        # Navidrome 0.64.2 /ping returns a single dot, not JSON or a login page.
        request = urllib.request.Request(f"{self.url}/ping", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(1024)
        except urllib.error.HTTPError as exc:
            raise ClientError(f"HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            raise ClientError(str(getattr(exc, "reason", exc))) from exc
        if body != b".":
            raise ClientError("navidrome: unexpected ping payload")
        return True
