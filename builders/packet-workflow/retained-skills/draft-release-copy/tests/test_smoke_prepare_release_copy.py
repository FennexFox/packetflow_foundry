from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import release_copy_plan_contract as contract  # noqa: E402
import smoke_prepare_release_copy as smoke  # noqa: E402


class SmokePrepareReleaseCopyTests(unittest.TestCase):
    def test_run_command_uses_python_builder_for_script_entrypoints(self) -> None:
        completed = subprocess.CompletedProcess(["python"], 0, "ok\n", "")

        with (
            patch.object(smoke, "build_python_command", return_value=["C:/Python312/python.exe", "-B", "driver.py", "--flag"]),
            patch.object(smoke.subprocess, "run", return_value=completed) as run_mock,
        ):
            output = smoke.run_command(["driver.py", "--flag"], cwd=Path("C:/repo"))

        self.assertEqual(output, "ok\n")
        self.assertEqual(run_mock.call_args.args[0], ["C:/Python312/python.exe", "-B", "driver.py", "--flag"])

    def test_build_smoke_plan_carries_review_mode_and_qa_gate_defaults(self) -> None:
        plan = smoke.build_smoke_plan(
            {"context_fingerprint": "sha256:context", "freshness_tuple": {"head_commit": "abc"}},
            {
                "plan_defaults": {
                    "context_fingerprint": "sha256:context",
                    "freshness_tuple": {"head_commit": "abc"},
                    "review_mode": "broad-delegation",
                    "qa_gate": {"qa_clear": False},
                    "draft_basis": {"synthesis_packet_fingerprint": "sha256:synthesis"},
                }
            },
            {"review_mode": "broad-delegation"},
        )

        self.assertEqual(plan["review_mode"], "broad-delegation")
        self.assertEqual(plan["qa_gate"], {"qa_clear": False})

    def test_main_uses_stable_collect_entrypoint(self) -> None:
        calls: list[list[str]] = []

        def fake_run_command(args: list[str], *, cwd: Path) -> str:
            calls.append(args)
            if args and Path(str(args[0])).suffix == ".py":
                raise RuntimeError("stop-after-collect")
            return ""

        with patch.object(smoke, "run_command", side_effect=fake_run_command):
            with self.assertRaisesRegex(RuntimeError, "stop-after-collect"):
                smoke.main()

        collect_args = next(args for args in calls if args and Path(str(args[0])).suffix == ".py")
        self.assertEqual(collect_args[0], str(smoke.script_path("collect_release_copy_context.py")))

    def test_success_output_uses_reference_schema(self) -> None:
        with patch.object(sys, "argv", ["smoke_prepare_release_copy.py"]):
            buffer = io.StringIO()
            with patch("sys.stdout", buffer):
                self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        for key in contract.SMOKE_OUTPUT_FIELDS:
            self.assertIn(key, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["reason"])
        self.assertEqual(payload["next_action"], "review_smoke_results")
        self.assertGreater(payload["packet_compaction_savings_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
