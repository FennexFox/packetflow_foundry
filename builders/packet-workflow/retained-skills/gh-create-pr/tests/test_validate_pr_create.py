from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_create_contract as contract  # noqa: E402
import validate_pr_create as validator  # noqa: E402


def collected_context(repo_root: Path, *, repo_slug: str = "owner/repo") -> dict:
    return {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "resolved_head": "feature/pr-create",
        "resolved_base": "main",
        "local_head_oid": "abc123",
        "remote_head_oid": "abc123",
        "changed_files": ["src/creator.py", "tests/test_creator.py"],
        "changed_files_fingerprint": contract.json_fingerprint(["src/creator.py", "tests/test_creator.py"]),
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["src/creator.py"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 0, "sample_files": []},
            "tests": {"count": 1, "sample_files": ["tests/test_creator.py"]},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
        "template_selection": {
            "status": "selected",
            "selected_path": "C:/repo/.github/pull_request_template.md",
            "fingerprint": contract.json_fingerprint("template"),
        },
        "expected_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "issue_reference_hints": {"numbers": ["42"], "branch": "feature/pr-create", "commit_subjects": []},
        "testing_signal_candidates": {"exact_commands": [], "supports_positive_testing_claims": False, "test_files_changed": True},
        "create_options": {
            "reviewers": ["Alice", "alice", "bob, alice"],
            "assignees": ["Carol", "carol"],
            "labels": ["automation", "automation", "docs"],
            "milestone": "v1",
            "draft": True,
            "no_maintainer_edit": True,
        },
        "checks": {
            "repo_slug_resolved": bool(repo_slug),
            "base_resolved": True,
            "remote_head_exists": True,
            "local_remote_match": True,
            "template_selected": True,
        },
        "duplicate_check_hint": {"status": "clear", "matched_repo_slug": repo_slug, "matched_head": "feature/pr-create"},
        "diff_stat": " 2 files changed, 4 insertions(+), 1 deletion(-)",
    }


def valid_body() -> str:
    return "\n".join(
        [
            "## Why",
            "Open a guarded PR from a pushed branch.",
            "## What changed",
            "- Added validator-normalized create flow.",
            "- Re-check duplicate and template state before create.",
            "## How",
            "- Keep create fail-closed on stale snapshots.",
            "## Risk / Rollback",
            "- Refresh branch state and rerun validation.",
            "## Testing",
            "- Not run.",
            "Refs: #42",
        ]
    )


class ValidatePrCreateTests(unittest.TestCase):
    def test_validator_rejects_repo_inference_failure_before_gh_calls(self) -> None:
        context = collected_context(Path.cwd(), repo_slug="")
        with mock.patch.object(
            validator.tools,
            "run_command",
            side_effect=AssertionError("gh command should not run when repo inference already failed"),
        ):
            payload = validator.validate_pr_create(
                context,
                "feat(pr-create): create guarded PRs",
                valid_body(),
            )

        self.assertFalse(payload["valid"])
        self.assertIn("repo_inference_failed", payload["stop_reasons"])

    def test_validator_rejects_invalid_title_before_gh_calls(self) -> None:
        context = collected_context(Path.cwd())
        with mock.patch.object(
            validator.tools,
            "run_command",
            side_effect=AssertionError("gh command should not run for invalid candidate lint"),
        ):
            payload = validator.validate_pr_create(context, "bad title", valid_body())

        self.assertFalse(payload["valid"])
        self.assertIn("invalid_title", payload["stop_reasons"])

    def test_validator_flags_unsupported_claims(self) -> None:
        context = collected_context(Path.cwd())
        body = valid_body().replace("- Not run.", "- Ran `python -m pytest`.")
        with mock.patch.object(
            validator.tools,
            "run_command",
            side_effect=AssertionError("gh command should not run once unsupported claims are detected"),
        ):
            payload = validator.validate_pr_create(
                context,
                "feat(pr-create): create guarded PRs",
                body,
            )

        self.assertFalse(payload["valid"])
        self.assertIn("unsupported_claim", payload["stop_reasons"])

    def test_validator_rejects_existing_open_pr_on_live_duplicate_check(self) -> None:
        context = collected_context(Path.cwd())
        with (
            mock.patch.object(validator.tools, "run_command", return_value="Logged in to github.com"),
            mock.patch.object(validator.tools, "local_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "remote_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "load_changed_files_between", return_value=context["changed_files"]),
            mock.patch.object(validator.tools, "select_pr_template", return_value=context["template_selection"]),
            mock.patch.object(
                validator.tools,
                "duplicate_check_summary",
                return_value={
                    "status": "existing-open-pr",
                    "matched_repo_slug": "owner/repo",
                    "matched_head": "feature/pr-create",
                    "existing_pr_number": 9,
                    "existing_pr_url": "https://example.invalid/pr/9",
                    "existing_pr_count": 1,
                },
            ),
        ):
            payload = validator.validate_pr_create(
                context,
                "feat(pr-create): create guarded PRs",
                valid_body(),
            )

        self.assertFalse(payload["valid"])
        self.assertIn("existing_open_pr", payload["stop_reasons"])

    def test_validator_emits_normalized_create_request_when_candidate_is_apply_safe(self) -> None:
        context = collected_context(Path.cwd())
        with (
            mock.patch.object(validator.tools, "run_command", return_value="Logged in to github.com"),
            mock.patch.object(validator.tools, "local_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "remote_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "load_changed_files_between", return_value=context["changed_files"]),
            mock.patch.object(validator.tools, "select_pr_template", return_value=context["template_selection"]),
            mock.patch.object(
                validator.tools,
                "duplicate_check_summary",
                return_value={
                    "status": "clear",
                    "matched_repo_slug": "owner/repo",
                    "matched_head": "feature/pr-create",
                    "existing_pr_count": 0,
                },
            ),
        ):
            payload = validator.validate_pr_create(
                context,
                "feat(pr-create): create guarded PRs",
                valid_body(),
            )

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])
        normalized = payload["normalized_create_request"]
        self.assertEqual(normalized["reviewers"], ["alice", "bob"])
        self.assertEqual(normalized["assignees"], ["carol"])
        self.assertEqual(normalized["labels"], ["automation", "docs"])
        self.assertEqual(normalized["milestone"], "v1")
        self.assertFalse(normalized["maintainer_can_modify"])
        self.assertEqual(
            sorted(normalized["validated_snapshot"].keys()),
            sorted(
                [
                    "local_head_oid",
                    "remote_head_oid",
                    "repo_slug",
                    "base_ref",
                    "head_ref",
                    "changed_files_fingerprint",
                    "template_path",
                    "template_fingerprint",
                    "duplicate_check_summary",
                ]
            ),
        )

    def test_validator_rejects_stale_snapshot_when_changed_files_drift(self) -> None:
        context = collected_context(Path.cwd())
        with (
            mock.patch.object(validator.tools, "run_command", return_value="Logged in to github.com"),
            mock.patch.object(validator.tools, "local_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "remote_head_oid", return_value="abc123"),
            mock.patch.object(validator.tools, "load_changed_files_between", return_value=context["changed_files"] + ["README.md"]),
            mock.patch.object(validator.tools, "select_pr_template", return_value=context["template_selection"]),
            mock.patch.object(
                validator.tools,
                "duplicate_check_summary",
                return_value={
                    "status": "clear",
                    "matched_repo_slug": "owner/repo",
                    "matched_head": "feature/pr-create",
                    "existing_pr_count": 0,
                },
            ),
        ):
            payload = validator.validate_pr_create(
                context,
                "feat(pr-create): create guarded PRs",
                valid_body(),
            )

        self.assertFalse(payload["valid"])
        self.assertIn("stale_snapshot", payload["stop_reasons"])
        self.assertEqual(payload["stale_fields"][0]["field"], "changed_files_fingerprint")


if __name__ == "__main__":
    unittest.main()
