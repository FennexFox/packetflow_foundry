from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lint_pr_create as lint  # noqa: E402


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
        "expected_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
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
            "supports_positive_testing_claims": False,
            "test_files_changed": True,
        },
        "instruction_snippets": {},
    }


class LintPrCreateTests(unittest.TestCase):
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

        self.assertIn("Positive testing claims cite commands that are not grounded in the testing packet.", findings["detected"]["unsupported_claims"])

    def test_candidate_findings_allow_no_behavior_change_when_runtime_packet_is_empty(self) -> None:
        context = collected_context()
        context["changed_file_groups"]["runtime"]["count"] = 0
        context["changed_file_groups"]["runtime"]["sample_files"] = []
        context["changed_files"] = ["README.md"]

        findings = lint.collect_candidate_findings(
            context,
            "docs(pr-create): document guarded create flow",
            "\n".join(
                [
                    "## Why",
                    "Document the create flow.",
                    "## What changed",
                    "- Updated docs only.",
                    "## How",
                    "- No behavior change.",
                    "## Risk / Rollback",
                    "- Revert the docs text.",
                    "## Testing",
                    "- Not run.",
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
                    "- Not run.",
                    "Refs: #42",
                ]
            ),
        )

        self.assertIn("Issue references are present without matching issue hints from the process packet.", findings["detected"]["unsupported_claims"])


if __name__ == "__main__":
    unittest.main()
