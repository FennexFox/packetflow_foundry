from __future__ import annotations

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

import build_review_packets as packets  # type: ignore  # noqa: E402
from review_thread_test_support import context_with_threads, marker_conflict, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


class BuildReviewPacketsTests(unittest.TestCase):
    def test_main_clusters_threads_and_routes_packet_explorer_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/app.py",
                    line=10,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please tighten naming.",
                ),
                review_thread(
                    thread_id="t-2",
                    path="src/app.py",
                    line=28,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please tighten naming!",
                ),
                review_thread(
                    thread_id="t-3",
                    path="src/helper.py",
                    line=4,
                    reviewer_login="reviewer-b",
                    reviewer_body="Please add a test for this edge case.",
                ),
                review_thread(
                    thread_id="t-4",
                    path="src/legacy.py",
                    line=2,
                    reviewer_login="reviewer-c",
                    reviewer_body="This is outdated now.",
                    is_outdated=True,
                ),
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(context_path, context)

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--repo-root",
                context["repo_root"],
                "--output-dir",
                str(output_dir),
                "--result-output",
                str(build_result_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(packets.main(), 0)

            orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
            global_packet = json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8"))
            batch_packet = json.loads((output_dir / "thread-batch-01.json").read_text(encoding="utf-8"))
            singleton_packet = json.loads((output_dir / "thread-03.json").read_text(encoding="utf-8"))
            outdated_packet = json.loads((output_dir / "thread-04.json").read_text(encoding="utf-8"))
            packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertEqual(orchestrator["review_mode"], "targeted-delegation")
            self.assertEqual(orchestrator["orchestrator_profile"], "standard")
            self.assertIn("common_path_contract", orchestrator)
            self.assertNotIn("estimated_packet_tokens", orchestrator)
            self.assertEqual(orchestrator["context_fingerprint"], context["context_fingerprint"])
            self.assertEqual(global_packet["context_fingerprint"], context["context_fingerprint"])
            self.assertEqual(global_packet["orchestrator_profile"], "standard")
            self.assertEqual(orchestrator["thread_counts"], {"unresolved": 4, "unresolved_non_outdated": 3, "unresolved_outdated": 1})
            self.assertEqual(orchestrator["thread_batches"], {"batch-01": ["t-1", "t-2"]})
            self.assertEqual(orchestrator["packet_worker_map"], {"thread-batch-01": ["packet_explorer"], "thread-03": ["packet_explorer"]})
            self.assertEqual(global_packet["packet_worker_map"], orchestrator["packet_worker_map"])
            self.assertEqual(orchestrator["recommended_worker_count"], 2)
            self.assertEqual(
                [worker["packets"] for worker in orchestrator["recommended_workers"]],
                [["global_packet.json", "thread-batch-01.json"], ["global_packet.json", "thread-03.json"]],
            )
            self.assertEqual(batch_packet["batch"]["thread_ids"], ["t-1", "t-2"])
            self.assertEqual(batch_packet["batch"]["cluster_reason"], "same_path_reviewer_and_line_window")
            self.assertIn("shared_fix_surface", batch_packet)
            self.assertTrue(batch_packet["validation_candidates"])
            self.assertIn("quality_escape_hints", batch_packet)
            self.assertTrue(batch_packet["adjudication_basis"]["common_path_sufficient"])
            self.assertEqual(singleton_packet["thread"]["thread_id"], "t-3")
            self.assertEqual(singleton_packet["applicability"]["default_decision_candidate"], "accept")
            self.assertIn("ownership_summary", singleton_packet)
            self.assertIn("reply_update_basis", singleton_packet)
            self.assertTrue(singleton_packet["validation_candidates"])
            self.assertEqual(outdated_packet["thread"]["thread_id"], "t-4")
            self.assertTrue(outdated_packet["thread"]["is_outdated"])
            self.assertEqual(outdated_packet["thread"]["default_decision_candidate"], "defer-outdated")
            self.assertTrue(packet_metrics["estimated_local_only_tokens"] > packet_metrics["estimated_packet_tokens"])
            self.assertTrue(build_result["common_path_sufficient"])
            self.assertNotIn("estimated_packet_tokens", build_result)
            self.assertEqual(Path(build_result["packet_metrics_file"]).name, "packet_metrics.json")

    def test_main_propagates_structured_marker_conflict_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/app.py",
                    line=10,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please tighten naming.",
                    marker_conflicts=[
                        marker_conflict(
                            phase="ack",
                            severity="warning",
                            reason="duplicate_exact_managed_replies",
                            comment_ids=["c1"],
                            blocks_adoption=False,
                            blocks_update=False,
                            blocks_apply=False,
                        ),
                        marker_conflict(
                            phase="complete",
                            severity="hard-stop",
                            reason="wrong_thread_managed_marker",
                            comment_ids=["c2"],
                            blocks_adoption=True,
                            blocks_update=True,
                            blocks_apply=True,
                        ),
                    ],
                )
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            output_dir = tmp / "packets"
            write_json(context_path, context)

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--repo-root",
                context["repo_root"],
                "--output-dir",
                str(output_dir),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(packets.main(), 0)

            orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))

            self.assertEqual(
                orchestrator["marker_conflict_summary"],
                {
                    "count": 2,
                    "by_severity": {"warning": 1, "adoption-blocking": 0, "hard-stop": 1},
                    "by_phase": {"ack": 1, "complete": 1},
                },
            )
            self.assertEqual(thread_packet["marker_conflicts"][0]["severity"], "warning")
            self.assertEqual(thread_packet["marker_conflicts"][1]["severity"], "hard-stop")

    def test_review_mode_override_does_not_upgrade_missing_evidence_to_common_path_sufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/missing.py",
                    line=10,
                    reviewer_login="reviewer-a",
                    reviewer_body="",
                )
            ]
            context = context_with_threads(tmp, threads)
            context["changed_files"] = ["src/app.py", ".github/workflows/release.yml"]
            (Path(context["repo_root"]) / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (Path(context["repo_root"]) / ".github" / "workflows" / "release.yml").write_text("name: release\n", encoding="utf-8")
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(context_path, context)

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--repo-root",
                context["repo_root"],
                "--output-dir",
                str(output_dir),
                "--result-output",
                str(build_result_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(packets.main(), 0)

            orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertEqual(orchestrator["review_mode"], "targeted-delegation")
            self.assertTrue(orchestrator["review_mode_overrides"])
            self.assertFalse(build_result["common_path_sufficient"])
            failure_reasons = build_result["common_path_failures"][0]["explicit_reread_reasons"]
            self.assertIn("missing_required_evidence", failure_reasons)
            self.assertIn("ownership_ambiguity", failure_reasons)

    def test_quality_escape_hints_are_advisory_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path=".github/workflows/release.yml",
                    line=1,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update the release workflow note.",
                )
            ]
            context = context_with_threads(tmp, threads)
            repo_root = Path(context["repo_root"])
            (repo_root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
            (repo_root / ".github" / "workflows" / "release.yml").write_text("name: release\n", encoding="utf-8")
            context["changed_files"] = [".github/workflows/release.yml"]
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            output_dir = tmp / "packets"
            write_json(context_path, context)

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--repo-root",
                context["repo_root"],
                "--output-dir",
                str(output_dir),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))

            self.assertTrue(thread_packet["quality_escape_hints"])
            self.assertTrue(thread_packet["adjudication_basis"]["common_path_sufficient"])
            self.assertEqual(thread_packet["adjudication_basis"]["explicit_reread_reasons"], [])

    def test_main_marks_same_run_outdated_transition_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                ),
                review_thread(
                    thread_id="t-2",
                    path="src/legacy.py",
                    line=1,
                    reviewer_login="reviewer-b",
                    reviewer_body="This legacy note is stale.",
                    is_outdated=True,
                ),
                review_thread(
                    thread_id="t-3",
                    path="src/helper.py",
                    line=2,
                    reviewer_login="reviewer-c",
                    reviewer_body="Please add more detail here.",
                ),
            ]
            current_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                    is_outdated=True,
                ),
                review_thread(
                    thread_id="t-2",
                    path="src/legacy.py",
                    line=1,
                    reviewer_login="reviewer-b",
                    reviewer_body="This legacy note is stale.",
                    is_outdated=True,
                ),
                review_thread(
                    thread_id="t-3",
                    path="src/helper.py",
                    line=2,
                    reviewer_login="reviewer-c",
                    reviewer_body="Please add more detail here.",
                ),
            ]
            previous_context = context_with_threads(tmp, previous_threads)
            current_context = context_with_threads(tmp, current_threads)
            repo_root = Path(current_context["repo_root"])
            (repo_root / "docs").mkdir(parents=True, exist_ok=True)
            (repo_root / "docs" / "guide.md").write_text(
                "# Guide\nOriginal wording\nCurrent wording\n",
                encoding="utf-8",
            )
            for context in (previous_context, current_context):
                context["changed_files"] = ["docs/guide.md", "src/helper.py", "src/legacy.py"]
                context["changed_file_groups"]["runtime"] = {
                    "count": 2,
                    "sample_files": ["src/helper.py", "src/legacy.py"],
                }
                context["changed_file_groups"]["docs"] = {
                    "count": 1,
                    "sample_files": ["docs/guide.md"],
                }
                context["context_fingerprint"] = build_context_fingerprint(context)

            previous_context_path = tmp / "previous-context.json"
            context_path = tmp / "context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, current_context)
            write_json(
                reconciliation_input_path,
                {
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_docs.py"],
                        }
                    ]
                },
            )

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--previous-context",
                str(previous_context_path),
                "--reconciliation-input",
                str(reconciliation_input_path),
                "--repo-root",
                current_context["repo_root"],
                "--output-dir",
                str(output_dir),
                "--result-output",
                str(build_result_path),
            ]
            def fake_diff_snippet(
                repo_root: Path,
                base_ref: str | None,
                head_ref: str | None,
                path: str,
                line_number: int | None,
                cache: dict[str, str | None],
            ) -> str | None:
                if path == "docs/guide.md":
                    return "@@ -1,2 +1,2 @@\n # Guide\n-Original wording\n+Current wording\n"
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            transitioned_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            already_outdated_packet = json.loads((output_dir / "thread-02.json").read_text(encoding="utf-8"))
            orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
            global_packet = json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertTrue(transitioned_packet["transitioned_to_outdated"])
            self.assertTrue(transitioned_packet["thread"]["transitioned_to_outdated"])
            self.assertEqual(transitioned_packet["outdated_recheck"]["resolution_verdict"], "auto-accept")
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["original_request"]["reviewer_body"],
                "Please use the current wording.",
            )
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["validation_provenance"]["commands"],
                ["python -m pytest tests/test_docs.py"],
            )
            self.assertNotIn("transitioned_to_outdated", already_outdated_packet)
            self.assertEqual(orchestrator["same_run_reconciliation"]["outdated_transition_candidates"], 1)
            self.assertEqual(orchestrator["same_run_reconciliation"]["outdated_auto_resolve_candidates"], 1)
            self.assertEqual(orchestrator["same_run_reconciliation"]["outdated_recheck_ambiguous"], 0)
            self.assertEqual(global_packet["same_run_reconciliation"], orchestrator["same_run_reconciliation"])
            self.assertTrue(build_result["same_run_reconciliation_enabled"])
            self.assertEqual(build_result["outdated_transition_candidates"], 1)
            self.assertEqual(build_result["outdated_auto_resolve_candidates"], 1)
            self.assertEqual(build_result["outdated_recheck_ambiguous"], 0)

    def test_same_run_outdated_transition_requires_diff_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                )
            ]
            current_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                    is_outdated=True,
                )
            ]
            previous_context = context_with_threads(tmp, previous_threads)
            current_context = context_with_threads(tmp, current_threads)
            repo_root = Path(current_context["repo_root"])
            (repo_root / "docs" / "guide.md").write_text(
                "# Guide\nCurrent wording\n",
                encoding="utf-8",
            )
            for context in (previous_context, current_context):
                context["changed_files"] = ["docs/guide.md"]
                context["changed_file_groups"]["runtime"] = {"count": 0, "sample_files": []}
                context["changed_file_groups"]["docs"] = {
                    "count": 1,
                    "sample_files": ["docs/guide.md"],
                }
                context["context_fingerprint"] = build_context_fingerprint(context)

            previous_context_path = tmp / "previous-context.json"
            context_path = tmp / "context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, current_context)
            write_json(
                reconciliation_input_path,
                {
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_docs.py"],
                        }
                    ]
                },
            )

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--previous-context",
                str(previous_context_path),
                "--reconciliation-input",
                str(reconciliation_input_path),
                "--repo-root",
                current_context["repo_root"],
                "--output-dir",
                str(output_dir),
                "--result-output",
                str(build_result_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(packets.main(), 0)

            transitioned_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertEqual(transitioned_packet["outdated_recheck"]["resolution_verdict"], "ambiguous")
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["verdict_reason"],
                "missing_current_head_evidence",
            )
            self.assertFalse(transitioned_packet["outdated_recheck"]["current_head_evidence"]["evidence_visible"])
            self.assertEqual(build_result["outdated_auto_resolve_candidates"], 0)
            self.assertEqual(build_result["outdated_recheck_ambiguous"], 1)

    def test_same_run_outdated_transition_requires_request_anchor_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                )
            ]
            current_threads = [
                review_thread(
                    thread_id="t-1",
                    path="docs/guide.md",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please use the current wording.",
                    is_outdated=True,
                )
            ]
            previous_context = context_with_threads(tmp, previous_threads)
            current_context = context_with_threads(tmp, current_threads)
            repo_root = Path(current_context["repo_root"])
            (repo_root / "docs" / "guide.md").write_text(
                "# Guide\nFresh intro\n",
                encoding="utf-8",
            )
            for context in (previous_context, current_context):
                context["changed_files"] = ["docs/guide.md"]
                context["changed_file_groups"]["runtime"] = {"count": 0, "sample_files": []}
                context["changed_file_groups"]["docs"] = {
                    "count": 1,
                    "sample_files": ["docs/guide.md"],
                }
                context["context_fingerprint"] = build_context_fingerprint(context)

            previous_context_path = tmp / "previous-context.json"
            context_path = tmp / "context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, current_context)
            write_json(
                reconciliation_input_path,
                {
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_docs.py"],
                        }
                    ]
                },
            )

            argv = [
                "build_review_packets.py",
                "--context",
                str(context_path),
                "--previous-context",
                str(previous_context_path),
                "--reconciliation-input",
                str(reconciliation_input_path),
                "--repo-root",
                current_context["repo_root"],
                "--output-dir",
                str(output_dir),
                "--result-output",
                str(build_result_path),
            ]

            def fake_diff_snippet(
                repo_root: Path,
                base_ref: str | None,
                head_ref: str | None,
                path: str,
                line_number: int | None,
                cache: dict[str, str | None],
            ) -> str | None:
                if path == "docs/guide.md":
                    return "@@ -1,2 +1,2 @@\n # Guide\n-Old intro\n+Fresh intro\n"
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            transitioned_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertEqual(transitioned_packet["outdated_recheck"]["resolution_verdict"], "ambiguous")
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["verdict_reason"],
                "missing_request_anchor_evidence",
            )
            self.assertTrue(transitioned_packet["outdated_recheck"]["current_head_evidence"]["evidence_visible"])
            self.assertFalse(
                transitioned_packet["outdated_recheck"]["current_head_evidence"]["request_anchor_visible"]
            )
            self.assertEqual(build_result["outdated_auto_resolve_candidates"], 0)
            self.assertEqual(build_result["outdated_recheck_ambiguous"], 1)


if __name__ == "__main__":
    unittest.main()
