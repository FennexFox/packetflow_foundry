from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import refresh_weekly_update_live_fixture as refresh
import weekly_update_lib as wl
from test_weekly_update_contract import load_json, review_comments_by_pr


class RefreshWeeklyUpdateLiveFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = load_json("weekly_update_sample.json")

    def test_build_plan_fixtures_match_validator_shape(self) -> None:
        plans = refresh.build_plan_fixtures(
            context_id="weekly-update:20260327T120000Z",
            context_fingerprint="fixture-context-fingerprint",
            reporting_window={"start_utc": "2026-03-20T23:59:59Z", "end_utc": "2026-03-27T12:00:00Z"},
        )
        ready = plans["weekly_update_plan_ready.json"]
        self.assertEqual(ready["selected_packets"], ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"])
        self.assertEqual(list(ready["sections"].keys()), wl.OUTPUT_SECTIONS)
        self.assertEqual(plans["weekly_update_plan_low.json"]["overall_confidence"], "low")
        self.assertIn("unresolved_raw_reread_candidate_ids", plans["weekly_update_plan_reread.json"])

    def test_build_review_threads_groups_root_comments_with_replies(self) -> None:
        comments = review_comments_by_pr(self.sample)[107]
        threads = refresh.build_review_threads(107, comments)
        self.assertEqual(len(threads), 3)
        self.assertEqual(threads[0]["pr_number"], 107)
        self.assertEqual([comment["id"] for comment in threads[0]["comments"]], [2992368622, 2992368623])
        self.assertEqual([comment["id"] for comment in threads[1]["comments"]], [2992369000])
        self.assertEqual([comment["id"] for comment in threads[2]["comments"]], [2992369999])

    def test_fixture_state_marker_keeps_window_end_only_when_marker_is_reused(self) -> None:
        marker = {"window_end_utc": "2026-03-20T23:59:59Z", "completed_at_utc": "2026-03-21T00:00:00Z"}
        reporting_window = {"source": "state_marker", "start_utc": "2026-03-20T23:59:59Z"}
        self.assertEqual(refresh.fixture_state_marker(marker, reporting_window), {"window_end_utc": "2026-03-20T23:59:59Z"})
        self.assertIsNone(refresh.fixture_state_marker(marker, {"source": "last_7_days"}))

    def test_parse_args_leaves_profile_unset_until_repo_root_is_known(self) -> None:
        with patch.object(sys, "argv", ["refresh_weekly_update_live_fixture.py", "--repo-root", "C:/repo"]):
            args = refresh.parse_args()
        self.assertIsNone(args.profile)


if __name__ == "__main__":
    unittest.main()
