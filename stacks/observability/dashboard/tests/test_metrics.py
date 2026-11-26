"""Application/queue evidence must fail closed without scrape-time network I/O."""

from __future__ import annotations

import copy
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app
import clients
import metrics
import snapshot as snapshot_module
from collectors import Collectors
from config import Settings, load_config


def page(number: int, total: int, records: list[dict]) -> dict:
    return {"page": number, "pageSize": 50, "totalRecords": total, "records": records}


def queue_row(identifier: int | str, state: str = "importBlocked") -> dict:
    return {"id": identifier, "trackedDownloadState": state, "title": "PRIVATE TITLE", "statusMessages": ["PRIVATE MESSAGE"]}


def snapshots() -> tuple[dict, dict]:
    entries = {}
    for name in metrics.APPS:
        entry = {"configured": True, "error": None, "health_checked_at": 1000, "status_payload": {"version": "1.2.3"}}
        if name in metrics.ARR_APPS:
            entry.update(health_payload=[], queue_payload={"records": [], "totalRecords": 0}, queue_success=True, queue_checked_at=1000)
        if name == "bazarr":
            entry["status_payload"] = {"data": {"bazarr_version": "1.6.2"}}
        if name == "navidrome":
            entry["status_payload"] = True
        entries[name] = entry
    by_key = {
        ("edge/caddy" if name == "caddy" else f"media/{name}"): {"state": "running", "health": "healthy" if name == "caddy" else None}
        for name in metrics.APPS
    }
    return (
        {"data": entries, "error": None, "updated_timestamp_seconds": 1000},
        {"data": {"by_key": by_key}, "error": None, "updated_timestamp_seconds": 1000},
    )


class ArrPaginationTests(unittest.TestCase):
    def client(self, pages: list[object]) -> clients.Arr:
        client = clients.Arr("sonarr", "http://unused", "unused")
        client._get = Mock(side_effect=pages)
        return client

    def test_fetches_all_121_records_preserving_both_apps_include_flags(self) -> None:
        rows = [queue_row(n) for n in range(121)]
        for kind, flags in (
            ("sonarr", "includeUnknownSeriesItems=true&includeSeries=true"),
            ("radarr", "includeUnknownMovieItems=true&includeMovie=true"),
        ):
            with self.subTest(kind=kind):
                client = self.client([page(1, 121, rows[:50]), page(2, 121, rows[50:100]), page(3, 121, rows[100:])])
                result = client.queue(kind)
                self.assertEqual(result["records"], rows)
                self.assertEqual(result["totalRecords"], 121)
                self.assertEqual([call.args[0] for call in client._get.call_args_list], [f"/queue?page={n}&pageSize=50&{flags}" for n in range(1, 4)])

    def test_empty_queue_is_complete(self) -> None:
        self.assertEqual(self.client([page(1, 0, [])]).queue("sonarr")["records"], [])

    def test_rejects_malformed_incomplete_and_repeated_pages(self) -> None:
        first = [queue_row(n) for n in range(50)]
        cases = [
            [None], [{}], [page(1, "0", [])], [page(1, True, [])],
            [page(1, -1, [])], [page(1, 100001, [])],
            [{**page(1, 0, []), "pageSize": 20}],
            [page(2, 0, [])], [page(1, 1, [])],
            [page(1, 1, [None])], [page(1, 1, [{}])],
            [page(1, 1, [{"id": True}])],
            [page(1, 1, [{"id": 1, "trackedDownloadState": []}])],
            [page(1, 2, [queue_row(1), queue_row(1)])],
            [page(1, 51, first), page(2, 51, [])],
            [page(1, 51, first), page(2, 52, [queue_row(50)])],
            [page(1, 51, first), page(1, 51, first)],
            [page(1, 51, first), page(2, 51, [queue_row(0)])],
        ]
        for payloads in cases:
            with self.subTest(payloads=payloads), self.assertRaises(clients.ClientError):
                self.client(payloads).queue("sonarr")

    def test_queue_has_whole_collection_deadline(self) -> None:
        client = self.client([page(1, 0, [])])
        with patch("clients.time.monotonic", side_effect=[0, 1, 31]), self.assertRaises(clients.ClientError):
            client.queue("sonarr")


class ResponseShapeTests(unittest.TestCase):
    def test_seerr_and_arr_require_version_not_arbitrary_json(self) -> None:
        for client in (clients.Seerr("http://unused", "secret"), clients.Arr("radarr", "http://unused", "secret")):
            for payload in (None, [], {}, {"version": None}, {"version": ""}, {"version": " "}):
                with self.subTest(client=type(client).__name__, payload=payload), patch.object(client, "_get", return_value=payload), self.assertRaises(clients.ClientError):
                    client.status()
            with patch.object(client, "_get", return_value={"version": "1.0"}):
                self.assertEqual(client.status(), {"version": "1.0"})

    def test_arr_health_requires_array_with_typed_entries(self) -> None:
        client = clients.Arr("radarr", "http://unused", "secret")
        for payload in ({}, [None], [{}], [{"type": None}]):
            with patch.object(client, "_get", return_value=payload), self.assertRaises(clients.ClientError):
                client.health()
        with patch.object(client, "_get", return_value=[]):
            self.assertEqual(client.health(), [])

    def test_bazarr_uses_header_and_confirmed_data_envelope(self) -> None:
        client = clients.Bazarr("http://bazarr:6767/", "secret")
        with patch("clients.http_json", return_value={"data": {"bazarr_version": "1.6.2"}}) as get:
            self.assertTrue(client.status())
            get.assert_called_once_with("http://bazarr:6767/api/system/status", headers={"X-API-KEY": "secret", "Accept": "application/json"}, timeout=8.0)
        for payload in ({"version": "1.6.2"}, {"data": {}}, "login"):
            with patch("clients.http_json", return_value=payload), self.assertRaises(clients.ClientError):
                client.status()

    def test_navidrome_requires_exact_ping_not_login_page(self) -> None:
        client = clients.Navidrome("http://navidrome:4533")
        for body in (b".", b"<html>login</html>", b"", b"{}"):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = body
            with patch("clients.urllib.request.urlopen", return_value=response):
                if body == b".":
                    self.assertTrue(client.ping())
                else:
                    with self.assertRaises(clients.ClientError):
                        client.ping()

    def test_bazarr_settings_and_redaction_follow_existing_integrations(self) -> None:
        settings = Settings.from_env({"BAZARR_API_KEY": "private-bazarr-key", "BAZARR_URL": "http://custom:6767", "NAVIDROME_URL": "http://custom:4533"})
        self.assertTrue(settings.integration("bazarr").configured)
        self.assertEqual(settings.integration("bazarr").url, "http://custom:6767")
        self.assertIn("private-bazarr-key", settings.secrets)
        self.assertEqual(settings.navidrome_url, "http://custom:4533")
        self.assertFalse(Settings.from_env({}).integration("bazarr").configured)


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.integrations, self.containers = snapshots()

    def render(self, now: float = 1001) -> str:
        return metrics.render(self.integrations, self.containers, now)

    def test_all_expected_labels_and_real_zero_issue_counts(self) -> None:
        text = self.render()
        for name in metrics.APPS:
            self.assertIn(f'homelab_app_healthy{{app="{name}"}} 1\n', text)
            self.assertIn(f'homelab_app_check_timestamp_seconds{{app="{name}"}} 1000\n', text)
        for name in metrics.ARR_APPS:
            self.assertIn(f'homelab_arr_queue_check_success{{app="{name}"}} 1\n', text)
            self.assertIn(f'homelab_arr_health_issues{{app="{name}"}} 0\n', text)

    def test_only_two_qualifying_states_without_private_metadata(self) -> None:
        entry = self.integrations["data"]["sonarr"]
        rows = [queue_row(n, state) for n, state in enumerate(("importBlocked", "IMPORTPENDING", "downloading", "completed", "failed", "importBlockedOther"))]
        entry["queue_payload"] = {"records": rows, "totalRecords": len(rows)}
        text = self.render()
        self.assertEqual(text.count("homelab_arr_queue_import_blocked{"), 2)
        self.assertIn('homelab_arr_queue_import_blocked{app="sonarr",queue_id="0"} 1\n', text)
        self.assertIn('homelab_arr_queue_import_blocked{app="sonarr",queue_id="1"} 1\n', text)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("title", text)
        self.assertNotIn("statusMessages", text)

    def test_queue_identifier_labels_are_escaped(self) -> None:
        self.integrations["data"]["sonarr"]["queue_payload"] = {"records": [queue_row('id"\\\nnext')], "totalRecords": 1}
        self.assertIn('queue_id="id\\"\\\\\\nnext"', self.render())

    def test_missing_credentials_or_malformed_status_is_unhealthy(self) -> None:
        for app_name in ("jellyseerr", "radarr", "sonarr", "bazarr", "navidrome"):
            for change in ({"configured": False}, {"error": "HTTP 401"}, {"status_payload": {}}):
                with self.subTest(app=app_name, change=change):
                    integrations = copy.deepcopy(self.integrations)
                    integrations["data"][app_name].update(change)
                    text = metrics.render(integrations, self.containers, 1001)
                    self.assertIn(f'homelab_app_healthy{{app="{app_name}"}} 0\n', text)

    def test_absent_stopped_starting_and_unhealthy_containers_fail(self) -> None:
        for name in metrics.APPS:
            key = "edge/caddy" if name == "caddy" else f"media/{name}"
            for row in ({}, {"state": "exited"}, {"state": "running", "health": "unhealthy"}, {"state": "running", "health": "starting"}):
                with self.subTest(app=name, row=row):
                    containers = copy.deepcopy(self.containers)
                    containers["data"]["by_key"][key] = row
                    text = metrics.render(self.integrations, containers, 1001)
                    self.assertIn(f'homelab_app_healthy{{app="{name}"}} 0\n', text)
        self.containers["data"]["by_key"]["edge/caddy"] = {"state": "running", "health": None}
        self.assertIn('homelab_app_healthy{app="caddy"} 0\n', self.render())

    def test_failed_or_stale_retained_stores_never_claim_success(self) -> None:
        entry = self.integrations["data"]["sonarr"]
        entry["queue_payload"] = {"records": [queue_row(1)], "totalRecords": 1}
        for store_name in ("integrations", "containers"):
            for change in ({"error": "refresh failed"}, {"updated_timestamp_seconds": 600}, {"updated_timestamp_seconds": 1100}):
                with self.subTest(store=store_name, change=change):
                    integrations, containers = copy.deepcopy((self.integrations, self.containers))
                    (integrations if store_name == "integrations" else containers).update(change)
                    text = metrics.render(integrations, containers, 1001)
                    self.assertIn('homelab_app_healthy{app="sonarr"} 0\n', text)
                    self.assertIn('homelab_arr_queue_check_success{app="sonarr"} 0\n', text)
                    self.assertNotIn("homelab_arr_queue_import_blocked{", text)
                    self.assertNotIn("homelab_arr_health_issues{", text)

    def test_failed_stale_or_incomplete_queue_omits_all_items(self) -> None:
        for change in (
            {"queue_success": False}, {"queue_checked_at": 600},
            {"queue_payload": {"records": [queue_row(1)], "totalRecords": 2}},
            {"queue_payload": {"records": [queue_row(1), queue_row(1)], "totalRecords": 2}},
        ):
            with self.subTest(change=change):
                integrations = copy.deepcopy(self.integrations)
                entry = integrations["data"]["sonarr"]
                entry["queue_payload"] = {"records": [queue_row(1)], "totalRecords": 1}
                entry.update(change)
                text = metrics.render(integrations, self.containers, 1001)
                self.assertIn('homelab_arr_queue_check_success{app="sonarr"} 0\n', text)
                self.assertNotIn("homelab_arr_queue_import_blocked{", text)

    def test_individual_health_check_age_is_not_group_completion_age(self) -> None:
        self.integrations["data"]["sonarr"]["health_checked_at"] = 600
        self.assertIn('homelab_app_healthy{app="sonarr"} 0\n', self.render())
        self.assertNotIn('homelab_arr_health_issues{app="sonarr"}', self.render())

    def test_health_issue_count_includes_only_warning_and_error(self) -> None:
        self.integrations["data"]["radarr"]["health_payload"] = [{"type": value} for value in ("warning", "Error", "ok", "notice")]
        self.assertIn('homelab_arr_health_issues{app="radarr"} 2\n', self.render())

    def test_empty_and_expired_cache_is_failed_and_timestamps_do_not_advance(self) -> None:
        text = metrics.render({"data": None}, {"data": None}, 1001)
        for name in metrics.APPS:
            self.assertIn(f'homelab_app_healthy{{app="{name}"}} 0\n', text)
            self.assertIn(f'homelab_app_check_timestamp_seconds{{app="{name}"}} 0\n', text)
        expired = self.render(now=1301)
        self.assertNotIn('} 1\n', expired)
        self.assertIn('homelab_app_check_timestamp_seconds{app="sonarr"} 1000\n', expired)

    def test_render_does_not_mutate_inputs(self) -> None:
        original = copy.deepcopy((self.integrations, self.containers))
        self.render()
        self.assertEqual((self.integrations, self.containers), original)


class CollectorMetricsTests(unittest.TestCase):
    def collectors(self) -> Collectors:
        collector = Collectors(Settings.from_env({}), load_config())
        collector.jellyfin = Mock(configured=False)
        collector.prowlarr = Mock(configured=False)
        collector.seerr = Mock(configured=True)
        collector.seerr.status.return_value = {"version": "3.5.2"}
        collector.seerr.requests.return_value = {"results": []}
        collector._seerr_titles = Mock(return_value={})
        for name in metrics.ARR_APPS:
            client = Mock(configured=True)
            client.status.return_value = {"version": "1"}
            client.health.return_value = []
            client.queue.return_value = {"records": [queue_row(1)], "totalRecords": 1}
            setattr(collector, name, client)
        collector.bazarr = Mock(configured=True)
        collector.bazarr.status.return_value = {"data": {"bazarr_version": "1.6.2"}}
        collector.navidrome = Mock()
        collector.navidrome.ping.return_value = True
        return collector

    def test_failed_refresh_replaces_queue_payload_not_retains_success(self) -> None:
        collector = self.collectors()
        first = collector._fetch_integrations()
        self.assertTrue(first["sonarr"]["queue_success"])
        collector.sonarr.queue.side_effect = clients.ClientError("HTTP 503")
        second = collector._fetch_integrations()
        self.assertFalse(second["sonarr"]["queue_success"])
        self.assertNotIn("queue_payload", second["sonarr"])
        self.assertIsNotNone(second["sonarr"]["error"])
        self.assertGreater(second["sonarr"]["queue_checked_at"], 0)

    def test_unconfigured_apps_are_stamped_without_network_calls(self) -> None:
        collector = self.collectors()
        collector.sonarr.configured = False
        collector.seerr.configured = False
        collector.bazarr.configured = False
        data = collector._fetch_integrations()
        for name in ("sonarr", "jellyseerr", "bazarr"):
            self.assertFalse(data[name]["configured"])
            self.assertGreater(data[name]["health_checked_at"], 0)
        collector.sonarr.status.assert_not_called()
        collector.sonarr.queue.assert_not_called()
        collector.seerr.status.assert_not_called()
        collector.bazarr.status.assert_not_called()

    def test_api_failure_does_not_reuse_previous_health_payload(self) -> None:
        collector = self.collectors()
        self.assertIn("status_payload", collector._fetch_integrations()["bazarr"])
        collector.bazarr.status.side_effect = clients.ClientError("invalid JSON")
        failed = collector._fetch_integrations()["bazarr"]
        self.assertNotIn("status_payload", failed)
        self.assertEqual(failed["error"], "invalid JSON")

    def test_store_failure_invalidates_retained_values(self) -> None:
        collector = self.collectors()
        integrations, containers = snapshots()
        with patch("collectors.time.time", return_value=1000):
            collector.integrations.set_ok(integrations["data"])
            collector.containers.set_ok(containers["data"])
        collector.integrations.set_error("failed")
        self.assertIn('homelab_app_healthy{app="sonarr"} 0\n', collector.render_metrics(now=1001))
        self.assertEqual(collector.integrations.snapshot()["updated_timestamp_seconds"], 1000)

    def test_metrics_handler_reads_cache_only(self) -> None:
        collector = self.collectors()
        collector._fetch_integrations = Mock(side_effect=AssertionError("scrape attempted network"))
        collector._fetch_docker = Mock(side_effect=AssertionError("scrape attempted Docker"))
        handler = object.__new__(app.Handler)
        handler.server = SimpleNamespace(collectors=collector)
        handler.path = "/metrics"
        handler.wfile = io.BytesIO()
        handler._headers = Mock()
        handler.do_GET()
        self.assertIn(b'homelab_app_healthy{app="sonarr"} 0\n', handler.wfile.getvalue())
        handler._headers.assert_called_once()
        self.assertIn("text/plain; version=0.0.4", handler._headers.call_args.args[1])
        collector._fetch_integrations.assert_not_called()
        collector._fetch_docker.assert_not_called()

    def test_failed_integration_store_hides_stale_queue_items(self) -> None:
        collector = self.collectors()
        collector.integrations.set_ok(collector._fetch_integrations())
        collector.integrations.set_error("refresh failed")
        payload = snapshot_module.build_snapshot(
            collector, collector.config, collector.settings, now=1001
        )
        for name in ("sonarr", "radarr"):
            with self.subTest(app=name):
                entry = payload["pipeline"][name]
                self.assertEqual(entry["error"], "refresh failed")
                self.assertNotIn("queue", entry)


if __name__ == "__main__":
    unittest.main()
