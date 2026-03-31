from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import smoke_weekly_update as smoke  # noqa: E402


class SmokeWeeklyUpdateTests(unittest.TestCase):
    def test_explicit_non_repo_root_returns_blocked_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            argv = ["smoke_weekly_update.py", "--repo-root", str(tmp_dir)]
            with patch.object(sys, "argv", argv):
                buffer = io.StringIO()
                with patch("sys.stdout", buffer):
                    self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason"], "git_repo_required")
        self.assertEqual(payload["next_action"], "run_from_repo_or_pass_repo_root")
        self.assertEqual(payload["repo_root"], str(tmp_dir.resolve()))

    def test_repo_root_path_returns_none_when_cwd_is_not_in_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            previous = Path.cwd()
            os.chdir(tmp_dir)
            try:
                self.assertIsNone(smoke.repo_root_path(None))
            finally:
                os.chdir(previous)

    def test_smoke_uses_collect_default_profile_when_not_explicit(self) -> None:
        repo_root = Path("C:/repo")
        calls: list[list[str]] = []

        def fail_after_collect(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            raise RuntimeError("stop-after-collect")

        argv = ["smoke_weekly_update.py", "--repo-root", str(repo_root)]
        with (
            patch.object(sys, "argv", argv),
            patch.object(smoke, "repo_root_path", return_value=repo_root),
            patch.object(smoke, "run_script", side_effect=fail_after_collect),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop-after-collect"):
                smoke.main()

        collect_args = calls[0]
        self.assertEqual(collect_args[0], str(smoke.script_path("collect_weekly_update_context.py")))
        self.assertNotIn("--profile", collect_args)

    def test_smoke_forwards_explicit_profile_to_collect_wrapper(self) -> None:
        repo_root = Path("C:/repo")
        profile_path = "C:/profiles/weekly-update.json"
        calls: list[list[str]] = []

        def fail_after_collect(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            raise RuntimeError("stop-after-collect")

        argv = [
            "smoke_weekly_update.py",
            "--repo-root",
            str(repo_root),
            "--profile",
            profile_path,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(smoke, "repo_root_path", return_value=repo_root),
            patch.object(smoke, "run_script", side_effect=fail_after_collect),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop-after-collect"):
                smoke.main()

        collect_args = calls[0]
        profile_index = collect_args.index("--profile")
        self.assertEqual(collect_args[profile_index + 1], profile_path)


if __name__ == "__main__":
    unittest.main()
