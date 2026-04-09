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

import apply_thread_action_plan as apply_plan  # type: ignore  # noqa: E402
import validate_thread_action_plan as validate_plan  # type: ignore  # noqa: E402
from review_thread_test_support import ack_reply_body, comment, context_with_threads, marker_conflict, reply_candidate, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint, validate_thread_action_payload  # type: ignore  # noqa: E402


class ValidateAndApplyThreadActionPlanTests(unittest.TestCase):
    def test_run_json_wraps_missing_executable(self) -> None:
        with patch.object(apply_plan.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(RuntimeError) as exc_info:
                apply_plan.run_json(["gh", "api", "graphql"], cwd=Path("."))
        self.assertEqual(str(exc_info.exception), "gh executable not found")

    def test_validator_sorts_actions_and_ignores_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-2", path="src/helper.py", line=20, reviewer_login="reviewer-b", reviewer_body="Please add a test."),
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this."),
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)

            payload = {
                "thread_actions": [
                    {
                        "thread_id": "t-2",
                        "decision": "defer",
                        "ack_mode": "add",
                        "ack_body": ack_reply_body(
                            decision="defer",
                            detail="Deferring until the current packet evidence is re-grounded.",
                        ),
                        "junk": "remove me",
                    },
                    {
                        "thread_id": "t-1",
                        "decision": "accept",
                        "ack_mode": "add",
                        "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                    },
                ]
            }
            result = validate_thread_action_payload(context, payload, "ack")

            self.assertTrue(result["valid"])
            self.assertEqual([item["thread_id"] for item in result["normalized_thread_actions"]], ["t-1", "t-2"])
            self.assertEqual(result["warnings"][0]["code"], "unknown_action_field_ignored")
            self.assertEqual(result["counters"]["unknown_fields_ignored"], 1)

    def test_validator_blocks_adoption_fallback_and_hard_stop_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            adoption_thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-2",
                        reason="adopt_latest_unmarked_reply_after_reviewer",
                        managed=False,
                        adopted_unmarked_reply=True,
                    ),
                    "complete": reply_candidate(
                        mode="add",
                        comment_id=None,
                        reason="complete_never_adopts_unmarked_reply",
                        managed=False,
                        adopted_unmarked_reply=False,
                    ),
                },
                marker_conflicts=[
                    marker_conflict(
                        phase="ack",
                        severity="adoption-blocking",
                        reason="multiple_unmarked_replies_after_latest_reviewer",
                        comment_ids=["self-1", "self-2"],
                        blocks_adoption=True,
                        blocks_update=False,
                        blocks_apply=False,
                    )
                ],
            )
            hard_stop_thread = review_thread(
                thread_id="t-2",
                path="src/helper.py",
                line=20,
                reviewer_login="reviewer-b",
                reviewer_body="Please add a test.",
                marker_conflicts=[
                    marker_conflict(
                        phase="ack",
                        severity="hard-stop",
                        reason="wrong_thread_managed_marker",
                        comment_ids=["bad-1"],
                        blocks_adoption=True,
                        blocks_update=True,
                        blocks_apply=True,
                    )
                ],
            )
            context = context_with_threads(tmp, [adoption_thread, hard_stop_thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            payload = {
                "thread_actions": [
                    {
                        "thread_id": "t-1",
                        "decision": "accept",
                        "ack_mode": "update",
                        "ack_body": ack_reply_body(decision="accept", detail="Updating the previous reply."),
                    },
                    {
                        "thread_id": "t-2",
                        "decision": "accept",
                        "ack_mode": "update",
                        "ack_body": ack_reply_body(decision="accept", detail="Trying to update through hard stop."),
                        "ack_comment_id": "bad-1",
                    },
                ]
            }
            result = validate_thread_action_payload(context, payload, "ack")

            self.assertFalse(result["valid"])
            self.assertEqual([item["code"] for item in result["errors"]], ["adoption_blocked_update", "hard_stop_marker_conflict"])

    def test_validator_uses_fixed_resolve_after_complete_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)

            ack_result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(
                                decision="accept",
                                detail="Will update the naming and rerun the relevant check.",
                            ),
                            "resolve_after_complete": True,
                        }
                    ]
                },
                "ack",
            )
            self.assertTrue(ack_result["valid"])
            self.assertEqual(ack_result["warnings"][0]["code"], "ignored_resolve_after_complete_outside_complete")

            complete_result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "complete_mode": "skip",
                            "resolve_after_complete": True,
                        }
                    ]
                },
                "complete",
            )
            self.assertFalse(complete_result["valid"])
            self.assertEqual(complete_result["errors"][0]["code"], "invalid_resolve_after_complete")

    def test_validator_rejects_ack_skip_without_exact_managed_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-1",
                        reason="adopt_latest_unmarked_reply_after_reviewer",
                        managed=False,
                        adopted_unmarked_reply=True,
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
                        body="Previous unmarked reply.",
                        created_at="2026-03-01T00:05:00Z",
                    )
                ],
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "non_exact_reply_candidate_for_skip")

    def test_validator_rejects_ack_add_without_explicit_decision_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": "Will fix this.",
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "missing_ack_body_decision")

    def test_validator_rejects_ack_update_when_body_decision_mismatches_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                comments=[
                    comment(
                        comment_id="self-1",
                        author_login="codex",
                        body="Previous unmarked reply.",
                        created_at="2026-03-01T00:05:00Z",
                    )
                ],
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-1",
                        reason="adopt_latest_unmarked_reply_after_reviewer",
                        managed=False,
                        adopted_unmarked_reply=True,
                    ),
                    "complete": reply_candidate(
                        mode="add",
                        comment_id=None,
                        reason="complete_never_adopts_unmarked_reply",
                        managed=False,
                        adopted_unmarked_reply=False,
                    ),
                },
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "update",
                            "ack_body": ack_reply_body(decision="defer", detail="Waiting for clearer grounding."),
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "mismatched_ack_body_decision")

    def test_validator_rejects_ack_skip_when_no_existing_ack_reply_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "missing_exact_managed_skip_target")

    def test_validator_allows_ack_skip_with_exact_managed_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
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
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertTrue(result["valid"])
            self.assertEqual(result["normalized_thread_actions"][0]["ack_mode"], "skip")

    def test_validator_rejects_ack_skip_when_exact_managed_decision_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-4",
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
                        comment_id="self-4",
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
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "mismatched_exact_managed_skip_decision")

    def test_validator_reads_skip_decision_from_explicit_decision_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-5",
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
                        comment_id="self-5",
                        author_login="codex",
                        body=(
                            "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                            "Reviewer asked to rename this.\n"
                            "I can accept the concern, but current grounding is incomplete.\n"
                            "defer\n"
                            "Will revisit after checking the current packet evidence."
                        ),
                        created_at="2026-03-01T00:05:00Z",
                        managed_phase="ack",
                        managed_thread_id="t-1",
                        has_exact_managed_marker=True,
                    )
                ],
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertFalse(result["valid"])
            self.assertEqual(result["errors"][0]["code"], "mismatched_exact_managed_skip_decision")

    def test_validator_allows_skip_when_later_explicit_decision_line_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-6",
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
                        comment_id="self-6",
                        author_login="codex",
                        body=(
                            "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                            "Reviewer asked to rename this.\n"
                            "I can accept the concern, but current grounding is incomplete.\n"
                            "defer\n"
                            "Will revisit after checking the current packet evidence."
                        ),
                        created_at="2026-03-01T00:05:00Z",
                        managed_phase="ack",
                        managed_thread_id="t-1",
                        has_exact_managed_marker=True,
                    )
                ],
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertTrue(result["valid"])
            self.assertEqual(result["normalized_thread_actions"][0]["ack_mode"], "skip")

    def test_validator_allows_skip_when_decision_line_uses_decision_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-7",
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
                        comment_id="self-7",
                        author_login="codex",
                        body=(
                            "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                            "Reviewer asked to rename this.\n"
                            "Decision: defer until the current packet evidence is re-grounded.\n"
                            "Waiting for clearer grounding before changing behavior."
                        ),
                        created_at="2026-03-01T00:05:00Z",
                        managed_phase="ack",
                        managed_thread_id="t-1",
                        has_exact_managed_marker=True,
                    )
                ],
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "skip",
                        }
                    ]
                },
                "ack",
            )

            self.assertTrue(result["valid"])
            self.assertEqual(result["normalized_thread_actions"][0]["ack_mode"], "skip")

    def test_validator_allows_adoptable_ack_reply_update_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/app.py",
                line=10,
                reviewer_login="reviewer-a",
                reviewer_body="Please rename this.",
                reply_candidates={
                    "ack": reply_candidate(
                        mode="update",
                        comment_id="self-3",
                        reason="adopt_latest_unmarked_reply_after_reviewer",
                        managed=False,
                        adopted_unmarked_reply=True,
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
                        comment_id="self-3",
                        author_login="codex",
                        body="Previous unmarked reply.",
                        created_at="2026-03-01T00:05:00Z",
                    )
                ],
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)

            result = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "defer",
                            "ack_mode": "update",
                            "ack_body": ack_reply_body(
                                decision="defer",
                                detail="Updating the previous reply into a managed defer acknowledgement.",
                            ),
                        }
                    ]
                },
                "ack",
            )

            self.assertTrue(result["valid"])
            self.assertEqual(result["normalized_thread_actions"][0]["ack_comment_id"], "self-3")
            self.assertEqual(result["counters"]["adopted_unmarked_reply_count"], 1)

    def test_validator_and_apply_enforce_fingerprint_and_normalized_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            raw_plan_path = tmp / "raw-plan.json"
            validated_path = tmp / "validated.json"
            write_json(context_path, context)
            write_json(
                raw_plan_path,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ]
                },
            )

            argv = [
                "validate_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(raw_plan_path),
                "--phase",
                "ack",
                "--output",
                str(validated_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(validate_plan.main(), 0)

            validated = json.loads(validated_path.read_text(encoding="utf-8"))
            self.assertTrue(validated["valid"])
            self.assertEqual(validated["context_fingerprint"], context["context_fingerprint"])

            stale_validated = dict(validated)
            stale_validated["context_fingerprint"] = "stale"
            stale_path = tmp / "stale-validated.json"
            write_json(stale_path, stale_validated)

            dry_run_path = tmp / "dry-run.json"
            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(validated_path),
                "--phase",
                "ack",
                "--dry-run",
                "--result-output",
                str(dry_run_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(apply_plan.main(), 0)

            dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
            self.assertTrue(dry_run["dry_run"])
            self.assertEqual(dry_run["normalized_thread_actions"][0]["thread_id"], "t-1")
            self.assertTrue(dry_run["fingerprint_match"])

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(raw_plan_path),
                "--phase",
                "ack",
                "--dry-run",
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaises(RuntimeError):
                    apply_plan.main()

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(stale_path),
                "--phase",
                "ack",
                "--dry-run",
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaises(RuntimeError):
                    apply_plan.main()

    def test_validator_and_apply_preserve_reconciliation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            raw_plan_path = tmp / "raw-plan.json"
            validated_path = tmp / "validated.json"
            dry_run_path = tmp / "dry-run.json"
            write_json(context_path, context)
            write_json(
                raw_plan_path,
                {
                    "context_fingerprint": context["context_fingerprint"],
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "complete_mode": "add",
                            "complete_body": "Current HEAD already covers the requested change.",
                            "resolve_after_complete": True,
                        }
                    ],
                    "reconciliation_summary": {
                        "outdated_transition_candidates": 1,
                        "outdated_auto_resolved": 1,
                        "outdated_recheck_ambiguous": 0,
                        "outdated_still_applicable": 0,
                    },
                },
            )

            argv = [
                "validate_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(raw_plan_path),
                "--phase",
                "complete",
                "--output",
                str(validated_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(validate_plan.main(), 0)

            validated = json.loads(validated_path.read_text(encoding="utf-8"))
            self.assertEqual(
                validated["reconciliation_summary"],
                {
                    "outdated_transition_candidates": 1,
                    "outdated_auto_resolved": 1,
                    "outdated_recheck_ambiguous": 0,
                    "outdated_still_applicable": 0,
                },
            )

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(validated_path),
                "--phase",
                "complete",
                "--dry-run",
                "--result-output",
                str(dry_run_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(apply_plan.main(), 0)

            dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
            self.assertEqual(dry_run["reconciliation_summary"]["outdated_auto_resolved"], 1)
            self.assertEqual(dry_run["reconciliation_summary"]["outdated_transition_candidates"], 1)

    def test_apply_skips_duplicate_add_when_live_exact_managed_reply_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            validated_path = tmp / "validated.json"
            result_path = tmp / "result.json"
            write_json(context_path, context)

            validated = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ]
                },
                "ack",
            )
            self.assertTrue(validated["valid"])
            write_json(validated_path, validated)

            calls: list[tuple[str, dict[str, str]]] = []

            def fake_graphql(_repo_root: Path, query: str, variables: dict[str, str]) -> dict[str, object]:
                calls.append((query, dict(variables)))
                if query == apply_plan.LIVE_THREAD_QUERY:
                    return {
                        "data": {
                            "viewer": {"login": "codex"},
                            "node": {
                                "id": "t-1",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "ack-1",
                                            "body": (
                                                "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\n"
                                                "Acknowledging the current thread-local plan.\n"
                                                "accept\n"
                                                "Will fix this."
                                            ),
                                            "createdAt": "2026-03-01T01:00:00Z",
                                            "updatedAt": "2026-03-01T01:00:00Z",
                                            "url": "https://example.invalid/comment/ack-1",
                                            "author": {"login": "codex"},
                                        }
                                    ]
                                },
                            },
                        }
                    }
                raise AssertionError("duplicate-preflight path should not execute a mutation")

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(validated_path),
                "--phase",
                "ack",
                "--result-output",
                str(result_path),
            ]
            with patch.object(sys, "argv", argv), patch.object(apply_plan, "graphql", side_effect=fake_graphql):
                self.assertEqual(apply_plan.main(), 0)

            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["results"][0]["operation"], "skip_existing_reply")
            self.assertEqual(result["results"][0]["reason"], "live_exact_managed_reply_already_matches")
            self.assertEqual(result["mutations"], [])
            self.assertIsNone(result["mutation_type"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1], {"threadId": "t-1"})

    def test_apply_blocks_add_when_live_exact_managed_reply_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            threads = [
                review_thread(thread_id="t-1", path="src/app.py", line=10, reviewer_login="reviewer-a", reviewer_body="Please rename this.")
            ]
            context = context_with_threads(tmp, threads)
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            validated_path = tmp / "validated.json"
            write_json(context_path, context)

            validated = validate_thread_action_payload(
                context,
                {
                    "thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ]
                },
                "ack",
            )
            self.assertTrue(validated["valid"])
            write_json(validated_path, validated)

            def fake_graphql(_repo_root: Path, query: str, _variables: dict[str, str]) -> dict[str, object]:
                if query == apply_plan.LIVE_THREAD_QUERY:
                    return {
                        "data": {
                            "viewer": {"login": "codex"},
                            "node": {
                                "id": "t-1",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "ack-1",
                                            "body": "<!-- codex:review-thread v1 phase=ack thread=t-1 -->\nAlready replied with different text.",
                                            "createdAt": "2026-03-01T01:00:00Z",
                                            "updatedAt": "2026-03-01T01:00:00Z",
                                            "url": "https://example.invalid/comment/ack-1",
                                            "author": {"login": "codex"},
                                        }
                                    ]
                                },
                            },
                        }
                    }
                raise AssertionError("conflict-preflight path should not execute a mutation")

            argv = [
                "apply_thread_action_plan.py",
                "--context",
                str(context_path),
                "--plan",
                str(validated_path),
                "--phase",
                "ack",
            ]
            with patch.object(sys, "argv", argv), patch.object(apply_plan, "graphql", side_effect=fake_graphql):
                with self.assertRaises(RuntimeError) as exc_info:
                    apply_plan.main()
            self.assertIn("live exact managed ack reply already exists", str(exc_info.exception))


if __name__ == "__main__":
    unittest.main()
