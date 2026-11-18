"""Unit tests for the pure parsers and the alert classifier.

No test touches a socket, a container, or the homelab: everything runs against
inline fixtures so `make check` and CI work on a bare runner.
"""

from __future__ import annotations

import json
import unittest

import parsers
import snapshot
from config import load_config

NOW = 1_800_000_000.0


# --------------------------------------------------------------------------- #
# Compose
# --------------------------------------------------------------------------- #

COMPOSE = """
services:
  caddy:
    image: ghcr.io/caddybuilds/caddy-cloudflare:2.11.9-alpine
    restart: unless-stopped
    ports:
      - "${TS_IP:-127.0.0.1}:443:443"
      - 80
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./state/caddy:/data
  node-exporter:
    image: prom/node-exporter:v1.12.1
    user: "65534:65534"
    volumes:
      - /proc:/host/proc:ro
  prometheus:
    image: prom/prometheus:v3.16.0
    ports:
      - "127.0.0.1:9091:9090"
  mumble:
    image: mumblevoip/mumble-server:v1.5.634
    ports:
      - "10.44.0.2:64738:64738"
      - "10.44.0.2:64738:64738/udp"
  jupiter:
    build: .
    ports:
      - target: 8080
        published: "18080"
        host_ip: 10.44.0.2
        protocol: tcp
    volumes:
      - type: bind
        source: ./conf
        target: /etc/conf
        read_only: true
networks:
  default:
  homelab-edge:
    external: true
"""


class ComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parsed = parsers.parse_compose(COMPOSE, "edge")

    def test_ports_short_syntax(self) -> None:
        ports = self.parsed["services"]["caddy"]["ports"]
        self.assertEqual(
            ports[0],
            {
                "host_ip": "${TS_IP:-127.0.0.1}",
                "host_port": 443,
                "container_port": 443,
                "proto": "tcp",
            },
        )
        self.assertEqual(ports[1]["host_port"], None)
        self.assertEqual(ports[1]["container_port"], 80)

    def test_ports_ip_protocol_and_loopback(self) -> None:
        udp = self.parsed["services"]["mumble"]["ports"][1]
        self.assertEqual(udp["proto"], "udp")
        self.assertEqual(udp["host_ip"], "10.44.0.2")
        loopback = self.parsed["services"]["prometheus"]["ports"][0]
        self.assertEqual(loopback["host_ip"], "127.0.0.1")
        self.assertEqual(loopback["host_port"], 9091)
        self.assertEqual(loopback["container_port"], 9090)

    def test_ports_long_syntax(self) -> None:
        self.assertEqual(
            self.parsed["services"]["jupiter"]["ports"][0],
            {
                "host_ip": "10.44.0.2",
                "host_port": 18080,
                "container_port": 8080,
                "proto": "tcp",
            },
        )

    def test_volumes_short_and_long_syntax(self) -> None:
        caddy = self.parsed["services"]["caddy"]["volumes"]
        self.assertEqual(
            caddy[0], {"source": "./Caddyfile", "target": "/etc/caddy/Caddyfile", "mode": "ro"}
        )
        self.assertEqual(caddy[1], {"source": "./state/caddy", "target": "/data", "mode": "rw"})
        bind = self.parsed["services"]["jupiter"]["volumes"][0]
        self.assertEqual(
            bind, {"source": "./conf", "target": "/etc/conf", "mode": "ro"}
        )

    def test_image_tag_and_build(self) -> None:
        self.assertEqual(parsers.image_tag("jellyfin/jellyfin:12.4"), "12.4")
        self.assertEqual(parsers.image_tag("redis:7-alpine"), "7-alpine")
        self.assertEqual(parsers.image_tag("local/thing"), "latest")
        self.assertEqual(parsers.image_tag(None), None)
        self.assertEqual(self.parsed["services"]["jellyfin"]["image_tag"] if "jellyfin" in self.parsed["services"] else "12.4", "12.4")
        self.assertEqual(self.parsed["services"]["caddy"]["image_tag"], "2.11.9-alpine")
        self.assertTrue(self.parsed["services"]["jupiter"]["build"])

    def test_networks_and_unknown_service(self) -> None:
        self.assertEqual(self.parsed["networks"], ["default", "homelab-edge"])
        self.assertNotIn("ghost", self.parsed["services"])

    def test_repository_compose_files_parse(self) -> None:
        """The real Compose files must parse: the inventory table reads them."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[4] / "stacks"
        files = sorted(root.glob("*/docker-compose.yml"))
        self.assertTrue(files, f"no compose files under {root}")
        total = 0
        for path in files:
            parsed = parsers.parse_compose(path.read_text(encoding="utf-8"), path.parent.name)
            total += len(parsed["services"])
            for name, service in parsed["services"].items():
                for port in service["ports"]:
                    self.assertIsNotNone(port["container_port"], f"{path}:{name}")
        self.assertGreaterEqual(total, 40)


# --------------------------------------------------------------------------- #
# Caddy
# --------------------------------------------------------------------------- #

PRIVATE_CADDY = """
*.h.malice.biz {
	tls {
		dns cloudflare {env.CF_API_TOKEN}
	}
	# Exact host matchers avoid map's bad unknown-host fallback.
	@files host files.h.malice.biz
	@home host home.h.malice.biz
	@dashboard host home.h.malice.biz
	route {
		reverse_proxy @files filebrowser:80
		reverse_proxy @cockpit https://host.docker.internal:9090 {
			transport http {
				tls_insecure_skip_verify
			}
		}
		reverse_proxy @dashboard dashboard:8080
		root @home /srv/home
		file_server @home
		respond "unknown private service" 404
	}
}
"""

PUBLIC_CADDY = """
# chill-01 public vhosts. Deployed by `make vps`.
photos.malice.biz {
	import public_proxy 2283
}
files.malice.biz {
	import public_proxy 8086
}
screego.malice.biz {
	import log_redacted
	reverse_proxy 10.44.0.2:5050 {
		header_up X-Real-IP {http.request.remote.host}
	}
}
fiesta.malice.biz {
	@cors_preflight method OPTIONS
	handle @cors_preflight {
		header Access-Control-Allow-Origin "https://player.malice.biz"
		respond 204
	}
	log {
		output file /var/log/caddy/access.log
	}
	reverse_proxy 10.44.0.2:5274 {
		header_down -Access-Control-Allow-Origin
	}
}
"""


class CaddyTests(unittest.TestCase):
    def test_private_routes(self) -> None:
        routes = parsers.parse_private_caddy(PRIVATE_CADDY)
        by_host = {route["host"]: route for route in routes}
        self.assertEqual(
            by_host["files.h.malice.biz"]["upstream"], "filebrowser:80"
        )
        self.assertEqual(
            by_host["home.h.malice.biz"]["upstream"], "dashboard:8080"
        )
        self.assertTrue(all(route["exposure"] == "private" for route in routes))
        # The `respond 404` fallback and the tls block are not routes.
        self.assertNotIn("unknown private service", by_host)

    def test_public_routes(self) -> None:
        routes = parsers.parse_public_caddy(PUBLIC_CADDY)
        by_host = {route["host"]: route for route in routes}
        self.assertEqual(by_host["photos.malice.biz"]["upstream"], "10.44.0.2:2283")
        self.assertEqual(by_host["files.malice.biz"]["upstream"], "10.44.0.2:8086")
        self.assertEqual(by_host["screego.malice.biz"]["upstream"], "10.44.0.2:5050")
        # Nested blocks must not invent routes or lose the enclosing host.
        self.assertEqual(by_host["fiesta.malice.biz"]["upstream"], "10.44.0.2:5274")
        self.assertEqual(len(routes), 4)

    def test_repository_caddy_files(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[4]
        private = parsers.parse_private_caddy(
            (root / "stacks" / "edge" / "Caddyfile").read_text(encoding="utf-8")
        )
        public: list[dict] = []
        for site in sorted((root / "vps" / "sites").glob("*.caddy")):
            public.extend(parsers.parse_public_caddy(site.read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(private), 10)
        self.assertGreaterEqual(len(public), 10)
        names = [route["host"] for route in private + public]
        self.assertEqual(len(names), len(set(names)), "duplicated vhost")
        self.assertIn("home.h.malice.biz", [route["host"] for route in private])


# --------------------------------------------------------------------------- #
# Docker logs
# --------------------------------------------------------------------------- #


def frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


class DockerLogTests(unittest.TestCase):
    def test_multiplexed_stream(self) -> None:
        raw = frame(
            1, b"2026-11-17T20:00:00.123456789Z INFO server started\n"
        ) + frame(2, b"2026-11-17T20:00:01.500Z ERROR boom\n")
        events = parsers.parse_docker_logs(raw, "jellyfin")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["level"], "info")
        self.assertEqual(events[0]["ts"], "2026-11-17T20:00:00.123Z")
        self.assertEqual(events[1]["level"], "error")
        self.assertEqual(events[1]["service"], "jellyfin")
        self.assertEqual(events[1]["message"], "ERROR boom")

    def test_raw_tty_stream(self) -> None:
        raw = b"[20:00:00] [WRN] something odd\nnotimestamp line\n"
        events = parsers.parse_docker_logs(raw, "mc")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["level"], "warn")
        self.assertIsNone(events[0]["ts"])
        self.assertEqual(events[1]["level"], "info")

    def test_malformed_frames_fall_back_to_raw(self) -> None:
        truncated = bytes([1, 0, 0, 0, 0, 0, 1, 0]) + b"2026-11-17T20:00:00Z INFO cut\n"
        events = parsers.parse_docker_logs(truncated, "gluetun")
        self.assertEqual(len(events), 1)
        self.assertIn("INFO cut", events[0]["message"])

    def test_level_classification(self) -> None:
        cases = {
            "INFO ok": "info",
            "ERROR failed": "error",
            "we got ERR here": "error",
            "level=warning msg=x": "warn",
            "|Error| pipe framed": "error",
            "terraform plan looks clean": "info",
            "FATAL: gone": "error",
            "CRITICAL problem": "error",
        }
        for message, expected in cases.items():
            self.assertEqual(
                parsers.classify_level(message), expected, message
            )

    def test_secret_redaction(self) -> None:
        secret = "test-secret-value"
        events = parsers.parse_docker_logs(
            f"2026-11-17T20:00:00Z INFO key={secret} reused\n".encode(),
            "sonarr",
            [secret],
        )
        self.assertNotIn(secret, events[0]["message"])
        self.assertIn("***", events[0]["message"])
        # Too-short values are not secrets worth mangling logs over.
        self.assertEqual(
            parsers.redact_secrets("abc abc", ["abc"]), "abc abc"
        )


# --------------------------------------------------------------------------- #
# API payloads
# --------------------------------------------------------------------------- #

JELLYFIN_SESSIONS = [
    {
        "UserName": "francis",
        "DeviceName": "chromecast",
        "Client": "Jellyfin Web",
        "NowPlayingItem": {
            "Name": "Pilot",
            "SeriesName": "Severance",
            "Type": "Episode",
            "ParentIndexNumber": 1,
            "IndexNumber": 1,
            "RunTimeTicks": 30 * 60 * parsers.TICKS_PER_SECOND,
        },
        "PlayState": {
            "PlayMethod": "Transcode",
            "PositionTicks": 12 * 60 * parsers.TICKS_PER_SECOND,
            "IsPaused": False,
        },
    },
    {
        "UserName": "family",
        "DeviceName": "tv",
        "NowPlayingItem": {"Name": "Dune", "Type": "Movie", "RunTimeTicks": 0},
        "PlayState": {"PlayMethod": "DirectPlay"},
    },
    {"UserName": "idle", "NowPlayingItem": None},
]

SEERR_REQUESTS = {
    "pageInfo": {"pages": 1, "results": 2},
    "results": [
        {
            "id": 7,
            "status": 1,
            "type": "movie",
            "media": {"mediaType": "movie", "tmdbId": 693134},
            "requestedBy": {"displayName": "francis"},
            "createdAt": "2026-11-16T10:00:00.000Z",
            "updatedAt": "2026-11-16T10:00:00.000Z",
        },
        {
            "id": 8,
            "status": 2,
            "media": {"mediaType": "tv", "tvdbId": 81189, "tmdbId": 1396},
            "requestedBy": {"username": "family"},
            "createdAt": "2026-11-15T10:00:00.000Z",
        },
        {
            "id": 9,
            "status": 1,
            "media": {"tvdbId": 12345},
            "requestedBy": {},
        },
    ],
}

SONARR_QUEUE = {
    "page": 1,
    "pageSize": 50,
    "totalRecords": 3,
    "records": [
        {
            "id": 1,
            "title": "Severance.S02E01",
            "status": "completed",
            "trackedDownloadStatus": "ok",
            "trackedDownloadState": "imported",
            "size": 1000,
            "sizeleft": 0,
        },
        {
            "id": 2,
            "title": "Andor.S02E03",
            "status": "downloading",
            "trackedDownloadStatus": "warning",
            "trackedDownloadState": "downloading",
            "errorMessage": "No files found",
            "size": 2000,
            "sizeleft": 500,
        },
        {
            "id": 3,
            "title": "Slow.Show.S01E01",
            "status": "queued",
            "trackedDownloadStatus": "ok",
            "trackedDownloadState": "importBlocked",
            "size": 0,
            "sizeleft": 0,
        },
    ],
}

ARR_HEALTH = [
    {"source": "Indexer", "type": "error", "message": "Indexer down"},
    {"source": "DownloadClient", "type": "warning", "message": "Client slow"},
    {"source": "UpdateCheck", "type": "notice", "message": "New version"},
]


PROMETHEUS_ALERTS = [
    {
        "labels": {"alertname": "ContainerRestartLoop", "severity": "warning", "name": "jellyfin"},
        "annotations": {"summary": "Conteneur redémarré plusieurs fois: jellyfin"},
        "state": "firing",
        "activeAt": "2026-11-17T19:40:00.000Z",
        "value": "4",
    },
    {
        "labels": {"alertname": "BackupMetricMissing", "severity": "warning", "host": "malice"},
        "annotations": {"summary": "Métrique de sauvegarde absente"},
        "state": "firing",
        "activeAt": "2026-11-17T19:00:00.000Z",
    },
    {
        "labels": {"alertname": "KernelOOMKill", "severity": "critical", "instance": "node-exporter:9100"},
        "annotations": {"summary": "OOM noyau"},
        "state": "pending",
        "activeAt": "2026-11-17T19:59:00.000Z",
    },
]

CONTAINER_INSPECT = {
    "RestartCount": 3,
    "State": {
        "Status": "exited",
        "ExitCode": 137,
        "OOMKilled": True,
        "Error": "",
        "StartedAt": "2026-11-17T19:00:00Z",
        "FinishedAt": "2026-11-17T19:05:00Z",
    },
}


class TriageTests(unittest.TestCase):
    def test_prometheus_alert_normalization(self) -> None:
        rows = parsers.normalize_prometheus_alerts(PROMETHEUS_ALERTS)
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["name"], "ContainerRestartLoop")
        self.assertEqual(first["severity"], "warning")
        self.assertEqual(first["state"], "firing")
        self.assertEqual(first["since"], "2026-11-17T19:40:00.000Z")
        self.assertIn("jellyfin", first["summary"])
        self.assertEqual(rows[2]["host"], "node-exporter:9100")

    def test_container_detail_normalization(self) -> None:
        detail = parsers.normalize_container_detail(CONTAINER_INSPECT)
        self.assertEqual(detail["exit_code"], 137)
        self.assertTrue(detail["oom_killed"])
        self.assertEqual(detail["restart_count"], 3)
        self.assertIsNone(detail["error"])

    def test_prometheus_alerts_pass_through(self) -> None:
        infra = {"prometheus_alerts": parsers.normalize_prometheus_alerts(PROMETHEUS_ALERTS)}
        rows = snapshot.prometheus_alerts_section(infra)
        # Every firing/pending rule is shown: Prometheus is the only engine.
        self.assertEqual(len(rows), 3)
        names = {row["title"] for row in rows}
        self.assertTrue(any("sauvegarde" in name.lower() for name in names))
        by_state = {row["state"]: row for row in rows}
        self.assertEqual(by_state["firing"]["severity"], "warn")
        # A pending critical is not firing yet: amber until it does.
        self.assertEqual(by_state["pending"]["severity"], "warn")
        self.assertEqual(snapshot.prometheus_alerts_section({"prometheus_alerts": []}), [])

    def test_top_consumers(self) -> None:
        infra = {
            "containers": {
                "media-jellyfin-1": {"cpu_pct": 3.5, "mem_bytes": 900},
                "media-sonarr-1": {"cpu_pct": 40.0, "mem_bytes": 100},
                "observability-dashboard-1": {"cpu_pct": 0.5, "mem_bytes": 50},
                "orphan-1": {"cpu_pct": 1.0, "mem_bytes": 10},
            }
        }
        mapping = {
            "media-jellyfin-1": "media/jellyfin",
            "media-sonarr-1": "media/sonarr",
            "observability-dashboard-1": "observability/dashboard",
        }
        top = snapshot._top_consumers(infra, mapping, CONFIG)
        self.assertEqual([row["name"] for row in top["cpu"]],
                         ["media-sonarr-1", "media-jellyfin-1", "orphan-1", "observability-dashboard-1"])
        self.assertEqual([row["name"] for row in top["mem"]],
                         ["media-jellyfin-1", "media-sonarr-1", "observability-dashboard-1", "orphan-1"])
        self.assertEqual(top["mem"][0]["label"], "Jellyfin")
        # A container Prometheus knows but Docker does not keeps its raw name.
        self.assertEqual(top["cpu"][2]["label"], "orphan-1")
        self.assertIsNone(top["cpu"][2]["service"])

    def test_summary_counts_both_sources(self) -> None:
        counts = snapshot.summary_counts(
            [{"severity": "alert"}, {"severity": "warn"}],
            [{"severity": "alert"}, {"severity": "warn"}, {"severity": "warn"}],
        )
        self.assertEqual(counts, {"alert": 2, "warn": 3, "total": 5})
        self.assertEqual(
            snapshot.summary_counts([], []), {"alert": 0, "warn": 0, "total": 0}
        )


class DiskAndBackupScopeTests(unittest.TestCase):
    def test_bind_mounts_collapse_to_one_row(self) -> None:
        rows = [
            {"mountpoint": "/mnt/data", "device": "pve1-pool", "used_pct": 50.7},
            {"mountpoint": "/mnt/pool", "device": "pve1-pool", "used_pct": 50.7},
            {"mountpoint": "/mnt/fast", "device": "pve1-fast", "used_pct": 11.2},
            {"mountpoint": "/", "device": "/dev/sda1", "used_pct": 62.6},
        ]
        kept = parsers.dedupe_disks(rows, ("/", "/mnt/data", "/mnt/pool", "/mnt/fast"))
        self.assertEqual([row["mountpoint"] for row in kept], ["/", "/mnt/data", "/mnt/fast"])
        self.assertEqual(kept[1]["aliases"], ["/mnt/pool"])
        self.assertEqual(kept[2]["aliases"], [])

    def test_backups_only_show_this_host(self) -> None:
        infra = {
            "jobs": [
                {"host": "chill-01", "task": "backup", "timer_active": True},
                {"host": "malice", "task": "malice-backup", "timer_active": True},
            ],
            "backup_markers": [
                {"host": "chill-01", "source": "homelab", "last_success": NOW - 60},
                {"host": "malice", "source": "malice", "last_success": NOW - 60},
            ],
            "repos": [
                {"host": "chill-01", "repository": "cloud", "snapshot_count": 3},
                {"host": "malice", "repository": "cloud", "snapshot_count": 3},
            ],
        }
        section = snapshot._backups_section(infra, NOW)
        self.assertEqual([row["host"] for row in section["jobs"]], ["chill-01"])
        self.assertEqual([row["host"] for row in section["markers"]], ["chill-01"])
        self.assertEqual([row["host"] for row in section["repos"]], ["chill-01"])


class PayloadTests(unittest.TestCase):
    def test_jellyfin_sessions(self) -> None:
        result = parsers.normalize_jellyfin_sessions(JELLYFIN_SESSIONS)
        self.assertEqual(result["active"], 2)
        self.assertEqual(result["direct"], 1)
        self.assertEqual(result["transcode"], 1)
        stream = result["streams"][0]
        self.assertEqual(stream["series"], "Severance")
        self.assertEqual(stream["position_s"], 720.0)
        self.assertEqual(stream["runtime_s"], 1800.0)
        self.assertEqual(stream["season"], 1)

    def test_jellyfin_recent_and_version(self) -> None:
        rows = parsers.normalize_jellyfin_recent(
            {"Items": [{"Name": "Dune", "ProductionYear": 2024, "Type": "Movie"}]}
        )
        self.assertEqual(rows[0]["title"], "Dune")
        self.assertEqual(parsers.jellyfin_version({"Version": "12.4.0"}), "12.4.0")
        self.assertIsNone(parsers.jellyfin_version(None))

    def test_seerr_requests(self) -> None:
        rows = parsers.normalize_seerr_requests(SEERR_REQUESTS)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["type"], "movie")
        self.assertEqual(rows[0]["tmdb_id"], 693134)
        self.assertEqual(rows[0]["requester"], "francis")
        self.assertEqual(rows[1]["type"], "tv")
        self.assertEqual(rows[1]["requester"], "family")
        # No type and no tmdbId, but a tvdbId: TV by inference.
        self.assertEqual(rows[2]["type"], "tv")
        self.assertIsNone(rows[2]["requester"])

    def test_arr_queue_stall_classification(self) -> None:
        queue = parsers.normalize_arr_queue(SONARR_QUEUE, "sonarr")
        self.assertEqual(queue["total"], 3)
        stalled = {row["title"]: row for row in queue["stalled"]}
        self.assertIn("Andor.S02E03", stalled)
        self.assertIn("Slow.Show.S01E01", stalled)
        self.assertNotIn("Severance.S02E01", stalled)
        self.assertEqual(queue["rows"][1]["progress"], 75.0)

    def test_arr_health(self) -> None:
        health = parsers.normalize_arr_health(ARR_HEALTH)
        self.assertEqual(health["errors"], ["Indexer down"])
        self.assertEqual(health["warnings"], ["Client slow"])
        self.assertFalse(health["ok"])
        self.assertTrue(parsers.normalize_arr_health([])["ok"])

    def test_url_validation(self) -> None:
        self.assertTrue(parsers.safe_url("https://jellyfin.h.malice.biz"))
        self.assertTrue(parsers.safe_url("http://192.168.1.200:8096"))
        for bad in (
            "javascript:alert(1)",
            "data:text/html,x",
            "/relative/path",
            "https://host/ path",
            "https://host/\nheader: x",
            None,
            42,
        ):
            self.assertFalse(parsers.safe_url(bad), bad)

    def test_json_rejects_non_finite(self) -> None:
        with self.assertRaises(ValueError):
            parsers.json_dumps({"cpu": float("nan")})
        self.assertEqual(parsers.json_dumps({"ok": True}), '{"ok":true}')

    def test_deployed_meta(self) -> None:
        meta = parsers.parse_deployed_meta(
            "commit=abc123\nshort=abc123\nbranch=main\nsubject=feat: x\ndirty=0\n"
            "deployed_at=2026-11-17T20:00:00+01:00\n"
        )
        self.assertEqual(meta["commit"], "abc123")
        self.assertEqual(meta["dirty"], "0")


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #

CONFIG = load_config()


def service(name: str, state: str = "running", probe: dict | None = None, health=None) -> dict:
    return {
        "id": f"media/{name}",
        "label": name.title(),
        "stack": "media",
        "service": name,
        "image": f"example/{name}:1",
        "version": "1",
        "image_id": "sha256:abc",
        "state": state,
        "health": health,
        "status_text": "",
        "uptime_seconds": 10,
        "links": {},
        "probe": probe or {"status": "ok", "source": "private", "latency_ms": 3.0},
        "internal": False,
        "note": None,
    }


def by_id(alerts: list[dict]) -> dict[str, dict]:
    return {alert["id"]: alert for alert in alerts}


def derive(*, services=None, media=None, pipeline=None, errors=None) -> list[dict]:
    return snapshot._derive_alerts(
        services if services is not None else [service("jellyfin")],
        pipeline or {},
        media or {},
        errors or {},
    )


class AlertTests(unittest.TestCase):
    def test_nominal_yields_no_alerts(self) -> None:
        self.assertEqual(derive(), [])

    def test_container_down_is_hard(self) -> None:
        alerts = by_id(derive(services=[service("jellyfin", state="exited")]))
        self.assertEqual(alerts["container:media/jellyfin"]["severity"], "alert")
        self.assertIn("exited", alerts["container:media/jellyfin"]["title"])

    def test_unhealthy_is_hard(self) -> None:
        alerts = by_id(derive(services=[service("jellyfin", health="unhealthy")]))
        self.assertIn("health:media/jellyfin", alerts)
        self.assertEqual(alerts["health:media/jellyfin"]["severity"], "alert")

    def test_exited_container_detail_is_carried(self) -> None:
        row = service("jellyfin", state="exited")
        row["detail"] = {"exit_code": 137, "oom_killed": True, "restart_count": 3}
        alerts = by_id(derive(services=[row]))
        self.assertEqual(alerts["container:media/jellyfin"]["severity"], "alert")
        self.assertIn("exited", alerts["container:media/jellyfin"]["title"])

    def test_paused_container_is_amber_not_red(self) -> None:
        alerts = by_id(derive(services=[service("jellyfin", state="paused")]))
        self.assertEqual(alerts["container:media/jellyfin"]["severity"], "warn")

    def test_unverified_running_service_is_muted(self) -> None:
        alerts = derive(
            services=[
                service("navidrome", probe={"status": "unverified", "source": "docker"})
            ]
        )
        self.assertEqual(alerts, [])

    def test_certificate_days_are_positive_while_valid(self) -> None:
        """A future expiry must not collapse to 0 d and page someone."""
        self.assertEqual(snapshot._days(NOW, NOW + 30 * 86400), 30.0)
        self.assertAlmostEqual(snapshot._days(NOW, NOW + 6 * 3600), 0.25)
        self.assertEqual(snapshot._days(NOW, NOW - 86400), -1.0)
        self.assertIsNone(snapshot._days(NOW, None))

    def test_network_joins_both_probe_jobs(self) -> None:
        routes = {
            "private": [
                {
                    "exposure": "private",
                    "host": "files.h.malice.biz",
                    "upstream": "filebrowser:80",
                }
            ],
            "public": [
                {
                    "exposure": "public",
                    "host": "photos.malice.biz",
                    "upstream": "10.44.0.2:2283",
                }
            ],
        }
        infra = {
            "http_probes": [
                {
                    "instance": "https://files.h.malice.biz",
                    "success": True,
                    "duration": 0.012,
                    "code": 200,
                    "expires_ts": NOW + 60 * 86400,
                },
                {
                    "instance": "https://photos.malice.biz",
                    "success": True,
                    "duration": 0.1,
                    "code": 200,
                    "expires_ts": NOW + 60 * 86400,
                },
            ]
        }
        network = snapshot._network_section(
            CONFIG, routes, infra, {"available": True, "peers": []}, NOW
        )
        by_host = {row["host"]: row for row in network["routes"]}
        self.assertEqual(by_host["files.h.malice.biz"]["status"], "ok")
        self.assertEqual(by_host["files.h.malice.biz"]["latency_ms"], 12.0)
        self.assertEqual(by_host["files.h.malice.biz"]["tls_days"], 60.0)
        self.assertEqual(by_host["photos.malice.biz"]["code"], 200)
        # No series yet (first scrape after a deploy): unknown, not fail.
        network = snapshot._network_section(
            CONFIG, routes, {"http_probes": []}, {"available": True, "peers": []}, NOW
        )
        self.assertEqual({row["status"] for row in network["routes"]}, {"unknown"})

    def test_integration_errors_are_warn(self) -> None:
        media = {
            "jellyfin": {"configured": True, "error": "session: timeout"},
            "requests": {"configured": False, "error": None},
        }
        pipeline = {
            "prowlarr": {"configured": True, "error": "timeout", "errors": ["Indexer down"], "warnings": ["update"]},
            "sonarr": {
                "configured": True,
                "error": None,
                "errors": [],
                "warnings": [],
                "queue": {"total": 1, "stalled": [{"title": "Andor.S02E03"}]},
            },
        }
        alerts = by_id(derive(media=media, pipeline=pipeline))
        self.assertEqual({alert["severity"] for alert in alerts.values()}, {"warn"})
        self.assertIn("integration:jellyfin", alerts)
        self.assertIn("integration:prowlarr", alerts)
        # Health notices and queue rows stay in the media panels: the top
        # strip is reserved for urgent/important state.
        self.assertNotIn("arr-error:prowlarr:Indexer down", alerts)
        self.assertNotIn("arr-warn:prowlarr:update", alerts)
        self.assertNotIn("queue:sonarr:Andor.S02E03", alerts)

    def test_unconfigured_integrations_are_muted(self) -> None:
        alerts = derive(
            media={
                "jellyfin": {"configured": False, "error": None},
                "requests": {"configured": False, "error": None},
            },
            pipeline={
                "prowlarr": {"configured": False, "error": None},
                "sonarr": {"configured": False, "error": None},
                "radarr": {"configured": False, "error": None},
            },
        )
        self.assertEqual(alerts, [])

    def test_prometheus_down_is_hard(self) -> None:
        alerts = by_id(derive(errors={"prometheus": "connection refused"}))
        self.assertEqual(alerts["prometheus-unreachable"]["severity"], "alert")


if __name__ == "__main__":
    unittest.main()
