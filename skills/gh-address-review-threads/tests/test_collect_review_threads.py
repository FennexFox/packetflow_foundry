from __future__ import annotations

import sys
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import collect_review_threads as collect  # noqa: E402
from review_thread_test_support import comment  # noqa: E402


class CollectReviewThreadsTests(unittest.TestCase):
    def test_build_reply_candidates_prefers_exact_managed_and_marks_duplicate_warning(self) -> None:
        comments = [
            comment(
                comment_id="review-1",
                author_login="reviewer",
                body="Please rename this helper.",
                created_at="2026-03-01T00:00:00Z",
                is_self=False,
            ),
            comment(
                comment_id="ack-1",
                author_login="codex",
                body="<!-- codex:review-thread v1 phase=ack thread=t-1 -->\nWorking on it.",
                created_at="2026-03-01T01:00:00Z",
                managed_phase="ack",
                managed_thread_id="t-1",
                has_exact_managed_marker=True,
            ),
            comment(
                comment_id="ack-2",
                author_login="codex",
                body="<!-- codex:review-thread v1 phase=ack thread=t-1 -->\nUpdated status.",
                created_at="2026-03-01T02:00:00Z",
                managed_phase="ack",
                managed_thread_id="t-1",
                has_exact_managed_marker=True,
            ),
        ]

        reply_candidates, marker_conflicts, latest_self_reply, latest_reviewer_at = collect.build_reply_candidates(comments)

        self.assertEqual(reply_candidates["ack"]["mode"], "update")
        self.assertEqual(reply_candidates["ack"]["comment_id"], "ack-2")
        self.assertTrue(reply_candidates["ack"]["managed"])
        self.assertEqual(latest_self_reply["id"], "ack-2")
        self.assertEqual(latest_reviewer_at, "2026-03-01T00:00:00Z")
        self.assertEqual(
            marker_conflicts,
            [
                {
                    "phase": "ack",
                    "severity": "warning",
                    "reason": "duplicate_exact_managed_replies",
                    "comment_ids": ["ack-1"],
                    "blocks_adoption": False,
                    "blocks_update": False,
                    "blocks_apply": False,
                }
            ],
        )

    def test_build_reply_candidates_marks_adoption_blocking_for_multiple_unmarked_replies(self) -> None:
        comments = [
            comment(
                comment_id="review-1",
                author_login="reviewer",
                body="Please clarify this.",
                created_at="2026-03-01T00:00:00Z",
                is_self=False,
            ),
            comment(
                comment_id="self-1",
                author_login="codex",
                body="First unmarked reply.",
                created_at="2026-03-01T01:00:00Z",
            ),
            comment(
                comment_id="self-2",
                author_login="codex",
                body="Second unmarked reply.",
                created_at="2026-03-01T02:00:00Z",
            ),
        ]

        reply_candidates, marker_conflicts, _latest_self_reply, _latest_reviewer_at = collect.build_reply_candidates(comments)

        self.assertEqual(reply_candidates["ack"]["mode"], "update")
        self.assertEqual(reply_candidates["ack"]["comment_id"], "self-2")
        self.assertTrue(reply_candidates["ack"]["adopted_unmarked_reply"])
        self.assertEqual(marker_conflicts[0]["severity"], "adoption-blocking")
        self.assertEqual(marker_conflicts[0]["comment_ids"], ["self-1", "self-2"])

    def test_build_reply_candidates_marks_hard_stop_for_wrong_thread_marker(self) -> None:
        comments = [
            comment(
                comment_id="review-1",
                author_login="reviewer",
                body="Please fix this.",
                created_at="2026-03-01T00:00:00Z",
                is_self=False,
            ),
            comment(
                comment_id="bad-ack",
                author_login="codex",
                body="<!-- codex:review-thread v1 phase=ack thread=t-other -->\nWrong thread marker.",
                created_at="2026-03-01T01:00:00Z",
                managed_phase="ack",
                managed_thread_id="t-other",
                has_exact_managed_marker=False,
            ),
        ]

        _reply_candidates, marker_conflicts, _latest_self_reply, _latest_reviewer_at = collect.build_reply_candidates(comments)

        self.assertEqual(marker_conflicts[0]["severity"], "hard-stop")
        self.assertEqual(marker_conflicts[0]["reason"], "wrong_thread_managed_marker")
        self.assertTrue(marker_conflicts[0]["blocks_apply"])


if __name__ == "__main__":
    unittest.main()
