from __future__ import annotations

import io
import json
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

import smoke_gh_address_review_threads as smoke  # type: ignore  # noqa: E402
from review_thread_test_support import context_with_threads, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


class SmokeGhAddressReviewThreadsTests(unittest.TestCase):
    def test_main_runs_self_contained_synthetic_smoke_without_gh(self) -> None:
        with patch.object(sys, "argv", ["smoke_gh_address_review_threads.py", "--synthetic"]):
            with patch.object(smoke, "ensure_gh_auth", side_effect=AssertionError("live gh auth should not run")), patch.object(
                smoke,
                "current_branch_pr",
                side_effect=AssertionError("live pr lookup should not run"),
            ):
                buffer = io.StringIO()
                with patch("sys.stdout", buffer):
                    self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["reason"])
        self.assertEqual(payload["next_action"], "review_smoke_results")
        self.assertEqual(payload["thread_counts"]["unresolved"], 2)
        self.assertTrue(payload["common_path_sufficient"])
        self.assertGreater(payload["estimated_delegation_savings"], 0)

    def test_main_reports_blocked_schema_when_gh_cli_is_missing(self) -> None:
        with patch.object(sys, "argv", ["smoke_gh_address_review_threads.py"]):
            with patch.object(smoke, "ensure_gh_auth", side_effect=smoke.GhCliMissing("gh missing")):
                buffer = io.StringIO()
                with patch("sys.stdout", buffer):
                    self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(set(payload.keys()), {"status", "reason", "thread_counts", "next_action"})
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason"], "gh_cli_missing")
        self.assertEqual(payload["next_action"], "install_gh_cli")

    def test_main_reports_blocked_schema_when_no_open_pr(self) -> None:
        with patch.object(sys, "argv", ["smoke_gh_address_review_threads.py"]):
            with patch.object(smoke, "ensure_gh_auth", return_value=True), patch.object(smoke, "current_branch_pr", return_value=None):
                buffer = io.StringIO()
                with patch("sys.stdout", buffer):
                    self.assertEqual(smoke.main(), 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(set(payload.keys()), {"status", "reason", "thread_counts", "next_action"})
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["reason"], "no_open_pr")
        self.assertEqual(payload["next_action"], "open_pr_for_current_branch")

    def test_main_runs_safe_skip_defer_smoke_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            repo_holder = tmp_dir / "repo-holder"
            repo_holder.mkdir()
            context = context_with_threads(
                tmp_dir,
                [
                    review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this."),
                    review_thread(thread_id="t-2", path="src/helper.py", line=20, reviewer_login="reviewer-b", reviewer_body="Please add a test."),
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)

            def fake_run_script(args: list[str], *, cwd: Path) -> str:
                arg_list = [str(item) for item in args]
                if arg_list[0].endswith("collect_review_threads.py"):
                    write_json(Path(arg_list[arg_list.index("--output") + 1]), context)
                    return ""
                if arg_list[0].endswith("build_review_packets.py"):
                    output_dir = Path(arg_list[arg_list.index("--output-dir") + 1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    write_json(
                        output_dir / "orchestrator.json",
                        {
                            "review_mode": "targeted-delegation",
                            "recommended_worker_count": 1,
                            "recommended_workers": [{"agent_type": "packet_explorer"}],
                            "packet_files": ["global_packet.json", "thread-01.json", "thread-02.json", "orchestrator.json"],
                        },
                    )
                    write_json(output_dir / "global_packet.json", {"orchestrator_profile": "standard"})
                    write_json(
                        output_dir / "packet_metrics.json",
                        {
                            "packet_count": 4,
                            "packet_size_bytes": 1200,
                            "largest_packet_bytes": 500,
                            "largest_two_packets_bytes": 900,
                            "estimated_local_only_tokens": 600,
                            "estimated_packet_tokens": 250,
                            "estimated_delegation_savings": 350,
                        },
                    )
                    write_json(
                        Path(arg_list[arg_list.index("--result-output") + 1]),
                        {
                            "review_mode": "targeted-delegation",
                            "recommended_worker_count": 1,
                            "recommended_workers": [{"agent_type": "packet_explorer"}],
                            "thread_batch_count": 0,
                            "singleton_thread_packet_count": 2,
                            "active_paths": ["src/app.py", "src/helper.py"],
                            "override_signals": [],
                            "common_path_sufficient": True,
                            "common_path_failures": [],
                            "thread_counts": {"unresolved": 2, "unresolved_outdated": 0},
                            "packet_metrics_file": str(output_dir / "packet_metrics.json"),
                        },
                    )
                    return ""
                if "write_evaluation_log.py" in arg_list[0] and "init" in arg_list:
                    write_json(Path(arg_list[arg_list.index("--output") + 1]), {"skill": {"name": "gh-address-review-threads"}})
                    return ""
                if "validate_thread_action_plan.py" in arg_list[0]:
                    write_json(
                        Path(arg_list[arg_list.index("--output") + 1]),
                        {
                            "phase": arg_list[arg_list.index("--phase") + 1],
                            "valid": True,
                            "context_fingerprint": context["context_fingerprint"],
                            "normalized_thread_actions": [],
                            "counters": {},
                        },
                    )
                    return ""
                if "apply_thread_action_plan.py" in arg_list[0]:
                    write_json(
                        Path(arg_list[arg_list.index("--result-output") + 1]),
                        {
                            "dry_run": True,
                            "apply_succeeded": True,
                            "fingerprint_match": True,
                            "counters": {},
                            "mutations": [],
                        },
                    )
                    return ""
                return ""

            argv = ["smoke_gh_address_review_threads.py", "--repo-root", str(repo_holder)]
            with patch.object(sys, "argv", argv):
                with patch.object(smoke, "ensure_gh_auth", return_value=True), patch.object(
                    smoke,
                    "current_branch_pr",
                    return_value={"number": 11, "url": "https://example.invalid/pr/11"},
                ), patch.object(smoke, "run_script", side_effect=fake_run_script):
                    buffer = io.StringIO()
                    with patch("sys.stdout", buffer):
                        self.assertEqual(smoke.main(), 0)

            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertIsNone(payload["reason"])
            self.assertEqual(payload["thread_counts"]["unresolved"], 2)
            self.assertEqual(payload["next_action"], "review_smoke_results")
            self.assertTrue(payload["common_path_sufficient"])
            self.assertGreater(payload["estimated_delegation_savings"], 0)

    def test_main_reports_noop_schema_when_no_unresolved_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            repo_holder = tmp_dir / "repo-holder"
            repo_holder.mkdir()
            context = context_with_threads(tmp_dir, [])
            context["context_fingerprint"] = build_context_fingerprint(context)

            def fake_run_script(args: list[str], *, cwd: Path) -> str:
                arg_list = [str(item) for item in args]
                if arg_list[0].endswith("collect_review_threads.py"):
                    write_json(Path(arg_list[arg_list.index("--output") + 1]), context)
                return ""

            argv = ["smoke_gh_address_review_threads.py", "--repo-root", str(repo_holder)]
            with patch.object(sys, "argv", argv):
                with patch.object(smoke, "ensure_gh_auth", return_value=True), patch.object(
                    smoke,
                    "current_branch_pr",
                    return_value={"number": 11, "url": "https://example.invalid/pr/11"},
                ), patch.object(smoke, "run_script", side_effect=fake_run_script):
                    buffer = io.StringIO()
                    with patch("sys.stdout", buffer):
                        self.assertEqual(smoke.main(), 0)

            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "noop")
            self.assertEqual(payload["reason"], "no_unresolved_threads")
            self.assertEqual(set(payload.keys()) & {"status", "reason", "thread_counts", "next_action"}, {"status", "reason", "thread_counts", "next_action"})


if __name__ == "__main__":
    unittest.main()
