from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import weekly_update_lib as wl


class WeeklyUpdatePaginationTests(unittest.TestCase):
    def test_paginate_gh_api_aggregates_pages_until_empty_page(self) -> None:
        responses = [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}],
        ]
        seen_paths: list[str] = []

        def fake_run_gh_json(repo_root: Path, args: list[str]) -> list[dict[str, int]]:
            seen_paths.append(args[-1])
            return responses.pop(0)

        with patch.object(wl, "run_gh_json", side_effect=fake_run_gh_json), patch.object(wl, "DEFAULT_PAGE_SIZE", 2):
            items, warnings = wl.paginate_gh_api(
                Path("C:/repo"),
                "repos/example/project/issues",
                params={"state": "all"},
                label="issues",
            )

        self.assertEqual([item["id"] for item in items], [1, 2, 3])
        self.assertEqual(warnings, [])
        self.assertEqual(len(seen_paths), 2)
        self.assertIn("per_page=2", seen_paths[0])
        self.assertIn("page=1", seen_paths[0])
        self.assertIn("page=2", seen_paths[1])

    def test_paginate_gh_api_reports_truncation_at_page_cap(self) -> None:
        def fake_run_gh_json(repo_root: Path, args: list[str]) -> list[dict[str, int]]:
            return [{"id": 1}]

        with patch.object(wl, "run_gh_json", side_effect=fake_run_gh_json) as mocked, patch.object(wl, "DEFAULT_PAGE_SIZE", 1):
            items, warnings = wl.paginate_gh_api(
                Path("C:/repo"),
                "repos/example/project/issues",
                max_pages=2,
                label="issues",
            )

        self.assertEqual([item["id"] for item in items], [1, 1])
        self.assertEqual(warnings, ["issues may be truncated after 2 pages."])
        self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
