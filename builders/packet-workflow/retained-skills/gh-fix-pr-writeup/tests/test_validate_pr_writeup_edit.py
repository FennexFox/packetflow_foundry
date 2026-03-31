from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_pr_writeup_edit as validator  # noqa: E402


def collected_context(repo_root: Path, *, broad: bool = False) -> dict:
    body = "\n".join(
        [
            "## Why",
            "Clarify the shipped behavior and validation evidence.",
            "## What changed",
            "- Tightened diagnostics wording.",
            "- Added lint coverage for PR text review.",
            "## How",
            "- Re-read the rules packet before changing PR text.",
            "## Risk / Rollback",
            "- Revert the PR text update if it overstates the diff.",
            "## Testing",
            "- Ran `python -m unittest discover tests`.",
        ]
    )
    changed_files = [
        "README.md",
        "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
    ]
    if broad:
        changed_files.extend(
            [
                ".github/instructions/pull-request.instructions.md",
                ".github/workflows/release.yml",
                "MAINTAINING.md",
                "CONTRIBUTING.md",
                "ExampleProduct/Setting.cs",
                "tests/test_writeup_rules.py",
                "ExampleProduct/ExampleProduct.csproj",
                "docs/faq.md",
                ".github/scripts/check_release.py",
                "README_ko.md",
                "README.md.bak",
                "docs/usage.md",
                "docs/testing.md",
                ".github/ISSUE_TEMPLATE/bug_report.yml",
                "ExampleProduct/Telemetry/Probe.cs",
                "ExampleProduct/Mod.cs",
                "ExampleProduct/Patches/Hook.cs",
                "ExampleProduct/Properties/PublishConfiguration.xml",
                "tests/test_apply_guard.py",
                "tests/test_build_packets.py",
                "tests/test_lint.py",
            ]
        )
    return {
        "repo_root": str(repo_root),
        "repo_slug": "owner/repo",
        "pr": {
            "number": 7,
            "title": "docs(pr-writeup): tighten lint coverage",
            "body": body,
            "url": "https://example.invalid/pr/7",
            "headRefName": "codex/guard",
            "headRefOid": "abc123def456",
            "baseRefName": "main",
            "closingIssuesReferences": [{"number": 42}],
        },
        "changed_files": changed_files,
        "changed_file_groups": {
            "runtime": {"count": 2 if broad else 1, "sample_files": ["ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs", *(["ExampleProduct/Setting.cs"] if broad else [])]},
            "automation": {"count": 3 if broad else 0, "sample_files": [".github/instructions/pull-request.instructions.md", *([".github/workflows/release.yml"] if broad else [])]},
            "docs": {"count": 4 if broad else 1, "sample_files": ["README.md", *(["MAINTAINING.md"] if broad else [])]},
            "tests": {"count": 3 if broad else 0, "sample_files": ["tests/test_writeup_rules.py"] if broad else []},
            "config": {"count": 1 if broad else 0, "sample_files": ["ExampleProduct/ExampleProduct.csproj"] if broad else []},
            "other": {"count": 0, "sample_files": []},
        },
        "expected_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "current_body_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "checks": {
            "title_matches_conventional_commit": True,
            "title_length": 42,
            "body_has_template_sections": True,
        },
        "diff_stat": (" 23 files changed, 280 insertions(+), 40 deletions(-)" if broad else " 2 files changed, 5 insertions(+), 1 deletion(-)"),
    }


def valid_candidate_body() -> str:
    return "\n".join(
        [
            "## Why",
            "Clarify the shipped behavior and evidence boundaries.",
            "## What changed",
            "- Added a guarded validate/apply path for PR text edits.",
            "- Kept the final writeup aligned with the inspected diff.",
            "## How",
            "- Re-fetched the live PR snapshot before the guarded mutation.",
            "## Risk / Rollback",
            "- Revert the PR text if the replacement proves inaccurate.",
            "## Testing",
            "- Ran `python -m unittest discover tests`.",
            "Refs: #42",
        ]
    )


def qa_keep() -> dict:
    return {
        "keep_or_revise": "keep",
        "rule_violations": [],
        "coverage_gaps": [],
        "unsupported_claims": [],
    }


class ValidatePrWriteupEditTests(unittest.TestCase):
    def test_validator_rejects_invalid_candidate_before_gh_calls(self) -> None:
        context = collected_context(Path.cwd())
        with mock.patch.object(
            validator.tools,
            "run_command",
            side_effect=AssertionError("gh command should not run for invalid candidate lint"),
        ):
            payload = validator.validate_pr_writeup_edit(context, "bad title", "## Why\nInvalid.\n")

        self.assertFalse(payload["valid"])
        self.assertIn("invalid_candidate", payload["stop_reasons"])
        codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["candidate_lint_failed"], codes)

    def test_validator_flags_unsupported_claims(self) -> None:
        context = collected_context(Path.cwd())
        body = valid_candidate_body().replace(
            "- Re-fetched the live PR snapshot before the guarded mutation.",
            "- Restart required after deploy because defaults changed.",
        )
        with mock.patch.object(
            validator.tools,
            "run_command",
            side_effect=AssertionError("gh command should not run once unsupported claims are detected"),
        ):
            payload = validator.validate_pr_writeup_edit(
                context,
                "docs(pr-writeup): add guarded validator flow",
                body,
            )

        self.assertFalse(payload["valid"])
        self.assertIn("unsupported_claims_detected", payload["stop_reasons"])
        codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["unsupported_claims"], codes)

    def test_validator_rejects_stale_context_after_live_snapshot_check(self) -> None:
        context = collected_context(Path.cwd())

        def fake_run_command(args: list[str], cwd: Path) -> str:
            if args[:3] == ["gh", "auth", "status"]:
                return "Logged in to github.com"
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(context["pr"])
            if args[:4] == ["gh", "pr", "diff", "7"]:
                return "\n".join(context["changed_files"] + ["MAINTAINING.md"])
            raise AssertionError(f"Unexpected command: {args}")

        with mock.patch.object(validator.tools, "run_command", side_effect=fake_run_command):
            payload = validator.validate_pr_writeup_edit(
                context,
                "docs(pr-writeup): add guarded validator flow",
                valid_candidate_body(),
            )

        self.assertFalse(payload["valid"])
        self.assertIn("stale_context", payload["stop_reasons"])
        self.assertEqual(payload["stale_fields"][0]["field"], "changed_files")

    def test_validator_emits_normalized_edit_when_candidate_is_apply_safe(self) -> None:
        context = collected_context(Path.cwd())

        def fake_run_command(args: list[str], cwd: Path) -> str:
            if args[:3] == ["gh", "auth", "status"]:
                return "Logged in to github.com"
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(context["pr"])
            if args[:4] == ["gh", "pr", "diff", "7"]:
                return "\n".join(context["changed_files"])
            raise AssertionError(f"Unexpected command: {args}")

        with mock.patch.object(validator.tools, "run_command", side_effect=fake_run_command):
            payload = validator.validate_pr_writeup_edit(
                context,
                "docs(pr-writeup): add guarded validator flow",
                valid_candidate_body(),
            )

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])
        self.assertEqual(payload["normalized_edit"]["pr_number"], 7)
        self.assertEqual(payload["apply_gate_status"]["status"], "pass")
        self.assertFalse(payload["qa_required"])
        self.assertEqual(
            sorted(payload["normalized_edit"]["validated_snapshot"].keys()),
            sorted(["title", "body", "url", "headRefName", "headRefOid", "baseRefName", "changed_files"]),
        )

    def test_broad_full_rewrite_requires_qa_clear(self) -> None:
        context = collected_context(Path.cwd(), broad=True)
        full_rewrite = "\n".join(
            [
                "## Why",
                "Rewrite the PR explanation to cover the full multi-area change set.",
                "## What changed",
                "- Rebuilt the whole writeup from scratch.",
                "## How",
                "- Rephrased the PR text after re-reading packets.",
                "## Risk / Rollback",
                "- Revert the PR text if the draft overstates the diff.",
                "## Testing",
                "- Ran `python -m unittest discover tests`.",
                "Refs: #42",
            ]
        )

        def fake_run_command(args: list[str], cwd: Path) -> str:
            if args[:3] == ["gh", "auth", "status"]:
                return "Logged in to github.com"
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(context["pr"])
            if args[:4] == ["gh", "pr", "diff", "7"]:
                return "\n".join(context["changed_files"])
            raise AssertionError(f"Unexpected command: {args}")

        with mock.patch.object(validator.tools, "run_command", side_effect=fake_run_command):
            payload = validator.validate_pr_writeup_edit(
                context,
                "docs(pr-writeup): rewrite multi-area summary",
                full_rewrite,
            )

        self.assertFalse(payload["valid"])
        self.assertTrue(payload["qa_required"])
        self.assertIn("qa_required", payload["stop_reasons"])

    def test_worker_claim_conflict_requires_qa(self) -> None:
        context = collected_context(Path.cwd())

        def fake_run_command(args: list[str], cwd: Path) -> str:
            if args[:3] == ["gh", "auth", "status"]:
                return "Logged in to github.com"
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(context["pr"])
            if args[:4] == ["gh", "pr", "diff", "7"]:
                return "\n".join(context["changed_files"])
            raise AssertionError(f"Unexpected command: {args}")

        with mock.patch.object(validator.tools, "run_command", side_effect=fake_run_command):
            payload = validator.validate_pr_writeup_edit(
                context,
                "docs(pr-writeup): add guarded validator flow",
                valid_candidate_body(),
                worker_claim_conflict=True,
                qa_result=qa_keep(),
            )

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["qa_required"])
        self.assertTrue(payload["qa_clear"])


if __name__ == "__main__":
    unittest.main()
