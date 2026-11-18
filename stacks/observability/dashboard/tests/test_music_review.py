"""Read-only status parsing for the daily music import pass."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from collectors import Collectors
from config import Settings, load_config


class MusicReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.collectors = Collectors(
            Settings(stacks_root=str(self.root)), load_config()
        )
        self.path = self.root / "observability" / "state" / "music-review.json"

    def write(self, payload: object) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_status_is_not_available(self) -> None:
        result = self.collectors._fetch_music_review()
        self.assertFalse(result["available"])
        self.assertIsNone(result["error"])

    def test_counts_are_normalized(self) -> None:
        self.write(
            {
                "generated_at": "2026-11-18T06:15:00+00:00",
                "generated_ts": 1_800_000_000,
                "needs_review": "3",
                "needs_input": 2,
                "errors": 1,
                "imported": 4,
                "job_url": "https://wrtag.h.malice.biz",
            }
        )
        result = self.collectors._fetch_music_review()
        self.assertTrue(result["available"])
        self.assertEqual(result["needs_review"], 3)
        self.assertEqual(result["needs_input"], 2)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["imported"], 4)
        self.assertEqual(result["job_url"], "https://wrtag.h.malice.biz")

    def test_invalid_status_is_reported(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        result = self.collectors._fetch_music_review()
        self.assertFalse(result["available"])
        self.assertTrue(result["error"])

    def test_non_https_job_url_is_dropped(self) -> None:
        self.write({"job_url": "javascript:alert(1)", "needs_review": 0})
        result = self.collectors._fetch_music_review()
        self.assertIsNone(result["job_url"])


if __name__ == "__main__":
    unittest.main()
