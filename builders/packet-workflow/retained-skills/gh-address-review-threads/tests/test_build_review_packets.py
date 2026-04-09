from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import build_review_packets as packets  # type: ignore  # noqa: E402
from review_thread_packet_contract import build_grounding_diagnostics, compute_packet_metrics  # type: ignore  # noqa: E402
from review_thread_test_support import context_with_threads, marker_conflict, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


class BuildReviewPacketsTests(unittest.TestCase):
    def test_request_anchor_evidence_keeps_exact_anchor_strict(self) -> None:
        visible, exact_anchors, matched_exact_anchors, matched_terms = packets.request_anchor_evidence(
            "Please update `build_global_packet()` to match the renamed parameter.",
            snippet="def build_global_packet(context):\n    return context\n",
            diff_snippet=None,
        )

        self.assertFalse(visible)
        self.assertEqual(exact_anchors, ["buildglobalpacket()"])
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(matched_terms, [])

    def test_delta_request_anchor_evidence_matches_canonical_identifier_terms(self) -> None:
        visible, matched_exact_anchors, identifier_anchors, matched_identifier_anchors = (
            packets.delta_request_anchor_evidence(
                "Please update `build_global_packet()` to match the renamed parameter.",
                diff_snippet=(
                    "@@ -1,2 +1,2 @@\n"
                    "-def build_global_packet(report):\n"
                    "+def build_global_packet(context):\n"
                ),
            )
        )

        self.assertTrue(visible)
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(identifier_anchors, ["build_global_packet"])
        self.assertEqual(matched_identifier_anchors, ["build_global_packet"])

    def test_delta_request_anchor_evidence_matches_split_dotted_identifier_terms(self) -> None:
        visible, matched_exact_anchors, identifier_anchors, matched_identifier_anchors = (
            packets.delta_request_anchor_evidence(
                "Please update `module.helper()` to match the renamed parameter.",
                diff_snippet=(
                    "@@ -1,2 +1,2 @@\n"
                    "-module.helper(report)\n"
                    "+module.helper(context)\n"
                ),
            )
        )

        self.assertTrue(visible)
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(identifier_anchors, ["module", "helper"])
        self.assertEqual(matched_identifier_anchors, ["module", "helper"])

    def test_delta_request_anchor_evidence_requires_full_multi_token_identifier_match(self) -> None:
        visible, matched_exact_anchors, identifier_anchors, matched_identifier_anchors = (
            packets.delta_request_anchor_evidence(
                "Please update `module.helper()` to match the renamed parameter.",
                diff_snippet=(
                    "@@ -1,2 +1,2 @@\n"
                    "-module = legacy_factory()\n"
                    "+module = updated_factory()\n"
                ),
            )
        )

        self.assertFalse(visible)
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(identifier_anchors, ["module", "helper"])
        self.assertEqual(matched_identifier_anchors, ["module"])

    def test_delta_request_anchor_evidence_requires_identifier_terms_on_same_diff_line(self) -> None:
        visible, matched_exact_anchors, identifier_anchors, matched_identifier_anchors = (
            packets.delta_request_anchor_evidence(
                "Please update `module.helper()` to match the renamed parameter.",
                diff_snippet=(
                    "@@ -1,3 +1,4 @@\n"
                    "-module = legacy_factory()\n"
                    "+module = updated_factory()\n"
                    "+helper = build_helper()\n"
                ),
            )
        )

        self.assertFalse(visible)
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(identifier_anchors, ["module", "helper"])
        self.assertEqual(matched_identifier_anchors, ["module", "helper"])

    def test_delta_request_anchor_evidence_requires_structural_identifier_match(self) -> None:
        visible, matched_exact_anchors, identifier_anchors, matched_identifier_anchors = (
            packets.delta_request_anchor_evidence(
                "Please update `module.helper()` to match the renamed parameter.",
                diff_snippet=(
                    "@@ -1,1 +1,1 @@\n"
                    "-legacy_value = old_helper\n"
                    "+module = helper\n"
                ),
            )
        )

        self.assertFalse(visible)
        self.assertEqual(matched_exact_anchors, [])
        self.assertEqual(identifier_anchors, ["module", "helper"])
        self.assertEqual(matched_identifier_anchors, ["module", "helper"])

    def test_grounding_diagnostics_marks_near_match_as_mismatch(self) -> None:
        grounding = build_grounding_diagnostics(
            "Please update `module.helper()` to match the renamed parameter.",
            path="src/app.py",
            path_exists=True,
            snippet="   10: module = helper\n",
            diff_snippet=None,
        )

        self.assertTrue(grounding["has_explicit_anchor"])
        self.assertFalse(grounding["exact_anchor_match"])
        self.assertFalse(grounding["structural_anchor_match"])
        self.assertTrue(grounding["grounding_mismatch"])
        self.assertEqual(grounding["mapped_escape_reason"], "missing_required_evidence")

    def test_grounding_diagnostics_ignores_broad_natural_language_requests(self) -> None:
        grounding = build_grounding_diagnostics(
            "Please clarify this flow before merging.",
            path="src/app.py",
            path_exists=True,
            snippet="   10: return current_flow\n",
            diff_snippet=None,
        )

        self.assertFalse(grounding["has_explicit_anchor"])
        self.assertFalse(grounding["grounding_mismatch"])
        self.assertIsNone(grounding["mapped_escape_reason"])

    def _run_estimated_savings_observation_case(
        self,
    ) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/app.py",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please tighten the worker selection handling.",
                )
            ]
            context = context_with_threads(tmp, threads)
            context["conversation_comments"] = [
                {
                    "id": "comment-1",
                    "body": "x" * 20000,
                    "created_at": "2026-03-01T00:00:00Z",
                    "updated_at": "2026-03-01T00:00:00Z",
                    "url": "https://example.invalid/pr/11#issuecomment-1",
                    "author_login": "reviewer-a",
                }
            ]
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
            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                return_value=None,
            ):
                self.assertEqual(packets.main(), 0)

            return (
                context,
                threads,
                json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8")),
                json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8")),
                json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8")),
                json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8")),
                json.loads(build_result_path.read_text(encoding="utf-8")),
            )

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
            self.assertIn("common_path_contract", global_packet)
            self.assertIn(
                "override_signals",
                global_packet["common_path_contract"]["override_policy"],
            )
            self.assertNotIn(
                "review_mode_overrides",
                global_packet["common_path_contract"]["override_policy"],
            )
            self.assertNotIn("estimated_packet_tokens", orchestrator)
            self.assertEqual(orchestrator["context_fingerprint"], context["context_fingerprint"])
            self.assertEqual(global_packet["context_fingerprint"], context["context_fingerprint"])
            self.assertEqual(global_packet["orchestrator_profile"], "standard")
            self.assertEqual(orchestrator["thread_counts"], {"unresolved": 4, "unresolved_non_outdated": 3, "unresolved_outdated": 1})
            self.assertEqual(orchestrator["packet_worker_map"], {"thread-batch-01": ["packet_explorer"], "thread-03": ["packet_explorer"]})
            self.assertEqual(global_packet["packet_worker_map"], orchestrator["packet_worker_map"])
            self.assertNotIn("recommended_worker_count", orchestrator)
            self.assertNotIn("recommended_workers", orchestrator)
            self.assertNotIn("active_paths", orchestrator)
            self.assertNotIn("active_areas", orchestrator)
            self.assertNotIn("analysis_targets", orchestrator)
            self.assertNotIn("thread_batches", orchestrator)
            self.assertEqual(
                [worker["packets"] for worker in build_result["recommended_workers"]],
                [["global_packet.json", "thread-batch-01.json"], ["global_packet.json", "thread-03.json"]],
            )
            self.assertEqual(build_result["recommended_worker_count"], 2)
            self.assertEqual(build_result["thread_batch_count"], 1)
            self.assertEqual(build_result["analysis_targets"], {"batch_count": 1, "singleton_count": 1})
            self.assertEqual(build_result["thread_batches"], {"batch-01": ["t-1", "t-2"]})
            self.assertEqual(build_result["active_paths"], ["src/app.py", "src/helper.py"])
            self.assertEqual(build_result["active_areas"], ["runtime"])
            self.assertEqual(
                build_result["delegation_non_use_cases"],
                {
                    "runtime_routing_authority": "packet_worker_map",
                    "record_only": [
                        "review_mode_local_only",
                        "code_change_guardrail_blockers",
                        "broad_or_cross_cutting_fix_kept_local",
                        "validation_path_unclear",
                        "optional_qa_not_requested",
                    ],
                    "fatal": [],
                },
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

    def test_main_defaults_singleton_explicit_anchor_mismatch_to_defer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/app.py",
                    line=10,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update `module.helper()` to match the renamed parameter.",
                )
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
            with patch.object(sys, "argv", argv), patch.object(packets, "diff_snippet_for_path", return_value=None):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertTrue(thread_packet["grounding"]["grounding_mismatch"])
            self.assertEqual(thread_packet["grounding"]["mapped_escape_reason"], "missing_required_evidence")
            self.assertEqual(thread_packet["thread"]["default_decision_candidate"], "defer")
            self.assertEqual(thread_packet["applicability"]["default_decision_candidate"], "defer")
            self.assertFalse(thread_packet["adjudication_basis"]["common_path_sufficient"])
            self.assertFalse(build_result["common_path_sufficient"])

    def test_main_lowers_batch_shared_default_without_overwriting_thread_defaults(self) -> None:
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
                    line=18,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update `module.helper()` to match the renamed parameter.",
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
            with patch.object(sys, "argv", argv), patch.object(packets, "diff_snippet_for_path", return_value=None):
                self.assertEqual(packets.main(), 0)

            batch_packet = json.loads((output_dir / "thread-batch-01.json").read_text(encoding="utf-8"))
            thread_defaults = {item["thread_id"]: item for item in batch_packet["threads"]}

            self.assertEqual(batch_packet["shared_fix_surface"]["default_decision_candidate"], "defer")
            self.assertEqual(thread_defaults["t-1"]["default_decision_candidate"], "accept")
            self.assertFalse(thread_defaults["t-1"]["grounding"]["grounding_mismatch"])
            self.assertEqual(thread_defaults["t-2"]["default_decision_candidate"], "defer")
            self.assertTrue(thread_defaults["t-2"]["grounding"]["grounding_mismatch"])

    def test_main_grounds_batched_threads_with_their_own_line_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=5,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please revisit this.\n`module.helper()` should stay aligned.",
                    ),
                    review_thread(
                        thread_id="t-2",
                        path="src/app.py",
                        line=40,
                        reviewer_login="reviewer-b",
                        reviewer_body="Please revisit this.\n`other.call()` should stay aligned.",
                    ),
                ],
            )
            repo_root = Path(context["repo_root"])
            (repo_root / "src" / "app.py").write_text(
                "\n".join(
                    [
                        "line 1",
                        "line 2",
                        "line 3",
                        "line 4",
                        "module.helper()",
                        "line 6",
                        "line 7",
                        "line 8",
                        "line 9",
                        "line 10",
                        "line 11",
                        "line 12",
                        "line 13",
                        "line 14",
                        "line 15",
                        "line 16",
                        "line 17",
                        "line 18",
                        "line 19",
                        "line 20",
                        "line 21",
                        "line 22",
                        "line 23",
                        "line 24",
                        "line 25",
                        "line 26",
                        "line 27",
                        "line 28",
                        "line 29",
                        "line 30",
                        "line 31",
                        "line 32",
                        "line 33",
                        "line 34",
                        "line 35",
                        "line 36",
                        "line 37",
                        "line 38",
                        "line 39",
                        "other.call()",
                        "line 41",
                        "line 42",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
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
            with patch.object(sys, "argv", argv), patch.object(packets, "diff_snippet_for_path", return_value=None):
                self.assertEqual(packets.main(), 0)

            batch_packet = json.loads((output_dir / "thread-batch-01.json").read_text(encoding="utf-8"))
            thread_defaults = {item["thread_id"]: item for item in batch_packet["threads"]}

            self.assertFalse(thread_defaults["t-1"]["grounding"]["grounding_mismatch"])
            self.assertFalse(thread_defaults["t-2"]["grounding"]["grounding_mismatch"])
            self.assertEqual(thread_defaults["t-1"]["default_decision_candidate"], "accept")
            self.assertEqual(thread_defaults["t-2"]["default_decision_candidate"], "accept")
            self.assertEqual(batch_packet["shared_fix_surface"]["default_decision_candidate"], "accept")
            self.assertTrue(batch_packet["adjudication_basis"]["common_path_sufficient"])

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
            self.assertNotIn("review_mode_overrides", orchestrator)
            self.assertFalse(build_result["common_path_sufficient"])
            self.assertTrue(build_result["override_signals"])
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

    def test_main_keeps_local_only_when_only_estimated_token_savings_are_high(self) -> None:
        context, _threads, _global_packet, _thread_packet, orchestrator, _packet_metrics, build_result = (
            self._run_estimated_savings_observation_case()
        )

        self.assertEqual(orchestrator["review_mode"], "local-only")
        self.assertNotIn("review_mode_adjustments", orchestrator)
        self.assertNotIn("recommended_worker_count", orchestrator)
        self.assertEqual(build_result["review_mode"], "local-only")
        self.assertEqual(build_result["review_mode_baseline"], "local-only")
        self.assertEqual(build_result["review_mode_adjustments"], [])
        self.assertEqual(build_result["recommended_worker_count"], 0)
        self.assertEqual(build_result["recommended_workers"], [])
        self.assertEqual(context["conversation_comments"][0]["author_login"], "reviewer-a")

    def test_main_keeps_packet_metrics_observational_when_estimated_savings_are_high(self) -> None:
        context, threads, global_packet, thread_packet, orchestrator, packet_metrics, build_result = (
            self._run_estimated_savings_observation_case()
        )

        expected_packet_metrics = compute_packet_metrics(
            {
                "global_packet.json": global_packet,
                "thread-01.json": thread_packet,
                "orchestrator.json": orchestrator,
            },
            common_path_packet_names=["global_packet.json", "thread-01.json"],
            local_only_sources={
                "context": context,
                "threads": threads,
                "pr": context["pr"],
                "changed_files": context["changed_files"],
                "override_signals": [],
            },
        )
        self.assertEqual(packet_metrics["packet_count"], len(orchestrator["packet_files"]))
        self.assertEqual(packet_metrics, expected_packet_metrics)
        self.assertGreater(packet_metrics["estimated_delegation_savings"], 0)
        self.assertEqual(build_result["review_mode"], "local-only")
        self.assertEqual(build_result["packet_metrics_file"], str(Path(context["repo_root"]).parent / "packets" / "packet_metrics.json"))

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

    def test_same_run_outdated_transition_does_not_require_request_anchor_evidence(self) -> None:
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

            self.assertEqual(transitioned_packet["outdated_recheck"]["resolution_verdict"], "auto-accept")
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["verdict_reason"],
                "accepted_same_run_with_current_head_evidence",
            )
            self.assertTrue(transitioned_packet["outdated_recheck"]["current_head_evidence"]["evidence_visible"])
            self.assertFalse(
                transitioned_packet["outdated_recheck"]["current_head_evidence"]["request_anchor_visible"]
            )
            self.assertEqual(build_result["outdated_auto_resolve_candidates"], 1)
            self.assertEqual(build_result["outdated_recheck_ambiguous"], 0)

    def test_same_run_outdated_transition_allows_template_auto_accept_with_request_anchor_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="core/templates/packet-workflow/skill_md.tmpl",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body=(
                        "Please use `references/__DOMAIN_EVALUATION_CONTRACT_FILE__` "
                        "for the domain evaluation fields entry."
                    ),
                )
            ]
            current_threads = [
                review_thread(
                    thread_id="t-1",
                    path="core/templates/packet-workflow/skill_md.tmpl",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body=(
                        "Please use `references/__DOMAIN_EVALUATION_CONTRACT_FILE__` "
                        "for the domain evaluation fields entry."
                    ),
                    is_outdated=True,
                )
            ]
            previous_context = context_with_threads(tmp, previous_threads)
            current_context = context_with_threads(tmp, current_threads)
            repo_root = Path(current_context["repo_root"])
            template_path = repo_root / "core" / "templates" / "packet-workflow" / "skill_md.tmpl"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text(
                "\n".join(
                    [
                        "## References",
                        "- Domain evaluation fields: `references/__DOMAIN_EVALUATION_CONTRACT_FILE__`",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            for context in (previous_context, current_context):
                context["changed_files"] = ["core/templates/packet-workflow/skill_md.tmpl"]
                context["changed_file_groups"]["runtime"] = {"count": 0, "sample_files": []}
                context["changed_file_groups"]["other"] = {
                    "count": 1,
                    "sample_files": ["core/templates/packet-workflow/skill_md.tmpl"],
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
                            "validation_commands": [
                                "python -m pytest builders/packet-workflow/tests/test_packet_workflow_builder_contract.py -q"
                            ],
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
                if path == "core/templates/packet-workflow/skill_md.tmpl":
                    return (
                        "@@ -1,2 +1,2 @@\n"
                        " ## References\n"
                        "- Domain evaluation fields: `references/__DOMAIN_SLUG__-evaluation-contract.md`\n"
                        "+ Domain evaluation fields: `references/__DOMAIN_EVALUATION_CONTRACT_FILE__`\n"
                    )
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            transitioned_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))

            self.assertEqual(transitioned_packet["outdated_recheck"]["resolution_verdict"], "auto-accept")
            self.assertEqual(
                transitioned_packet["outdated_recheck"]["verdict_reason"],
                "accepted_same_run_with_current_head_evidence",
            )
            self.assertTrue(
                transitioned_packet["outdated_recheck"]["current_head_evidence"]["request_anchor_visible"]
            )
            self.assertEqual(build_result["outdated_auto_resolve_candidates"], 1)
            self.assertEqual(build_result["outdated_recheck_ambiguous"], 0)

    def test_post_push_marks_non_outdated_accepted_thread_with_delta_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/helper.py",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please fix the helper branch.",
                )
            ]
            current_threads = json.loads(json.dumps(previous_threads))
            previous_context = context_with_threads(tmp, previous_threads)
            context = context_with_threads(tmp, current_threads)
            repo_root = Path(context["repo_root"])
            (repo_root / "src" / "helper.py").write_text(
                "alpha\nbeta updated\ngamma\n",
                encoding="utf-8",
            )
            context["changed_files"] = ["src/helper.py"]
            context["changed_file_groups"]["runtime"] = {
                "count": 1,
                "sample_files": ["src/helper.py"],
            }
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            previous_context_path = tmp / "previous-context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
            write_json(previous_context_path, previous_context)
            write_json(context_path, context)
            write_json(
                reconciliation_input_path,
                {
                    "pre_push_head_sha": "pre-sha",
                    "post_push_head_sha": "post-sha",
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_helper.py"],
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
                context["repo_root"],
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
                cache: dict[object, str | None],
            ) -> str | None:
                if path == "src/helper.py" and base_ref == "pre-sha" and head_ref == "post-sha":
                    return "@@ -1,3 +1,3 @@\n alpha\n-beta\n+beta updated\n gamma\n"
                if path == "src/helper.py" and base_ref == "main" and head_ref == "feature/packets":
                    return "@@ -1,3 +1,3 @@\n alpha\n-beta\n+beta updated\n gamma\n"
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            self.assertEqual(thread_packet["accepted_recheck"]["resolution_verdict"], "auto-accept")
            self.assertEqual(
                thread_packet["accepted_recheck"]["verdict_reason"],
                "accepted_same_run_with_post_push_delta_evidence",
            )
            self.assertTrue(thread_packet["accepted_recheck"]["current_head_evidence"]["evidence_visible"])
            self.assertEqual(thread_packet["accepted_recheck"]["current_head_evidence"]["evidence_kind"], "post_push_delta")

    def test_post_push_marks_non_outdated_accepted_thread_with_delta_anchor_identifier_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/helper.py",
                    line=40,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update `build_global_packet()` to match the renamed parameter.",
                )
            ]
            current_threads = json.loads(json.dumps(previous_threads))
            previous_context = context_with_threads(tmp, previous_threads)
            context = context_with_threads(tmp, current_threads)
            repo_root = Path(context["repo_root"])
            helper_lines = [
                "def build_global_packet(context):",
                "    return context",
                "",
            ] + [f"padding_{index} = {index}" for index in range(1, 48)]
            (repo_root / "src" / "helper.py").write_text(
                "\n".join(helper_lines) + "\n",
                encoding="utf-8",
            )
            context["changed_files"] = ["src/helper.py"]
            context["changed_file_groups"]["runtime"] = {
                "count": 1,
                "sample_files": ["src/helper.py"],
            }
            previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            previous_context_path = tmp / "previous-context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, context)
            write_json(
                reconciliation_input_path,
                {
                    "pre_push_head_sha": "pre-sha",
                    "post_push_head_sha": "post-sha",
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_helper.py"],
                        }
                    ],
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
                context["repo_root"],
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
                cache: dict[object, str | None],
            ) -> str | None:
                if path == "src/helper.py" and base_ref == "pre-sha" and head_ref == "post-sha":
                    return (
                        "@@ -1,2 +1,2 @@\n"
                        "-def build_global_packet(report):\n"
                        "-    return report\n"
                        "+def build_global_packet(context):\n"
                        "+    return context\n"
                    )
                if path == "src/helper.py" and base_ref == "main" and head_ref == "feature/packets":
                    return (
                        "@@ -1,2 +1,2 @@\n"
                        "-def build_global_packet(report):\n"
                        "-    return report\n"
                        "+def build_global_packet(context):\n"
                        "+    return context\n"
                    )
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            self.assertEqual(thread_packet["accepted_recheck"]["resolution_verdict"], "auto-accept")
            self.assertEqual(
                thread_packet["accepted_recheck"]["verdict_reason"],
                "accepted_same_run_with_post_push_anchor_evidence",
            )
            self.assertFalse(thread_packet["accepted_recheck"]["current_head_evidence"]["evidence_visible"])
            self.assertFalse(thread_packet["accepted_recheck"]["current_head_evidence"]["request_anchor_visible"])
            self.assertTrue(thread_packet["accepted_recheck"]["current_head_evidence"]["delta_request_anchor_visible"])
            self.assertEqual(
                thread_packet["accepted_recheck"]["current_head_evidence"]["matched_delta_exact_request_anchors"],
                [],
            )
            self.assertEqual(
                thread_packet["accepted_recheck"]["current_head_evidence"]["matched_identifier_request_anchors"],
                ["build_global_packet"],
            )

    def test_post_push_does_not_auto_accept_when_only_removed_anchor_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/helper.py",
                    line=40,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update `module.helper()` to match the renamed parameter.",
                )
            ]
            current_threads = json.loads(json.dumps(previous_threads))
            previous_context = context_with_threads(tmp, previous_threads)
            context = context_with_threads(tmp, current_threads)
            repo_root = Path(context["repo_root"])
            helper_lines = [
                "module = helper",
                "",
            ] + [f"padding_{index} = {index}" for index in range(1, 48)]
            (repo_root / "src" / "helper.py").write_text(
                "\n".join(helper_lines) + "\n",
                encoding="utf-8",
            )
            context["changed_files"] = ["src/helper.py"]
            context["changed_file_groups"]["runtime"] = {
                "count": 1,
                "sample_files": ["src/helper.py"],
            }
            previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            previous_context_path = tmp / "previous-context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, context)
            write_json(
                reconciliation_input_path,
                {
                    "pre_push_head_sha": "pre-sha",
                    "post_push_head_sha": "post-sha",
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_helper.py"],
                        }
                    ],
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
                context["repo_root"],
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
                cache: dict[object, str | None],
            ) -> str | None:
                if path == "src/helper.py" and base_ref == "pre-sha" and head_ref == "post-sha":
                    return (
                        "@@ -1,2 +1,2 @@\n"
                        "-module.helper(old)\n"
                        "+module = helper\n"
                    )
                if path == "src/helper.py" and base_ref == "main" and head_ref == "feature/packets":
                    return (
                        "@@ -1,2 +1,2 @@\n"
                        "-module.helper(old)\n"
                        "+module = helper\n"
                    )
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            self.assertEqual(thread_packet["accepted_recheck"]["resolution_verdict"], "still-applies")
            self.assertEqual(
                thread_packet["accepted_recheck"]["verdict_reason"],
                "missing_post_push_delta_evidence",
            )
            self.assertFalse(thread_packet["accepted_recheck"]["current_head_evidence"]["delta_request_anchor_visible"])

    def test_post_push_keeps_non_outdated_accepted_thread_open_when_identifier_terms_only_cooccur(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/helper.py",
                    line=40,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please update `module.helper()` to match the renamed parameter.",
                )
            ]
            current_threads = json.loads(json.dumps(previous_threads))
            previous_context = context_with_threads(tmp, previous_threads)
            context = context_with_threads(tmp, current_threads)
            repo_root = Path(context["repo_root"])
            helper_lines = [
                "module = helper",
                "",
            ] + [f"padding_{index} = {index}" for index in range(1, 48)]
            (repo_root / "src" / "helper.py").write_text(
                "\n".join(helper_lines) + "\n",
                encoding="utf-8",
            )
            context["changed_files"] = ["src/helper.py"]
            context["changed_file_groups"]["runtime"] = {
                "count": 1,
                "sample_files": ["src/helper.py"],
            }
            previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            previous_context_path = tmp / "previous-context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, context)
            write_json(
                reconciliation_input_path,
                {
                    "pre_push_head_sha": "pre-sha",
                    "post_push_head_sha": "post-sha",
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_helper.py"],
                        }
                    ],
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
                context["repo_root"],
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
                cache: dict[object, str | None],
            ) -> str | None:
                if path == "src/helper.py" and base_ref == "pre-sha" and head_ref == "post-sha":
                    return (
                        "@@ -1,1 +1,1 @@\n"
                        "-legacy_value = old_helper\n"
                        "+module = helper\n"
                    )
                if path == "src/helper.py" and base_ref == "main" and head_ref == "feature/packets":
                    return (
                        "@@ -1,1 +1,1 @@\n"
                        "-legacy_value = old_helper\n"
                        "+module = helper\n"
                    )
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            self.assertEqual(thread_packet["accepted_recheck"]["resolution_verdict"], "still-applies")
            self.assertEqual(
                thread_packet["accepted_recheck"]["verdict_reason"],
                "missing_post_push_delta_evidence",
            )
            self.assertFalse(thread_packet["accepted_recheck"]["current_head_evidence"]["delta_request_anchor_visible"])
            self.assertEqual(
                thread_packet["accepted_recheck"]["current_head_evidence"]["matched_identifier_request_anchors"],
                ["module", "helper"],
            )

    def test_post_push_keeps_non_outdated_accepted_thread_open_without_delta_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            previous_threads = [
                review_thread(
                    thread_id="t-1",
                    path="src/helper.py",
                    line=2,
                    reviewer_login="reviewer-a",
                    reviewer_body="Please fix the helper branch.",
                )
            ]
            current_threads = json.loads(json.dumps(previous_threads))
            previous_context = context_with_threads(tmp, previous_threads)
            context = context_with_threads(tmp, current_threads)
            repo_root = Path(context["repo_root"])
            (repo_root / "src" / "helper.py").write_text(
                "alpha\nbeta\ngamma\n",
                encoding="utf-8",
            )
            context["changed_files"] = ["src/helper.py"]
            context["changed_file_groups"]["runtime"] = {
                "count": 1,
                "sample_files": ["src/helper.py"],
            }
            previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
            context["context_fingerprint"] = build_context_fingerprint(context)

            context_path = tmp / "context.json"
            previous_context_path = tmp / "previous-context.json"
            reconciliation_input_path = tmp / "reconciliation-input.json"
            output_dir = tmp / "packets"
            build_result_path = tmp / "build-result.json"
            write_json(previous_context_path, previous_context)
            write_json(context_path, context)
            write_json(
                reconciliation_input_path,
                {
                    "pre_push_head_sha": "pre-sha",
                    "post_push_head_sha": "post-sha",
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["python -m pytest tests/test_helper.py"],
                        }
                    ],
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
                context["repo_root"],
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
                cache: dict[object, str | None],
            ) -> str | None:
                if path == "src/helper.py" and base_ref == "main" and head_ref == "feature/packets":
                    return "@@ -1,3 +1,3 @@\n alpha\n-beta\n+beta updated\n gamma\n"
                if path == "src/helper.py" and base_ref == "pre-sha" and head_ref == "post-sha":
                    return None
                return None

            with patch.object(sys, "argv", argv), patch.object(
                packets,
                "diff_snippet_for_path",
                side_effect=fake_diff_snippet,
            ):
                self.assertEqual(packets.main(), 0)

            thread_packet = json.loads((output_dir / "thread-01.json").read_text(encoding="utf-8"))
            self.assertEqual(thread_packet["accepted_recheck"]["resolution_verdict"], "still-applies")
            self.assertEqual(
                thread_packet["accepted_recheck"]["verdict_reason"],
                "missing_post_push_delta_evidence",
            )
            self.assertFalse(thread_packet["accepted_recheck"]["current_head_evidence"]["evidence_visible"])


if __name__ == "__main__":
    unittest.main()
