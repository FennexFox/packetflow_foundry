from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_commit_plan as validator  # noqa: E402


def sample_worktree() -> dict[str, object]:
    return {
        "repo_root": "C:/repo",
        "pathspecs": [],
        "head_commit": "abc123",
        "worktree_fingerprint": "sha256:worktree",
        "files": [
            {
                "path": "src/app.py",
                "change_kind": "modified",
                "split_eligible": True,
                "hunks": [
                    {
                        "hunk_id": "H1",
                        "old_start": 1,
                        "old_count": 1,
                        "new_start": 1,
                        "new_count": 1,
                        "removed_digest": "old",
                        "added_digest": "new",
                    }
                ],
            }
        ],
    }


def sample_plan() -> dict[str, object]:
    return {
        "repo_root": "C:/repo",
        "base_head": "abc123",
        "worktree_fingerprint": "sha256:worktree",
        "input_scope": "all-local-changes",
        "overall_confidence": "high",
        "validation_commands": ["python -m unittest"],
        "omitted_paths": [],
        "stop_reasons": [],
        "extra_field": "ignored",
        "commits": [
            {
                "commit_index": 1,
                "intent_summary": "Update app behavior.",
                "type": "fix",
                "scope": "core",
                "subject": "update app behavior",
                "body": "- update the app behavior\n- keep tests green",
                "whole_file_paths": ["src/app.py"],
                "untracked_paths": [],
                "split_paths": [],
                "selected_hunk_ids": [],
                "supporting_paths": [],
                "targeted_checks": ["python -m unittest"],
                "confidence": "high",
                "extra_commit_field": "ignored",
            }
        ],
    }


class ValidateCommitPlanContractTests(unittest.TestCase):
    def test_validator_normalizes_unknown_fields_and_emits_fixed_warning_codes(self) -> None:
        worktree = sample_worktree()
        plan = sample_plan()
        with patch.object(validator, "build_worktree_context", return_value=worktree):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])
        warning_codes = {item["code"] for item in payload["warning_details"]}
        self.assertIn(validator.VALIDATION_WARNING_CODES["unknown_top_level_field"], warning_codes)
        self.assertIn(validator.VALIDATION_WARNING_CODES["unknown_commit_field"], warning_codes)
        self.assertIn(validator.VALIDATION_WARNING_CODES["body_string_normalized"], warning_codes)
        self.assertNotIn("extra_field", payload["normalized_plan"])
        self.assertNotIn("extra_commit_field", payload["normalized_plan"]["commits"][0])
        self.assertTrue(str(payload["normalized_plan_fingerprint"]).startswith("sha256:"))
        self.assertEqual(
            payload["apply_gate_status"]["covered_stop_categories"],
            [
                "active_git_operation",
                "ambiguous_split_rematch",
                "low_confidence",
                "partial_split_unsupported",
                "stale_context",
                "targeted_check_unavailable",
                "validator_mismatch",
                "unresolved_stop_reason",
            ],
        )
        self.assertEqual(
            payload["apply_gate_status"]["local_hard_stop_categories"],
            [
                "active_git_operation",
                "ambiguous_split_rematch",
                "commit_creation_failed",
                "partial_split_unsupported",
                "rollback_failed",
                "targeted_check_failed",
                "targeted_check_unavailable",
                "validator_mismatch",
            ],
        )
        self.assertEqual(payload["stop_categories"], [])

    def test_validator_reports_stale_context_with_fixed_error_code(self) -> None:
        worktree = sample_worktree()
        plan = sample_plan()
        current_worktree = dict(worktree)
        current_worktree["worktree_fingerprint"] = "sha256:changed"
        with patch.object(validator, "build_worktree_context", return_value=current_worktree):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["fingerprint_changed"], error_codes)
        self.assertEqual(payload["apply_gate_status"]["status"], "fail")
        self.assertIn("stale_context", payload["stop_categories"])

    def test_validator_rejects_active_git_operation_with_explicit_stop_category(self) -> None:
        worktree = sample_worktree()
        plan = sample_plan()
        current_worktree = dict(worktree)
        current_worktree["active_operation"] = "rebase"
        with patch.object(validator, "build_worktree_context", return_value=current_worktree):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["active_git_operation"], error_codes)
        self.assertIn("active_git_operation", payload["stop_categories"])

    def test_validator_rejects_partial_split_unsupported_with_explicit_stop_category(self) -> None:
        worktree = sample_worktree()
        worktree["files"][0]["change_kind"] = "added"
        plan = sample_plan()
        plan["commits"][0]["whole_file_paths"] = []
        plan["commits"][0]["split_paths"] = ["src/app.py"]
        plan["commits"][0]["selected_hunk_ids"] = ["H1"]
        with patch.object(validator, "build_worktree_context", return_value=worktree):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["partial_split_unsupported"], error_codes)
        self.assertIn("partial_split_unsupported", payload["stop_categories"])

    def test_validator_rejects_ambiguous_split_rematch_with_explicit_stop_category(self) -> None:
        worktree = sample_worktree()
        worktree["files"][0]["hunks"] = [
            {
                "hunk_id": "H1",
                "old_start": 1,
                "old_count": 1,
                "new_start": 1,
                "new_count": 1,
                "removed_digest": "same-old",
                "added_digest": "same-new",
            },
            {
                "hunk_id": "H2",
                "old_start": 10,
                "old_count": 1,
                "new_start": 10,
                "new_count": 1,
                "removed_digest": "same-old",
                "added_digest": "same-new",
            },
        ]
        plan = sample_plan()
        plan["commits"][0]["whole_file_paths"] = []
        plan["commits"][0]["split_paths"] = ["src/app.py"]
        plan["commits"][0]["selected_hunk_ids"] = ["H1", "H2"]
        with patch.object(validator, "build_worktree_context", return_value=worktree):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["ambiguous_split_rematch"], error_codes)
        self.assertIn("ambiguous_split_rematch", payload["stop_categories"])

    def test_validator_rejects_targeted_check_when_command_is_unavailable(self) -> None:
        worktree = sample_worktree()
        plan = sample_plan()
        plan["validation_commands"] = ["missing-tool --version"]
        plan["commits"][0]["targeted_checks"] = ["missing-tool --version"]
        with (
            patch.object(validator, "build_worktree_context", return_value=worktree),
            patch.object(validator, "resolve_command_executable", return_value=None),
        ):
            payload = validator.validate_plan_against_worktree(worktree, plan)

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["targeted_check_unavailable"], error_codes)
        self.assertIn("targeted_check_unavailable", payload["stop_categories"])


if __name__ == "__main__":
    unittest.main()
