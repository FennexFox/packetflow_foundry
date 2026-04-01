from __future__ import annotations

import sys
import unittest
from subprocess import CompletedProcess
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import apply_commit_plan as apply_commit  # noqa: E402
import validate_commit_plan as validator  # noqa: E402


def sample_worktree() -> dict[str, object]:
    return {
        "repo_root": "C:/repo",
        "pathspecs": [],
        "head_commit": "abc123",
        "worktree_fingerprint": "sha256:worktree",
        "files": [],
    }


def sample_validation_payload() -> dict[str, object]:
    normalized_plan = {
        "repo_root": "C:/repo",
        "base_head": "abc123",
        "worktree_fingerprint": "sha256:worktree",
        "input_scope": "all-local-changes",
        "overall_confidence": "high",
        "validation_commands": ["python -m unittest"],
        "omitted_paths": [],
        "stop_reasons": [],
        "commits": [
            {
                "commit_index": 1,
                "intent_summary": "Update app behavior.",
                "type": "fix",
                "scope": "core",
                "subject": "normalized subject",
                "body": ["- keep normalized output"],
                "whole_file_paths": ["src/app.py"],
                "untracked_paths": [],
                "split_paths": [],
                "selected_hunk_ids": [],
                "supporting_paths": [],
                "targeted_checks": ["python -m unittest"],
                "confidence": "high",
            }
        ],
    }
    return {
        "valid": True,
        "can_apply": True,
        "normalized_plan": normalized_plan,
        "normalized_plan_fingerprint": validator.json_fingerprint(normalized_plan),
        "apply_gate_status": {
            "status": "pass",
            "applicable_stop_categories": ["stale_context", "validator_mismatch", "unresolved_stop_reason"],
            "covered_stop_categories": ["stale_context", "validator_mismatch", "unresolved_stop_reason"],
            "uncovered_stop_categories": [],
            "not_applicable_stop_categories": ["missing_auth", "missing_required_evidence"],
        },
    }


def sample_multi_commit_validation_payload() -> dict[str, object]:
    payload = sample_validation_payload()
    payload["normalized_plan"] = {
        **payload["normalized_plan"],
        "commits": [
            payload["normalized_plan"]["commits"][0],
            {
                "commit_index": 2,
                "intent_summary": "Follow-up change.",
                "type": "fix",
                "scope": "core",
                "subject": "second normalized subject",
                "body": ["- follow up"],
                "whole_file_paths": ["src/other.py"],
                "untracked_paths": [],
                "split_paths": [],
                "selected_hunk_ids": [],
                "supporting_paths": [],
                "targeted_checks": ["python -m unittest"],
                "confidence": "high",
            },
        ],
    }
    payload["normalized_plan_fingerprint"] = validator.json_fingerprint(payload["normalized_plan"])
    return payload


class ApplyCommitPlanContractTests(unittest.TestCase):
    def test_dry_run_consumes_validator_normalized_plan_only(self) -> None:
        worktree = sample_worktree()
        validation_payload = sample_validation_payload()

        def fake_validate(worktree_arg: dict[str, object], plan_arg: dict[str, object]) -> dict[str, object]:
            self.assertEqual(plan_arg["commits"][0]["subject"], "normalized subject")
            return {
                "valid": True,
                "can_apply": True,
                "deduped_validation_commands": ["python -m unittest"],
                "normalized_plan_fingerprint": validation_payload["normalized_plan_fingerprint"],
            }

        with (
            patch.object(apply_commit, "validate_plan_against_worktree", side_effect=fake_validate),
            patch.object(apply_commit, "detect_operation", return_value=None),
            patch.object(
                apply_commit,
                "run_git",
                return_value=CompletedProcess(["git", "rev-parse", "HEAD"], 0, stdout="abc123\n", stderr=""),
            ),
        ):
            payload = apply_commit.apply_validated_plan(worktree, validation_payload, dry_run=True)

        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["validation_source"], "validator_normalized_plan")
        self.assertEqual(payload["commits"][0]["subject"], "fix(core): normalized subject")
        self.assertEqual(payload["apply_status"]["status"], "dry_run")
        self.assertIsNone(payload["apply_status"]["stop_category"])

    def test_apply_rejects_mismatched_normalized_plan_fingerprint(self) -> None:
        worktree = sample_worktree()
        validation_payload = sample_validation_payload()
        validation_payload["normalized_plan_fingerprint"] = "sha256:not-the-same"

        with self.assertRaisesRegex(RuntimeError, "normalized-plan fingerprint"):
            apply_commit.apply_validated_plan(worktree, validation_payload, dry_run=True)

    def test_apply_rejects_active_git_operation_with_explicit_category(self) -> None:
        worktree = sample_worktree()
        validation_payload = sample_validation_payload()

        with (
            patch.object(apply_commit, "validate_plan_against_worktree", return_value={
                "valid": True,
                "can_apply": True,
                "deduped_validation_commands": [],
                "normalized_plan_fingerprint": validation_payload["normalized_plan_fingerprint"],
            }),
            patch.object(apply_commit, "detect_operation", return_value="rebase"),
        ):
            with self.assertRaises(apply_commit.ApplyHardStop) as caught:
                apply_commit.apply_validated_plan(worktree, validation_payload, dry_run=True)

        self.assertEqual(caught.exception.category, "active_git_operation")
        self.assertEqual(caught.exception.payload["apply_status"]["stop_category"], "active_git_operation")

    def test_run_targeted_checks_rejects_unavailable_command_before_execution(self) -> None:
        with patch.object(apply_commit, "command_feasibility_issues", return_value=[{
            "command": "missing-tool --version",
            "detail": "command executable `missing-tool` is unavailable on PATH",
        }]):
            with self.assertRaises(apply_commit.ApplyHardStop) as caught:
                apply_commit.run_targeted_checks(Path("C:/repo"), ["missing-tool --version"])

        self.assertEqual(caught.exception.category, "targeted_check_unavailable")

    def test_current_hunk_match_raises_ambiguous_split_rematch(self) -> None:
        original_hunk = {"hunk_id": "H1", "removed_digest": "same-old", "added_digest": "same-new"}
        current_hunks = [
            {"hunk_id": "A", "removed_digest": "same-old", "added_digest": "same-new"},
            {"hunk_id": "B", "removed_digest": "same-old", "added_digest": "same-new"},
        ]

        with self.assertRaises(apply_commit.ApplyHardStop) as caught:
            apply_commit.current_hunk_match("src/app.py", original_hunk, current_hunks)

        self.assertEqual(caught.exception.category, "ambiguous_split_rematch")

    def test_apply_rolls_back_created_commits_when_later_step_fails(self) -> None:
        worktree = sample_worktree()
        validation_payload = sample_multi_commit_validation_payload()

        def fake_validate(worktree_arg: dict[str, object], plan_arg: dict[str, object]) -> dict[str, object]:
            self.assertEqual(len(plan_arg["commits"]), 2)
            return {
                "valid": True,
                "can_apply": True,
                "deduped_validation_commands": ["python -m unittest"],
                "normalized_plan_fingerprint": validation_payload["normalized_plan_fingerprint"],
            }

        def fake_run_git(repo: Path, args: list[str], **_: object) -> CompletedProcess[str]:
            if args == ["rev-parse", "HEAD"]:
                return CompletedProcess(["git", *args], 0, stdout="abc123\n", stderr="")
            if args == ["diff", "--cached", "--name-only"]:
                return CompletedProcess(["git", *args], 0, stdout="src/app.py\n", stderr="")
            if args[:2] == ["commit", "--no-gpg-sign"]:
                return CompletedProcess(["git", *args], 0, stdout="", stderr="")
            if args[:2] == ["reset", "--mixed"]:
                return CompletedProcess(["git", *args], 0, stdout="", stderr="")
            return CompletedProcess(["git", *args], 0, stdout="", stderr="")

        with (
            patch.object(apply_commit, "validate_plan_against_worktree", side_effect=fake_validate),
            patch.object(apply_commit, "detect_operation", return_value=None),
            patch.object(apply_commit, "run_targeted_checks", return_value=None),
            patch.object(apply_commit, "reset_index", return_value=None),
            patch.object(apply_commit, "build_hunk_lookup", return_value={}),
            patch.object(apply_commit, "created_commit_hash", return_value="commit-1"),
            patch.object(apply_commit, "run_git", side_effect=fake_run_git),
            patch.object(apply_commit, "stage_commit", side_effect=[None, RuntimeError("second commit failed")]),
            patch.object(apply_commit, "rollback_created_commits") as mocked_rollback,
        ):
            with self.assertRaisesRegex(apply_commit.ApplyHardStop, "second commit failed"):
                apply_commit.apply_validated_plan(worktree, validation_payload, dry_run=False)

        mocked_rollback.assert_called_once_with(Path("C:/repo"), "abc123")

    def test_stage_commit_does_not_stage_supporting_paths(self) -> None:
        commit = {
            "whole_file_paths": ["src/app.py"],
            "untracked_paths": ["src/new_file.py"],
            "supporting_paths": ["docs/context.md"],
            "selected_hunk_ids": [],
            "split_paths": [],
        }

        with patch.object(apply_commit, "run_git") as mocked_run_git:
            apply_commit.stage_commit(Path("C:/repo"), commit, {})

        self.assertEqual(
            [call.args[1] for call in mocked_run_git.call_args_list],
            [
                ["add", "--all", "--", "src/app.py"],
                ["add", "--all", "--", "src/new_file.py"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
