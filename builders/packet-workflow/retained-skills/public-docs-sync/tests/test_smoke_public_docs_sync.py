from __future__ import annotations

import io
import json
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

import smoke_public_docs_sync as smoke  # noqa: E402


class SmokePublicDocsSyncTests(unittest.TestCase):
    def test_resolve_python_bin_skips_windowsapps_shims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            shim = tmp_dir / "Microsoft" / "WindowsApps" / "python.exe"
            concrete = tmp_dir / "Python312" / "python.exe"
            shim.parent.mkdir(parents=True, exist_ok=True)
            concrete.parent.mkdir(parents=True, exist_ok=True)
            shim.write_text("", encoding="utf-8")
            concrete.write_text("", encoding="utf-8")

            with patch.object(smoke, "python_bin_candidates", return_value=[shim, concrete]):
                self.assertEqual(smoke.resolve_python_bin(), str(concrete))

    def test_run_python_uses_python_builder(self) -> None:
        completed = subprocess.CompletedProcess(["python"], 0, "{}", "")

        with (
            patch.object(smoke, "build_python_command", return_value=["C:/Python312/python.exe", "-B", "driver.py", "--flag"]),
            patch.object(smoke.subprocess, "run", return_value=completed) as run_mock,
        ):
            result = smoke.run_python(["driver.py", "--flag"], cwd=Path("C:/repo"))

        self.assertIs(result, completed)
        self.assertEqual(run_mock.call_args.args[0], ["C:/Python312/python.exe", "-B", "driver.py", "--flag"])

    def test_main_uses_stable_collect_entrypoint(self) -> None:
        calls: list[list[str]] = []

        def fake_run_python(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            raise RuntimeError("stop-after-collect")

        with patch.object(smoke, "run_python", side_effect=fake_run_python):
            with self.assertRaisesRegex(RuntimeError, "stop-after-collect"):
                smoke.main()

        self.assertEqual(calls[0][0], str(smoke.script_path("collect_public_docs_sync_context.py")))

    def test_success_output_reports_smoke_passed(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["smoke"], "passed")
        self.assertGreater(payload["packet_compaction_savings_tokens"], 0)
        self.assertEqual(payload["raw_reread_count"], 0)
        self.assertTrue(payload["common_path_sufficient"])


if __name__ == "__main__":
    unittest.main()
