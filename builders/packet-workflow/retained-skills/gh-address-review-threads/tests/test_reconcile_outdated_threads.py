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

import reconcile_outdated_threads as reconcile  # type: ignore  # noqa: E402
from review_thread_test_support import context_with_threads, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


def packet_for_thread(
    thread: dict[str, object],
    *,
    transitioned_to_outdated: bool,
    resolution_verdict: str,
    verdict_reason: str,
    area: str,
    validation_commands: list[str],
    reply_update_basis: dict[str, object] | None = None,
) -> dict[str, object]:
    packet = {
        "thread": thread,
        "transitioned_to_outdated": transitioned_to_outdated,
        "outdated_recheck": {
            "validation_provenance": {"commands": validation_commands},
            "current_head_evidence": {
                "path": str(thread.get("path") or ""),
                "area": area,
            },
            "resolution_verdict": resolution_verdict,
            "verdict_reason": verdict_reason,
        },
    }
    if reply_update_basis is not None:
        packet["reply_update_basis"] = reply_update_basis
    return packet


class ReconcileOutdatedThreadsTests(unittest.TestCase):
    def test_reconcile_auto_accepts_docs_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="docs/guide.md",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please use the current wording.",
                is_outdated=True,
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            output_path = tmp / "plan.json"
            packet_dir.mkdir()
            write_json(context_path, context)
            write_json(
                packet_dir / "thread-01.json",
                packet_for_thread(
                    thread,
                    transitioned_to_outdated=True,
                    resolution_verdict="auto-accept",
                    verdict_reason="accepted_same_run_with_current_head_evidence",
                    area="docs",
                    validation_commands=["python -m pytest tests/test_docs.py"],
                ),
            )

            argv = [
                "reconcile_outdated_threads.py",
                "--context",
                str(context_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(reconcile.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            action = payload["thread_actions"][0]
            self.assertEqual(action["decision"], "accept")
            self.assertEqual(action["complete_mode"], "add")
            self.assertTrue(action["resolve_after_complete"])
            self.assertIn("Current HEAD already covers the requested wording change", action["complete_body"])
            self.assertIn("Validation: `python -m pytest tests/test_docs.py`.", action["complete_body"])
            self.assertEqual(payload["reconciliation_summary"]["outdated_transition_candidates"], 1)
            self.assertEqual(payload["reconciliation_summary"]["outdated_auto_resolved"], 1)
            self.assertEqual(payload["reconciliation_summary"]["outdated_recheck_ambiguous"], 0)

    def test_reconcile_auto_accepts_runtime_candidate_only_with_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/helper.py",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please fix the helper branch.",
                is_outdated=True,
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            output_path = tmp / "plan.json"
            packet_dir.mkdir()
            write_json(context_path, context)
            write_json(
                packet_dir / "thread-01.json",
                packet_for_thread(
                    thread,
                    transitioned_to_outdated=True,
                    resolution_verdict="auto-accept",
                    verdict_reason="accepted_same_run_with_current_head_evidence",
                    area="runtime",
                    validation_commands=["python -m pytest builders/consumer-bootstrap/tests/test_consumer_bootstrap.py"],
                ),
            )

            argv = [
                "reconcile_outdated_threads.py",
                "--context",
                str(context_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(reconcile.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            action = payload["thread_actions"][0]
            self.assertEqual(action["decision"], "accept")
            self.assertTrue(action["resolve_after_complete"])
            self.assertIn("requested change", action["complete_body"])

    def test_reconcile_auto_accept_updates_existing_completion_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="docs/guide.md",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please use the current wording.",
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            output_path = tmp / "plan.json"
            packet_dir.mkdir()
            write_json(context_path, context)
            write_json(
                packet_dir / "thread-01.json",
                packet_for_thread(
                    thread,
                    transitioned_to_outdated=True,
                    resolution_verdict="auto-accept",
                    verdict_reason="accepted_same_run_with_current_head_evidence",
                    area="docs",
                    validation_commands=["python -m pytest tests/test_docs.py"],
                    reply_update_basis={
                        "complete": {
                            "mode": "update",
                            "comment_id": "comment-123",
                            "reason": "managed_complete_reply_exists",
                            "managed": True,
                            "adopted_unmarked_reply": False,
                        }
                    },
                ),
            )

            argv = [
                "reconcile_outdated_threads.py",
                "--context",
                str(context_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(reconcile.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            action = payload["thread_actions"][0]
            self.assertEqual(action["decision"], "accept")
            self.assertEqual(action["complete_mode"], "update")
            self.assertEqual(action["complete_comment_id"], "comment-123")
            self.assertTrue(action["resolve_after_complete"])

    def test_reconcile_leaves_missing_validation_candidate_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/helper.py",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please fix the helper branch.",
                is_outdated=True,
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            output_path = tmp / "plan.json"
            packet_dir.mkdir()
            write_json(context_path, context)
            write_json(
                packet_dir / "thread-01.json",
                packet_for_thread(
                    thread,
                    transitioned_to_outdated=True,
                    resolution_verdict="ambiguous",
                    verdict_reason="missing_validation_provenance",
                    area="runtime",
                    validation_commands=[],
                ),
            )

            argv = [
                "reconcile_outdated_threads.py",
                "--context",
                str(context_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(reconcile.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            action = payload["thread_actions"][0]
            self.assertEqual(action["decision"], "defer-outdated")
            self.assertEqual(action["complete_mode"], "skip")
            self.assertFalse(action["resolve_after_complete"])
            self.assertEqual(payload["reconciliation_summary"]["outdated_auto_resolved"], 0)
            self.assertEqual(payload["reconciliation_summary"]["outdated_recheck_ambiguous"], 1)

    def test_reconcile_returns_still_applicable_candidate_to_normal_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            thread = review_thread(
                thread_id="t-1",
                path="src/helper.py",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please fix the helper branch.",
                is_outdated=True,
            )
            context = context_with_threads(tmp, [thread])
            context["context_fingerprint"] = build_context_fingerprint(context)
            context_path = tmp / "context.json"
            packet_dir = tmp / "packets"
            output_path = tmp / "plan.json"
            packet_dir.mkdir()
            write_json(context_path, context)
            write_json(
                packet_dir / "thread-01.json",
                packet_for_thread(
                    thread,
                    transitioned_to_outdated=True,
                    resolution_verdict="still-applies",
                    verdict_reason="thread_was_not_accepted_before_push",
                    area="runtime",
                    validation_commands=[],
                ),
            )

            argv = [
                "reconcile_outdated_threads.py",
                "--context",
                str(context_path),
                "--packet-dir",
                str(packet_dir),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(reconcile.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            action = payload["thread_actions"][0]
            self.assertEqual(action["decision"], "defer")
            self.assertEqual(action["complete_mode"], "skip")
            self.assertFalse(action["resolve_after_complete"])
            self.assertEqual(payload["reconciliation_summary"]["outdated_still_applicable"], 1)


if __name__ == "__main__":
    unittest.main()
