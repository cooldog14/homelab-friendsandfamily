#!/usr/bin/env python3
"""Read-only status bit consumed by the external WAN heartbeat Worker.

The Worker probes https://health.malice.biz from the internet. This service
answers 200 with {"ok": true|false} for any path; the Worker reads that body
instead of treating the vhost as an ordinary public endpoint. It exposes no
admin UI and no secrets -- only whether the local alert pipeline is healthy.
Reuses the dashboard image (python:3.13-slim, stdlib only) so no new image is
needed; the compose service runs this file instead of app.py.

A stale gauge is unhealthy: if homelab-pipeline-check.timer stops running, the
Worker must fail the Healthchecks check rather than trust an old "all green"
file. Binding 0.0.0.0 here is container-internal; the host publishes only
10.44.0.2:8098.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GAUGE = Path(os.environ.get("PIPELINE_GAUGE", "/textfile/homelab-alert-path.prom"))
MAX_AGE_SECONDS = 15 * 60
PORT = int(os.environ.get("PORT", "8080"))
EXPECTED_COMPONENTS = 4


def pipeline_ok() -> bool:
    try:
        if time.time() - GAUGE.stat().st_mtime > MAX_AGE_SECONDS:
            return False
        values = []
        for line in GAUGE.read_text(encoding="utf-8").splitlines():
            if line.startswith("homelab_alert_path_healthy{"):
                values.append(int(line.rsplit(" ", 1)[1]))
        return len(values) == EXPECTED_COMPONENTS and all(v == 1 for v in values)
    except (OSError, ValueError, IndexError):
        return False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        body = json.dumps({"ok": pipeline_ok()}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
