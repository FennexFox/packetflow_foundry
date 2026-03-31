from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import collect_pr_context as collect_pr_context  # type: ignore  # noqa: E402


class CollectPrContextTests(unittest.TestCase):
    def test_main_stops_cleanly_when_build_context_raises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            profile_path = tmp / "profile.json"
            profile_path.write_text('{"name":"default","summary":"test"}\n', encoding="utf-8")
            stderr = io.StringIO()
            argv = [
                "collect_pr_context.py",
                "1",
                "--repo-root",
                str(tmp),
                "--profile",
                str(profile_path),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    collect_pr_context,
                    "build_context",
                    side_effect=RuntimeError("gh executable not found"),
                ),
                redirect_stderr(stderr),
            ):
                exit_code = collect_pr_context.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("collect_pr_context.py: gh executable not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
