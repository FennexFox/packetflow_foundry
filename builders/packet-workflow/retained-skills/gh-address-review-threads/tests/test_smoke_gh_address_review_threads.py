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
from review_thread_test_support import comment, context_with_threads, reply_candidate, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


class SmokeGhAddressReviewThreadsTests(unittest.TestCase):
    def test_build_safe_plan_updates_exact_ack_when_decision_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            context = context_with_threads(
                tmp_dir,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                        reply_candidates={
                            "ack": reply_candidate(
                                mode="update",
                                comment_id="self-1",
                                reason="exact_managed_reply",
                                managed=True,
                                adopted_unmarked_reply=False,
                            ),
                            "complete": reply_candidate(
                                mode="add",
                                comment_id=None,
                                reason="complete_never_adopts_unmarked_reply",
                                managed=False,
                                adopted_unmarked_reply=False,
                            ),
                        },
                        comments=[
                            comment(
                                comment_id="self-1",
                                author_login="codex",
                                body=(
                                    "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                                    "Reviewer asked to rename this.\n"
                                    "accept\n"
                                    "Will update the naming and rerun the relevant check."
                                ),
                                created_at="2026-03-01T00:05:00Z",
                                managed_phase="ack",
                                managed_thread_id="t-1",
                                has_exact_managed_marker=True,
                            )
                        ],
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)

            plan = smoke.build_safe_plan(context, phase="ack", accepted_thread_ids=[])

            self.assertEqual(plan["thread_actions"][0]["ack_mode"], "update")
            self.assertEqual(plan["thread_actions"][0]["ack_comment_id"], "self-1")
            self.assertEqual(plan["thread_actions"][0]["ack_body"], smoke.safe_ack_body(decision="defer"))

    def test_build_safe_plan_skips_exact_ack_when_decision_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            context = context_with_threads(
                tmp_dir,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                        reply_candidates={
                            "ack": reply_candidate(
                                mode="update",
                                comment_id="self-2",
                                reason="exact_managed_reply",
                                managed=True,
                                adopted_unmarked_reply=False,
                            ),
                            "complete": reply_candidate(
                                mode="add",
                                comment_id=None,
                                reason="complete_never_adopts_unmarked_reply",
                                managed=False,
                                adopted_unmarked_reply=False,
                            ),
                        },
                        comments=[
                            comment(
                                comment_id="self-2",
                                author_login="codex",
                                body=(
                                    "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                                    "Reviewer asked to rename this.\n"
                                    "defer\n"
                                    "Waiting for clearer grounding before changing behavior."
                                ),
                                created_at="2026-03-01T00:05:00Z",
                                managed_phase="ack",
                                managed_thread_id="t-1",
                                has_exact_managed_marker=True,
                            )
                        ],
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)

            plan = smoke.build_safe_plan(context, phase="ack", accepted_thread_ids=[])

            self.assertEqual(plan["thread_actions"][0]["ack_mode"], "skip")
            self.assertNotIn("ack_body", plan["thread_actions"][0])
            self.assertNotIn("ack_comment_id", plan["thread_actions"][0])

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
        self.assertGreaterEqual(payload["estimated_delegation_savings"], 0)
        self.assertEqual(payload["outdated_transition_candidates"], 1)
        self.assertEqual(payload["outdated_auto_resolved"], 1)
        self.assertEqual(payload["outdated_recheck_ambiguous"], 0)
        self.assertIn("run_id", payload)
        self.assertIn("manifest_path", payload)
        self.assertIn("run_root", payload)
        self.assertIn("evaluation_final_path", payload)

    def test_synthetic_run_smoke_workflow_completes_accepted_current_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            temp_dir = Path(tmp_dir_name)
            (
                repo_root,
                previous_context_path,
                context_path,
                accepted_thread_ids,
                validation_commands,
            ) = smoke.build_synthetic_context(temp_dir)

            payload = smoke.run_smoke_workflow(
                repo_root=repo_root,
                context_path=context_path,
                temp_dir=temp_dir,
                previous_context_path=previous_context_path,
                accepted_thread_ids=accepted_thread_ids,
                validation_commands=validation_commands,
            )

            manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
            complete_plan = json.loads(
                Path(manifest["paths"]["complete"]["validated_plan"]).read_text(encoding="utf-8")
            )
            normalized_actions = {
                action["thread_id"]: action for action in complete_plan["normalized_thread_actions"]
            }
            self.assertEqual(normalized_actions["t-1"]["decision"], "accept")
            self.assertTrue(normalized_actions["t-1"]["resolve_after_complete"])
            self.assertEqual(normalized_actions["t-2"]["decision"], "accept")
            self.assertTrue(normalized_actions["t-2"]["resolve_after_complete"])

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

    def test_main_runs_ack_reply_smoke_path_without_contract_bypass(self) -> None:
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

            real_run_script = smoke.run_script

            def fake_run_script(args: list[str], *, cwd: Path) -> str:
                arg_list = [str(item) for item in args]
                if arg_list[0].endswith("manage_review_thread_run.py"):
                    return real_run_script(args, cwd=cwd)
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
                            "outdated_transition_candidates": 0,
                            "outdated_recheck_ambiguous": 0,
                            "packet_metrics_file": str(output_dir / "packet_metrics.json"),
                        },
                    )
                    return ""
                if arg_list[0].endswith("reconcile_outdated_threads.py"):
                    write_json(
                        Path(arg_list[arg_list.index("--output") + 1]),
                        {
                            "context_fingerprint": context["context_fingerprint"],
                            "thread_actions": [],
                            "reconciliation_summary": {
                                "outdated_transition_candidates": 0,
                                "outdated_auto_resolved": 0,
                                "outdated_recheck_ambiguous": 0,
                                "outdated_still_applicable": 0,
                            },
                        },
                    )
                    return ""
                if "write_evaluation_log.py" in arg_list[0] and "init" in arg_list:
                    write_json(Path(arg_list[arg_list.index("--output") + 1]), {"skill": {"name": "gh-address-review-threads"}})
                    return ""
                if "validate_thread_action_plan.py" in arg_list[0]:
                    plan_path = Path(arg_list[arg_list.index("--plan") + 1])
                    plan_payload = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
                    write_json(
                        Path(arg_list[arg_list.index("--output") + 1]),
                        {
                            "phase": arg_list[arg_list.index("--phase") + 1],
                            "valid": True,
                            "context_fingerprint": context["context_fingerprint"],
                            "normalized_thread_actions": [],
                            "counters": {},
                            "reconciliation_summary": plan_payload.get("reconciliation_summary"),
                        },
                    )
                    return ""
                if "apply_thread_action_plan.py" in arg_list[0]:
                    plan_path = Path(arg_list[arg_list.index("--plan") + 1])
                    plan_payload = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
                    write_json(
                        Path(arg_list[arg_list.index("--result-output") + 1]),
                        {
                            "dry_run": True,
                            "apply_succeeded": True,
                            "fingerprint_match": True,
                            "counters": {},
                            "mutations": [],
                            "reconciliation_summary": plan_payload.get("reconciliation_summary"),
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
            self.assertEqual(payload["outdated_transition_candidates"], 0)
            self.assertEqual(payload["outdated_auto_resolved"], 0)
            self.assertEqual(payload["outdated_recheck_ambiguous"], 0)
            self.assertIn("run_id", payload)
            self.assertIn("manifest_path", payload)
            self.assertIn("evaluation_final_path", payload)
            manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"]["last_completed_phase"], "complete-applied")
            self.assertTrue(Path(payload["evaluation_final_path"]).is_file())
            finalized = json.loads(Path(payload["evaluation_final_path"]).read_text(encoding="utf-8"))
            self.assertEqual(finalized["quality"]["result_status"], "dry-run")

    def test_main_reports_noop_schema_when_no_unresolved_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            repo_holder = tmp_dir / "repo-holder"
            repo_holder.mkdir()
            context = context_with_threads(tmp_dir, [])
            context["context_fingerprint"] = build_context_fingerprint(context)

            real_run_script = smoke.run_script

            def fake_run_script(args: list[str], *, cwd: Path) -> str:
                arg_list = [str(item) for item in args]
                if arg_list[0].endswith("manage_review_thread_run.py"):
                    return real_run_script(args, cwd=cwd)
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
