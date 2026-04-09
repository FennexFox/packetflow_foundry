from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_create_contract as contract  # noqa: E402
import validate_pr_create as validator  # noqa: E402


REPO_TEMPLATE_SECTIONS = [
    "What changed",
    "Why",
    "How",
    "Testing",
    "Compatibility / Adoption",
    "Risk / Rollback",
    "Reviewer Checklist",
    "PR Classification (optional)",
]


def _lines(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return list(value)


def candidate_body(
    *,
    what_changed: str | list[str],
    why: str | list[str],
    how: str | list[str],
    testing: str | list[str] | None = None,
    compatibility: str | list[str] | None = None,
    risk: str | list[str] | None = None,
    reviewer_checklist: str | list[str] | None = None,
    classification: str | list[str] | None = None,
    justification: str | list[str] | None = None,
) -> str:
    testing_lines = (
        _lines(testing)
        if testing is not None
        else [
            "- Validation / tests:",
            "  - Not run.",
            "- Manual review:",
            "  - Not applicable.",
        ]
    )
    compatibility_lines = (
        _lines(compatibility)
        if compatibility is not None
        else [
            "- Consumer / vendor impact:",
            "  - [x] None",
            "  - [ ] Requires regenerating builder output",
            "  - [ ] Requires updating project-local profiles or agents",
            "  - [ ] Requires a migration note for vendored consumers",
            "- Details:",
            "  - No additional consumer changes.",
        ]
    )
    risk_lines = (
        _lines(risk)
        if risk is not None
        else [
            "- Risk areas:",
            "  - Validation could drift from live branch or template state.",
            "- Rollback / mitigation:",
            "  - Refresh branch state and rerun validation.",
        ]
    )
    reviewer_lines = (
        _lines(reviewer_checklist)
        if reviewer_checklist is not None
        else [
            "- [x] Linked issue, design note, or release item when applicable",
            "- [x] Docs or templates updated if shared behavior changed",
            "- [x] Builder/tests updated with core contract/template/default changes",
            "- [x] Consumer impact called out when applicable",
            "- [x] Validation steps are specific enough to reproduce",
            "- [x] Risk and rollback are concrete when behavior could regress",
        ]
    )
    classification_lines = _lines(classification) if classification is not None else ["- [x] Bugfix"]
    justification_lines = (
        _lines(justification)
        if justification is not None
        else ["- Tightens the guarded PR create flow without widening the supported claim set."]
    )
    return "\n".join(
        [
            "## What changed",
            *_lines(what_changed),
            "## Why",
            *_lines(why),
            "## How",
            *_lines(how),
            "## Testing",
            *testing_lines,
            "## Compatibility / Adoption",
            *compatibility_lines,
            "## Risk / Rollback",
            *risk_lines,
            "## Reviewer Checklist",
            *reviewer_lines,
            "## PR Classification (optional)",
            *classification_lines,
            "",
            "Justification:",
            *justification_lines,
        ]
    )


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
        "expected_template_sections": list(REPO_TEMPLATE_SECTIONS),
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


def repo_template_context(repo_root: Path) -> dict:
    context = collected_context(repo_root)
    context["issue_reference_hints"] = {"numbers": ["23"], "branch": "feature/pr-create", "commit_subjects": []}
    return context


def valid_body() -> str:
    return candidate_body(
        what_changed=[
            "- Added validator-normalized create flow.",
            "- Re-check duplicate and template state before create.",
        ],
        why=["- Open a guarded PR from a pushed branch.", "- Refs: #42"],
        how="- Keep create fail-closed on stale snapshots.",
    )


def repo_template_checkbox_body(*, migration_checkbox: str) -> str:
    return candidate_body(
        what_changed="- Tightened compatibility claim gating.",
        why=["- Keep template-compatible PR bodies accepted.", "- Refs: #23"],
        how="- Keep authored consumer migration prose fail-closed.",
        testing=[
            "- Validation / tests:",
            "  - Not run.",
            "- Manual review:",
            "  - Not run.",
        ],
        compatibility=[
            "- Consumer / vendor impact:",
            "  - [ ] None",
            "  - [ ] Requires regenerating builder output",
            "  - [ ] Requires updating project-local profiles or agents",
            f"  - [{migration_checkbox}] Requires a migration note for vendored consumers",
            "- Details:",
            "  - None.",
        ],
        risk=[
            "- Risk areas:",
            "  - Claim-gate regressions.",
            "- Rollback / mitigation:",
            "  - Revert the lint update.",
        ],
        reviewer_checklist="- [x] Builder/tests updated with core contract/template/default changes",
        justification="- Keeps the validator aligned with the template.",
    )


def internal_migration_body() -> str:
    return candidate_body(
        what_changed=[
            "- Added validator-normalized create flow.",
            "- Re-check duplicate and template state before create.",
        ],
        why=[
            "- Complete the next internal migration slice for the guarded create flow.",
            "- Refs: #42",
        ],
        how="- Keep the migrated workflow shape local to the retained skill boundary.",
        risk=[
            "- Risk areas:",
            "  - Workflow-shape drift.",
            "- Rollback / mitigation:",
            "  - Revert if the migrated workflow shape drifts.",
        ],
    )


class ValidatePrCreateTests(unittest.TestCase):
    def assert_validator_rejects_consumer_claim(self, claim_line: str) -> None:
        context = collected_context(Path.cwd())
        body = valid_body().replace("- Keep create fail-closed on stale snapshots.", claim_line)
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
        body = valid_body().replace("  - Not run.", "  - Ran `python -m pytest`.", 1)
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

    def test_validator_rejects_direct_consumer_migration_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Requires migration for consumers.")

    def test_validator_rejects_subject_first_consumer_migration_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Existing users must migrate.")

    def test_validator_rejects_subject_first_consumer_should_migrate_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Existing users should migrate.")

    def test_validator_rejects_passive_voice_consumer_migration_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Consumers are required to migrate.")

    def test_validator_rejects_by_audience_consumer_migration_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Requires migration by consumers.")

    def test_validator_rejects_copular_migration_subject_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Migration is required for consumers.")

    def test_validator_rejects_copular_audience_migration_claim(self) -> None:
        self.assert_validator_rejects_consumer_claim("- Consumer migration is required.")

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

    def test_validator_allows_internal_migration_wording(self) -> None:
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
                internal_migration_body(),
            )

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])

    def test_validator_allows_unchecked_repo_template_migration_checkbox(self) -> None:
        context = repo_template_context(Path.cwd())
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
                "fix(pr-create): align claim gates with template",
                repo_template_checkbox_body(migration_checkbox=" "),
            )

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])

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

    def test_main_accepts_bom_prefixed_body_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = collected_context(tmp)
            context_path = tmp / "context.json"
            body_path = tmp / "candidate.md"
            output_path = tmp / "validation.json"
            context_path.write_text(json.dumps(context), encoding="utf-8")
            body_path.write_text(valid_body(), encoding="utf-8-sig")

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
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "validate_pr_create.py",
                        "--context",
                        str(context_path),
                        "--title",
                        "feat(pr-create): create guarded PRs",
                        "--body-file",
                        str(body_path),
                        "--output",
                        str(output_path),
                    ],
                ),
            ):
                self.assertEqual(validator.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["valid"])
            self.assertTrue(payload["can_apply"])
            self.assertFalse(payload["normalized_create_request"]["body"].startswith("\ufeff"))
            self.assertEqual(payload["normalized_create_request"]["body"].splitlines()[0], "## What changed")


if __name__ == "__main__":
    unittest.main()
