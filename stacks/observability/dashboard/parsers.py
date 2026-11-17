"""Pure parsers and normalizers.

Every function here takes text or decoded JSON and returns plain data; none of
them touch a socket, the clock, or the filesystem. That is deliberate: the unit
tests exercise exactly what runs in the container.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------------------- #
# Compose
# --------------------------------------------------------------------------- #

RO_MODE = "ro"
_PORT_RANGE_RE = re.compile(r"^\d+(?:-\d+)?$")


def _split_colons(value: str) -> list[str]:
    """Split on ':' outside ${...} and [...].

    Compose ports and volumes both hide colons inside placeholders
    (``${TS_IP:-127.0.0.1}:443:443``) and IPv6 literals (``[::1]:80:80``).
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for char in value:
        if char in "{[":
            depth += 1
        elif char in "}]" and depth:
            depth -= 1
        if char == ":" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


def _port_value(raw: Any) -> int | str | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    return text or None


def parse_port_entry(entry: Any) -> list[dict]:
    """Normalize one Compose ports item (short or long syntax) to rows."""
    if isinstance(entry, bool):  # bool is an int subclass; never a port
        return []
    if isinstance(entry, int):
        return [
            {
                "host_ip": None,
                "host_port": None,
                "container_port": entry,
                "proto": "tcp",
            }
        ]
    if isinstance(entry, dict):
        container = _port_value(entry.get("target"))
        if container is None:
            return []
        return [
            {
                "host_ip": (str(entry.get("host_ip")).strip() or None)
                if entry.get("host_ip")
                else None,
                "host_port": _port_value(entry.get("published")),
                "container_port": container,
                "proto": str(entry.get("protocol") or "tcp").lower(),
            }
        ]
    if not isinstance(entry, str):
        return []
    spec = entry.strip()
    if not spec:
        return []
    proto = "tcp"
    if "/" in spec:
        spec, _, proto = spec.rpartition("/")
        proto = proto.strip().lower() or "tcp"
    parts = _split_colons(spec)
    host_ip = None
    host_port: int | str | None = None
    container: int | str | None = None
    if len(parts) >= 3:
        host_ip = parts[0].strip() or None
        host_port = _port_value(parts[1])
        container = _port_value(parts[2])
    elif len(parts) == 2:
        left, right = parts
        if _PORT_RANGE_RE.match(left.strip()):
            host_port = _port_value(left)
        else:
            # `10.44.0.2:8096` (no published port) is host_ip:container.
            host_ip = left.strip() or None
        container = _port_value(right)
    else:
        container = _port_value(parts[0])
    if container is None:
        return []
    return [
        {
            "host_ip": host_ip,
            "host_port": host_port,
            "container_port": container,
            "proto": proto,
        }
    ]


def parse_volume_entry(entry: Any) -> dict | None:
    """Normalize one Compose volumes item to {source, target, mode}."""
    if isinstance(entry, dict):
        target = entry.get("target")
        if not target:
            return None
        return {
            "source": str(entry["source"]) if entry.get("source") else None,
            "target": str(target),
            "mode": RO_MODE if entry.get("read_only") else "rw",
        }
    if not isinstance(entry, str) or not entry.strip():
        return None
    parts = _split_colons(entry.strip())
    if len(parts) == 1:
        return {"source": None, "target": parts[0], "mode": "rw"}
    source = parts[0] or None
    target = parts[1]
    if not target:
        return None
    mode = "rw"
    for extra in parts[2:]:
        if extra in ("ro", "rw"):
            mode = extra
    return {"source": source, "target": target, "mode": mode}


def image_tag(image: str | None) -> str | None:
    """Tag of an image reference; `<registry>/name` without a tag is `latest`."""
    if not image:
        return None
    tail = image.rsplit("/", 1)[-1]
    if ":" in tail:
        return tail.rsplit(":", 1)[1] or "latest"
    return "latest"


def parse_compose(text: str, stack: str) -> dict:
    """Parse one docker-compose.yml into the flat shape the dashboard needs."""
    import yaml  # local import keeps `python -m py_compile` cheap

    doc = yaml.safe_load(text) or {}
    services = doc.get("services") or {}
    parsed: dict[str, dict] = {}
    for name, spec in services.items():
        spec = spec or {}
        ports: list[dict] = []
        for entry in spec.get("ports") or []:
            ports.extend(parse_port_entry(entry))
        volumes = [
            volume
            for volume in (parse_volume_entry(e) for e in spec.get("volumes") or [])
            if volume
        ]
        image = spec.get("image")
        parsed[str(name)] = {
            "stack": stack,
            "service": str(name),
            "image": str(image) if image else None,
            "image_tag": image_tag(str(image) if image else None),
            "build": bool(spec.get("build")),
            "ports": ports,
            "volumes": volumes,
            "network_mode": spec.get("network_mode"),
            "restart": spec.get("restart"),
        }
    return {
        "stack": stack,
        "services": parsed,
        "networks": sorted(str(name) for name in (doc.get("networks") or {})),
    }


# --------------------------------------------------------------------------- #
# Caddy
# --------------------------------------------------------------------------- #

_COMMENT_RE = re.compile(r"\s+#.*$")
_PRIVATE_ALIAS_RE = re.compile(r"^@(\S+)\s+host\s+(\S+)\s*$")
_PRIVATE_PROXY_RE = re.compile(r"^reverse_proxy\s+@(\S+)\s+(\S+)")
_PUBLIC_SITE_RE = re.compile(r"^(\S+)\s*\{$")
_PUBLIC_IMPORT_RE = re.compile(r"^import\s+public_proxy\s+(\S+)")
_PUBLIC_PROXY_RE = re.compile(r"^reverse_proxy\s+(\S+)")


def strip_comment(line: str) -> str:
    return _COMMENT_RE.sub("", line).strip()


def parse_private_caddy(text: str) -> list[dict]:
    """Route table of the private Caddyfile: `@alias host <name>` + reverse_proxy."""
    aliases: dict[str, str] = {}
    routes: list[dict] = []
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        alias = _PRIVATE_ALIAS_RE.match(line)
        if alias:
            aliases[alias.group(1)] = alias.group(2)
            continue
        proxy = _PRIVATE_PROXY_RE.match(line)
        if proxy:
            host = aliases.get(proxy.group(1))
            if not host:
                continue
            routes.append(
                {
                    "exposure": "private",
                    "host": host,
                    "upstream": proxy.group(2),
                    "matcher": proxy.group(1),
                }
            )
    return routes


def parse_public_caddy(text: str) -> list[dict]:
    """Route table of one VPS site file (`host { ... }` blocks)."""
    routes: list[dict] = []
    host: str | None = None
    depth = 0
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if depth == 0:
            site = _PUBLIC_SITE_RE.match(line)
            if site:
                host = site.group(1)
                depth = line.count("{") - line.count("}")
            continue
        if host:
            imported = _PUBLIC_IMPORT_RE.match(line)
            if imported:
                routes.append(
                    {
                        "exposure": "public",
                        "host": host,
                        "upstream": f"10.44.0.2:{imported.group(1)}",
                        "matcher": None,
                    }
                )
            else:
                proxy = _PUBLIC_PROXY_RE.match(line)
                if proxy:
                    routes.append(
                        {
                            "exposure": "public",
                            "host": host,
                            "upstream": proxy.group(1),
                            "matcher": None,
                        }
                    )
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            depth = 0
            host = None
    return routes


def parse_deployed_meta(text: str) -> dict:
    """`key=value` lines written by host/deploy.sh."""
    meta: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        meta[key.strip()] = value.strip()
    return meta


# --------------------------------------------------------------------------- #
# Docker logs
# --------------------------------------------------------------------------- #

_ERROR_RE = re.compile(
    r"(?<![A-Za-z])(?:ERROR|ERR|FATAL|CRITICAL|PANIC|EMERG|ALERT)(?![A-Za-z])",
    re.IGNORECASE,
)
_WARN_RE = re.compile(
    r"(?<![A-Za-z])(?:WARN|WARNING|WRN)(?![A-Za-z])", re.IGNORECASE
)
_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+(.*)$",
    re.DOTALL,
)

# Docker's raw stream framing: [stream, 0, 0, 0, len_be32] + payload.
_FRAME_HEADER = 8


def demux_docker_logs(raw: bytes) -> bytes:
    """Strip Docker's 8-byte stream headers; return raw bytes for TTY streams."""
    out = bytearray()
    offset = 0
    frames = 0
    while offset + _FRAME_HEADER <= len(raw):
        stream = raw[offset]
        if stream not in (0, 1, 2) or raw[offset + 1 : offset + 4] != b"\x00\x00\x00":
            break
        size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        start = offset + _FRAME_HEADER
        end = start + size
        if end > len(raw):
            break
        out += raw[start:end]
        offset = end
        frames += 1
    if frames == 0:
        return raw
    out += raw[offset:]
    return bytes(out)


def classify_level(message: str) -> str:
    if _ERROR_RE.search(message):
        return "error"
    if _WARN_RE.search(message):
        return "warn"
    return "info"


def parse_timestamp(text: str) -> datetime | None:
    raw = text.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # Trim nanoseconds: fromisoformat() handles at most microseconds.
    if "." in raw:
        head, _, rest = raw.partition(".")
        frac = re.match(r"(\d+)", rest)
        suffix = rest[frac.end():] if frac else ""
        digits = (frac.group(1) if frac else "")[:6].ljust(6, "0")
        raw = f"{head}.{digits}{suffix}"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_docker_logs(
    raw: bytes, service: str, secrets: Sequence[str] = ()
) -> list[dict]:
    """Decode one container's log tail into timestamped, redacted events."""
    events: list[dict] = []
    for line in demux_docker_logs(raw).decode("utf-8", "replace").splitlines():
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        stamp = None
        message = line
        match = _TS_RE.match(line)
        if match:
            stamp = parse_timestamp(match.group(1))
            message = match.group(2)
        message = redact_secrets(message, secrets)
        events.append(
            {
                "ts": iso_z(stamp) if stamp else None,
                "service": service,
                "level": classify_level(message),
                "message": message.strip()[:1000],
            }
        )
    return events


def redact_secrets(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "***")
    return text


# --------------------------------------------------------------------------- #
# API payloads
# --------------------------------------------------------------------------- #

TICKS_PER_SECOND = 10_000_000


def ticks_to_seconds(value: Any) -> float | None:
    try:
        ticks = int(value)
    except (TypeError, ValueError):
        return None
    if ticks <= 0:
        return None
    return round(ticks / TICKS_PER_SECOND, 3)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def normalize_jellyfin_sessions(payload: Any) -> dict:
    """Active Jellyfin streams, direct-play/transcode counts, version-less."""
    streams: list[dict] = []
    for session in _as_list(payload):
        if not isinstance(session, dict):
            continue
        item = session.get("NowPlayingItem") or {}
        if not isinstance(item, dict) or not item:
            continue
        play = session.get("PlayState") or {}
        method = str(play.get("PlayMethod") or "DirectPlay")
        streams.append(
            {
                "user": session.get("UserName"),
                "device": session.get("DeviceName"),
                "client": session.get("Client"),
                "title": item.get("Name"),
                "series": item.get("SeriesName"),
                "season": item.get("ParentIndexNumber"),
                "episode": item.get("IndexNumber"),
                "type": item.get("Type"),
                "method": method,
                "paused": bool(play.get("IsPaused")),
                "position_s": ticks_to_seconds(play.get("PositionTicks")),
                "runtime_s": ticks_to_seconds(item.get("RunTimeTicks")),
            }
        )
    direct = sum(1 for row in streams if row["method"] in ("DirectPlay", "DirectStream"))
    transcode = sum(1 for row in streams if row["method"] == "Transcode")
    return {
        "active": len(streams),
        "direct": direct,
        "transcode": transcode,
        "streams": streams,
    }


def normalize_jellyfin_recent(payload: Any) -> list[dict]:
    items = payload.get("Items") if isinstance(payload, dict) else payload
    rows: list[dict] = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": item.get("Name"),
                "series": item.get("SeriesName"),
                "year": item.get("ProductionYear"),
                "type": item.get("Type"),
                "created": item.get("DateCreated"),
            }
        )
    return rows


def jellyfin_version(payload: Any) -> str | None:
    if isinstance(payload, dict):
        version = payload.get("Version")
        return str(version) if version else None
    return None


def normalize_seerr_requests(payload: Any) -> list[dict]:
    """Jellyseerr request rows. Titles are resolved separately."""
    records = payload.get("results") if isinstance(payload, dict) else payload
    rows: list[dict] = []
    for request in _as_list(records):
        if not isinstance(request, dict):
            continue
        media = request.get("media") or {}
        media_type = request.get("type") or media.get("mediaType")
        if not media_type:
            media_type = "tv" if media.get("tvdbId") else "movie"
        rows.append(
            {
                "id": request.get("id"),
                "type": str(media_type),
                "tmdb_id": media.get("tmdbId"),
                "tvdb_id": media.get("tvdbId"),
                "requester": (request.get("requestedBy") or {}).get("displayName")
                or (request.get("requestedBy") or {}).get("username"),
                "created": request.get("createdAt"),
                "updated": request.get("updatedAt"),
                "status": request.get("status"),
            }
        )
    return rows


def seerr_title(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("title", "name", "originalTitle", "originalName"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def arr_version(payload: Any) -> str | None:
    if isinstance(payload, dict):
        version = payload.get("version")
        return str(version) if version else None
    return None


STALLED_STATES = {"importblocked", "importpending", "failedpending"}


def normalize_arr_queue(payload: Any, kind: str) -> dict:
    """Sonarr/Radarr queue with the documented stall classification."""
    records = payload.get("records") if isinstance(payload, dict) else payload
    rows: list[dict] = []
    for record in _as_list(records):
        if not isinstance(record, dict):
            continue
        state = str(record.get("trackedDownloadState") or "")
        tracked = str(record.get("trackedDownloadStatus") or "")
        status = str(record.get("status") or "")
        stalled = (
            state.lower() in STALLED_STATES
            or tracked.lower() in ("warning", "error")
            or status.lower() == "warning"
        )
        size = record.get("size")
        size_left = record.get("sizeleft")
        progress = None
        if isinstance(size, (int, float)) and isinstance(size_left, (int, float)) and size > 0:
            progress = round(100 * (1 - size_left / size), 1)
        rows.append(
            {
                "kind": kind,
                "title": record.get("title") or (record.get("movie") or {}).get("title"),
                "series": (record.get("series") or {}).get("title"),
                "status": status,
                "tracked_status": tracked,
                "tracked_state": state,
                "error": record.get("errorMessage") or None,
                "progress": progress,
                "stalled": stalled,
            }
        )
    stalled_rows = [row for row in rows if row["stalled"]]
    total = payload.get("totalRecords") if isinstance(payload, dict) else None
    return {
        "kind": kind,
        "total": total if isinstance(total, int) else len(rows),
        "rows": rows,
        "stalled": stalled_rows,
    }


def normalize_prometheus_alerts(payload: Any) -> list[dict]:
    """Alertmanager/Prometheus alert state, firing and pending."""
    rows: list[dict] = []
    for alert in _as_list(payload):
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        since = parse_timestamp(str(alert.get("activeAt") or ""))
        rows.append(
            {
                "name": labels.get("alertname"),
                "severity": str(labels.get("severity") or "warning").lower(),
                "state": str(alert.get("state") or "").lower(),
                "since": iso_z(since) if since else None,
                "summary": annotations.get("summary"),
                "description": annotations.get("description"),
                "host": labels.get("host") or labels.get("instance"),
                "value": alert.get("value"),
            }
        )
    return rows


def normalize_container_detail(payload: Any) -> dict:
    """Why a container is not serving: exit code, OOM, restarts, error text."""
    document = payload if isinstance(payload, dict) else {}
    state = document.get("State") or {}
    code = state.get("ExitCode")
    restarts = document.get("RestartCount")
    return {
        "exit_code": code if isinstance(code, int) else None,
        "oom_killed": bool(state.get("OOMKilled")),
        "error": str(state.get("Error")) if state.get("Error") else None,
        "restart_count": restarts if isinstance(restarts, int) else None,
        "started_at": state.get("StartedAt") or None,
        "finished_at": state.get("FinishedAt") or None,
    }


def normalize_arr_health(payload: Any) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    for entry in _as_list(payload):
        if not isinstance(entry, dict):
            continue
        message = str(entry.get("message") or entry.get("source") or "unknown")
        kind = str(entry.get("type") or "").lower()
        if kind == "error":
            errors.append(message)
        elif kind in ("warning", "warn"):
            warnings.append(message)
    return {"errors": errors, "warnings": warnings, "ok": not errors and not warnings}


# --------------------------------------------------------------------------- #
# URLs
# --------------------------------------------------------------------------- #

_SAFE_SCHEMES = ("http://", "https://")


def safe_url(url: Any) -> bool:
    """Only absolute http(s) URLs may reach an href."""
    if not isinstance(url, str):
        return False
    text = url.strip()
    if not text.lower().startswith(_SAFE_SCHEMES):
        return False
    return "\n" not in text and "\r" not in text and " " not in text


def json_dumps(payload: Any) -> str:
    """Serialize with NaN/Infinity rejected: a bad float must never break the API."""
    return json.dumps(payload, allow_nan=False, separators=(",", ":"))
