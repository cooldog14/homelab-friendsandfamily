"""HTTP surface: one JSON snapshot, one health probe, one rate-limited ping.

The browser only ever sees normalized read-only data; every credential stays in
this process and is sent upstream as a request header.
"""

from __future__ import annotations

import json
import signal
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import clients
import parsers
import snapshot as snapshot_module
from collectors import Collectors
from config import Settings, load_config

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/static/index.html": ("index.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 4096
PING_MIN_INTERVAL = 2.0
CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class PingGate:
    """One in-flight ping per peer, minimum interval between pings."""

    def __init__(self, interval: float = PING_MIN_INTERVAL) -> None:
        self.interval = interval
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}
        self._inflight: set[str] = set()

    def acquire(self, peer_id: str) -> float | None:
        """Return retry-after seconds when refused, None when allowed."""
        now = time.monotonic()
        with self._lock:
            if peer_id in self._inflight:
                return 0.5
            last = self._last.get(peer_id)
            if last is not None and now - last < self.interval:
                return round(self.interval - (now - last), 1)
            self._inflight.add(peer_id)
            return None

    def release(self, peer_id: str) -> None:
        with self._lock:
            self._inflight.discard(peer_id)
            self._last[peer_id] = time.monotonic()


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], collectors: Collectors, settings: Settings) -> None:
        super().__init__(address, Handler)
        self.collectors = collectors
        self.settings = settings
        self.config = collectors.config
        self.gate = PingGate()


class Handler(BaseHTTPRequestHandler):
    server_version = "homelab-dashboard"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def dashboard(self) -> DashboardServer:
        return self.server  # type: ignore[return-value]

    # -- plumbing --------------------------------------------------------- #

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"dashboard: {self.address_string()} {fmt % args}", file=sys.stderr)

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        try:
            body = parsers.json_dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            body = json.dumps({"error": f"serialization failed: {exc}"}).encode("utf-8")
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        self._headers(int(status), "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _read_body(self) -> bytes | None:
        length = self.headers.get("Content-Length")
        if length is None:
            return b""
        try:
            size = int(length)
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
            return None
        if size < 0 or size > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
            return None
        return self.rfile.read(size)

    # -- routes ----------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json({"ok": True, "now": iso_now()})
            return
        if path == "/api/snapshot":
            self._snapshot()
            return
        if path == "/metrics":
            body = self.dashboard.collectors.render_metrics().encode("utf-8")
            self._headers(HTTPStatus.OK, "text/plain; version=0.0.4; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path in STATIC_FILES:
            self._static(*STATIC_FILES[path])
            return
        if path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        body = self._read_body()
        if body is None:
            return
        if path == "/api/tailscale/ping":
            self._tailscale_ping(body)
            return
        if path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")
            return
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    def do_PUT(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    def do_DELETE(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    def do_PATCH(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    # -- handlers --------------------------------------------------------- #

    def _snapshot(self) -> None:
        try:
            payload = snapshot_module.build_snapshot(
                self.dashboard.collectors, self.dashboard.config, self.dashboard.settings
            )
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the browser
            print(f"dashboard: snapshot failed: {exc}", file=sys.stderr)
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "snapshot unavailable")
            return
        self._json(payload)

    def _static(self, filename: str, content_type: str) -> None:
        path = (STATIC_DIR / filename).resolve()
        if STATIC_DIR.resolve() not in path.parents and path.parent != STATIC_DIR.resolve():
            self._error(HTTPStatus.FORBIDDEN, "forbidden")
            return
        try:
            body = path.read_bytes()
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        self._headers(HTTPStatus.OK, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _tailscale_ping(self, body: bytes) -> None:
        try:
            request = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid JSON body")
            return
        peer_id = request.get("id") if isinstance(request, dict) else None
        if not isinstance(peer_id, str) or not peer_id:
            self._error(HTTPStatus.BAD_REQUEST, "id is required")
            return

        status = self.dashboard.collectors.network.get() or {}
        peers = {str(peer.get("id")): peer for peer in status.get("peers") or []}
        peer = peers.get(peer_id)
        if not peer or not peer.get("ip"):
            self._error(HTTPStatus.NOT_FOUND, "unknown peer")
            return

        gate = self.dashboard.gate
        retry = gate.acquire(peer_id)
        if retry is not None:
            self._json(
                {
                    "latency_ms": None,
                    "path": "error",
                    "endpoint": None,
                    "derp": None,
                    "error": f"rate limited, retry in {retry:.1f}s",
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return
        try:
            payload = self.dashboard.collectors.tailscale.ping(peer["ip"])
        except (clients.ClientError, socket.error) as exc:
            gate.release(peer_id)
            self._json(
                {
                    "latency_ms": None,
                    "path": "error",
                    "endpoint": None,
                    "derp": None,
                    "error": str(exc) or "ping failed",
                }
            )
            return
        gate.release(peer_id)

        latency = payload.get("LatencySeconds")
        endpoint = payload.get("Endpoint") or None
        derp = payload.get("DERPRegionCode") or None
        status_text = str(payload.get("Status") or "").lower()
        error = None
        if status_text and status_text != "ok":
            error = str(payload.get("Status"))
        path = "direct" if endpoint else ("relay" if derp else "error")
        latency_ms = None
        try:
            latency_ms = round(float(latency) * 1000, 1)
        except (TypeError, ValueError):
            latency_ms = None
        self._json(
            {
                "latency_ms": latency_ms,
                "path": path,
                "endpoint": endpoint,
                "derp": derp,
                "error": error,
            }
        )


def main() -> int:
    settings = Settings.from_env()
    config = load_config()
    collectors = Collectors(settings, config)
    collectors.start()
    server = DashboardServer((settings.bind, settings.port), collectors, settings)

    def shutdown(signum: int, _frame: Any) -> None:
        print(f"dashboard: signal {signum}, stopping", file=sys.stderr)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(
        f"dashboard: listening on {settings.bind}:{settings.port} "
        f"(stacks={settings.stacks_root})",
        file=sys.stderr,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        collectors.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
