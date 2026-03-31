from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import collect_review_threads as collect  # type: ignore  # noqa: E402
from review_thread_test_support import comment  # noqa: E402


class CollectReviewThreadsTests(unittest.TestCase):
    def test_ensure_gh_auth_wraps_missing_gh_binary(self) -> None:
        with mock.patch.object(collect.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(RuntimeError) as exc_info:
                collect.ensure_gh_auth(Path("."))
        self.assertEqual(str(exc_info.exception), "gh auth status failed; run `gh auth login` first")

    def test_load_changed_files_uses_diff_output_when_available(self) -> None:
        with mock.patch.object(
            collect,
            "run_command",
            return_value="src/foo.py\nsrc/bar.py\n",
        ) as run_command:
            result = collect.load_changed_files(Path("."), "owner/repo", 7)

        self.assertEqual(result, ["src/foo.py", "src/bar.py"])
        run_command.assert_called_once_with(
            ["gh", "pr", "diff", "7", "--name-only", "--repo", "owner/repo"],
            cwd=Path("."),
        )

    def test_load_changed_files_falls_back_to_api_when_pr_diff_is_too_large(self) -> None:
        with mock.patch.object(
            collect,
            "run_command",
            side_effect=[
                RuntimeError(
                    "gh pr diff 7 --name-only --repo owner/repo: "
                    "could not find pull request diff: HTTP 406: Sorry, the diff exceeded "
                    "the maximum number of lines (20000)\nPullRequest.diff too_large"
                ),
                "src/foo.py\nsrc/bar.py\n",
            ],
        ) as run_command:
            result = collect.load_changed_files(Path("."), "owner/repo", 7)

        self.assertEqual(result, ["src/foo.py", "src/bar.py"])
        self.assertEqual(run_command.call_count, 2)
        self.assertEqual(
            run_command.call_args_list[1].args[0],
            [
                "gh",
                "api",
                "repos/owner/repo/pulls/7/files",
                "--paginate",
                "--jq",
                ".[].filename",
            ],
        )

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
