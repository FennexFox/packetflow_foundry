from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lint_pr_create as lint  # noqa: E402
from pr_create_test_support import REPO_TEMPLATE_SECTIONS  # noqa: E402

UNSUPPORTED_CLAIM_MESSAGE = (
    "Consumer migration or compatibility claims require direct runtime/process evidence and are blocked by default."
)


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
            "  - Claim-gate regressions.",
            "- Rollback / mitigation:",
            "  - Revert the create flow changes.",
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
        else ["- Keeps the validator aligned with the repository template."]
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


def collected_context() -> dict:
    return {
        "repo_root": str(Path.cwd()),
        "repo_slug": "owner/repo",
        "resolved_head": "feature/pr-create",
        "resolved_base": "main",
        "local_head_oid": "abc123",
        "remote_head_oid": "abc123",
        "changed_files": ["src/creator.py", "tests/test_creator.py"],
        "changed_files_fingerprint": "sha256:changed",
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["src/creator.py"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 0, "sample_files": []},
            "tests": {"count": 1, "sample_files": ["tests/test_creator.py"]},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
        "diff_stat": " 2 files changed, 4 insertions(+), 1 deletion(-)",
        "template_selection": {
            "status": "selected",
            "selected_path": "C:/repo/.github/pull_request_template.md",
            "fingerprint": "sha256:template",
        },
        "expected_template_sections": list(REPO_TEMPLATE_SECTIONS),
        "duplicate_check_hint": {"status": "clear", "matched_repo_slug": "owner/repo", "matched_head": "feature/pr-create"},
        "checks": {
            "repo_slug_resolved": True,
            "base_resolved": True,
            "remote_head_exists": True,
            "local_remote_match": True,
            "template_selected": True,
        },
        "issue_reference_hints": {
            "numbers": ["42"],
            "branch": "feature/pr-create",
            "commit_subjects": ["feat(pr-create): add guarded creator #42"],
        },
        "testing_signal_candidates": {
            "exact_commands": [],
            "operator_supplied": [],
            "supports_positive_testing_claims": False,
            "test_files_changed": True,
        },
        "instruction_snippets": {},
    }


def repo_template_context() -> dict:
    context = collected_context()
    context["issue_reference_hints"]["numbers"] = ["23"]
    context["issue_reference_hints"]["commit_subjects"] = ["fix(pr-create): align claim gates with template #23"]
    return context


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
    )


class LintPrCreateTests(unittest.TestCase):
    def assert_consumer_claim_blocked(self, claim_line: str) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "fix(pr-create): harden guarded flow",
            candidate_body(
                what_changed="- Tightened verifier comparisons.",
                why=["- Document the guarded create flow.", "- Refs: #42"],
                how=claim_line,
            ),
        )

        self.assertIn(UNSUPPORTED_CLAIM_MESSAGE, findings["detected"]["unsupported_claims"])

    def test_context_findings_flag_missing_default_template(self) -> None:
        context = collected_context()
        context["template_selection"] = {"status": "not_found", "selected_path": None, "fingerprint": ""}
        context["checks"]["template_selected"] = False

        findings = lint.collect_context_findings(context)

        self.assertIn("No unique default PR template was found.", findings["errors"])

    def test_candidate_findings_block_positive_testing_claim_without_external_command(self) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "feat(pr-create): create guarded PRs",
            candidate_body(
                what_changed="- Added validator/apply gates.",
                why=["- Open a guarded PR.", "- Refs: #42"],
                how="- Keep create fail-closed.",
                testing=[
                    "- Validation / tests:",
                    "  - Ran `python -m pytest`.",
                    "- Manual review:",
                    "  - Not needed.",
                ],
                risk=[
                    "- Risk areas:",
                    "  - Validation could drift.",
                    "- Rollback / mitigation:",
                    "  - Re-run validation.",
                ],
            ),
        )

        self.assertIn(
            "Positive testing claims cite commands that are not grounded in the testing packet.",
            findings["detected"]["unsupported_claims"],
        )

    def test_candidate_findings_allow_no_behavior_change_when_runtime_packet_is_empty(self) -> None:
        context = collected_context()
        context["changed_file_groups"]["runtime"]["count"] = 0
        context["changed_file_groups"]["runtime"]["sample_files"] = []
        context["changed_files"] = ["README.md"]

        findings = lint.collect_candidate_findings(
            context,
            "docs(pr-create): document guarded create flow",
            candidate_body(
                what_changed="- Updated docs only.",
                why=["- Document the create flow.", "- Refs: #42"],
                how="- No behavior change.",
                risk=[
                    "- Risk areas:",
                    "  - Docs-only drift.",
                    "- Rollback / mitigation:",
                    "  - Revert the docs text.",
                ],
                classification="- [x] Docs",
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_allow_positive_testing_claim_with_trusted_command(self) -> None:
        context = collected_context()
        context["testing_signal_candidates"]["exact_commands"] = ["python -m pytest"]
        context["testing_signal_candidates"]["operator_supplied"] = ["python -m pytest"]
        context["testing_signal_candidates"]["supports_positive_testing_claims"] = True

        findings = lint.collect_candidate_findings(
            context,
            "feat(pr-create): create guarded PRs",
            "\n".join(
                [
                    "## Why",
                    "Open a guarded PR.",
                    "## What changed",
                    "- Added validator/apply gates.",
                    "## How",
                    "- Keep create fail-closed.",
                    "## Risk / Rollback",
                    "- Re-run validation.",
                    "## Testing",
                    "- Ran `python -m pytest`.",
                    "Refs: #42",
                ]
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_block_issue_reference_without_hint(self) -> None:
        context = collected_context()
        context["issue_reference_hints"]["numbers"] = []

        findings = lint.collect_candidate_findings(
            context,
            "feat(pr-create): create guarded PRs",
            candidate_body(
                what_changed="- Added validator/apply gates.",
                why=["- Open a guarded PR.", "- Refs: #42"],
                how="- Keep create fail-closed.",
                risk=[
                    "- Risk areas:",
                    "  - Validation could drift.",
                    "- Rollback / mitigation:",
                    "  - Re-run validation.",
                ],
            ),
        )

        self.assertIn(
            "Issue references are present without matching issue hints from the process packet.",
            findings["detected"]["unsupported_claims"],
        )

    def test_candidate_findings_allow_canonicalized_issue_refs(self) -> None:
        context = collected_context()
        context["issue_reference_hints"]["numbers"] = ["1"]

        findings = lint.collect_candidate_findings(
            context,
            "feat(pr-create): create guarded PRs",
            candidate_body(
                what_changed="- Added validator/apply gates.",
                why=["- Open a guarded PR.", "- Refs: #01", "- Fixes: #01"],
                how="- Keep create fail-closed.",
                risk=[
                    "- Risk areas:",
                    "  - Validation could drift.",
                    "- Rollback / mitigation:",
                    "  - Re-run validation.",
                ],
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_allow_internal_migration_batch_wording(self) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "fix(pr-create): harden guarded flow",
            candidate_body(
                what_changed="- Tightened verifier comparisons.",
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
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_allow_internal_operator_migration_note_wording(self) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "fix(pr-create): harden guarded flow",
            candidate_body(
                what_changed="- Tightened verifier comparisons.",
                why=["- Document the guarded create flow for maintainers.", "- Refs: #42"],
                how="- Requires migration note for internal operators.",
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_allow_internal_compatibility_note_wording(self) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "fix(pr-create): harden guarded flow",
            candidate_body(
                what_changed="- Tightened verifier comparisons.",
                why=["- Document the guarded create flow for maintainers.", "- Refs: #42"],
                how="- Compatible with internal tooling.",
            ),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_flag_present_but_empty_testing_section(self) -> None:
        findings = lint.collect_candidate_findings(
            collected_context(),
            "fix(pr-create): harden guarded flow",
            candidate_body(
                what_changed="- Tightened verifier comparisons.",
                why=["- Document the guarded create flow for maintainers.", "- Refs: #42"],
                how="- Keep the migrated workflow shape local to the retained skill boundary.",
                testing="",
            ),
        )

        self.assertIn("`Testing` is present but empty.", findings["detected"]["body_errors"])

    def test_candidate_findings_allow_unchecked_repo_template_migration_checkbox(self) -> None:
        findings = lint.collect_candidate_findings(
            repo_template_context(),
            "fix(pr-create): align claim gates with template",
            repo_template_checkbox_body(migration_checkbox=" "),
        )

        self.assertEqual(findings["detected"]["unsupported_claims"], [])

    def test_candidate_findings_block_checked_repo_template_migration_checkbox(self) -> None:
        findings = lint.collect_candidate_findings(
            repo_template_context(),
            "fix(pr-create): align claim gates with template",
            repo_template_checkbox_body(migration_checkbox="x"),
        )

        self.assertIn(UNSUPPORTED_CLAIM_MESSAGE, findings["detected"]["unsupported_claims"])

    def test_candidate_findings_block_consumer_migration_claim(self) -> None:
        self.assert_consumer_claim_blocked("- Requires a migration note for vendored consumers.")

    def test_candidate_findings_block_qualified_consumer_migration_claim(self) -> None:
        self.assert_consumer_claim_blocked("- Requires migration for all consumers.")

    def test_candidate_findings_block_consumer_compatibility_claim(self) -> None:
        self.assert_consumer_claim_blocked("- Consumers require backward compatibility.")

    def test_candidate_findings_block_direct_consumer_migration_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Requires migration for consumers.")

    def test_candidate_findings_block_subject_first_consumer_migration_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Existing users must migrate.")

    def test_candidate_findings_block_subject_first_consumer_should_migrate_claim(self) -> None:
        self.assert_consumer_claim_blocked("- Existing users should migrate.")

    def test_candidate_findings_block_passive_voice_consumer_migration_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Consumers are required to migrate.")

    def test_candidate_findings_block_by_audience_consumer_migration_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Requires migration by consumers.")

    def test_candidate_findings_block_copular_migration_subject_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Migration is required for consumers.")

    def test_candidate_findings_block_copular_audience_migration_requirement(self) -> None:
        self.assert_consumer_claim_blocked("- Consumer migration is required.")


if __name__ == "__main__":
    unittest.main()
