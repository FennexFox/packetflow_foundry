from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lint_pr_writeup as lint  # noqa: E402


def broken_context() -> dict:
    body = "\n".join(
        [
            "## Why",
            "The existing PR writeup is vague.",
            "Refs: #",
            "## What changed",
            "- ",
            "## How",
            "Note any important defaults, thresholds, reload/restart requirements, or",
            "## PR Classification (optional)",
            "- [x] Bug fix",
            "",
            "Justification:",
        ]
    )
    return {
        "pr": {
            "number": 42,
            "title": "Rewrite PR writeup",
            "url": "https://example.invalid/pr/42",
            "body": body,
        },
        "expected_template_sections": [
            "Why",
            "What changed",
            "How",
            "Risk / Rollback",
            "Testing",
            "PR Classification (optional)",
        ],
        "current_body_sections": [
            "Why",
            "What changed",
            "How",
            "PR Classification (optional)",
        ],
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["ExampleProduct/Mod.cs"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 1, "sample_files": ["README.md"]},
            "tests": {"count": 0, "sample_files": []},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
    }


def clean_context() -> dict:
    body = "\n".join(
        [
            "## Why",
            "Clarify the shipped change and the validation evidence.",
            "## What changed",
            "- Tightened the audit report contract reference.",
            "- Added deterministic linter coverage for the audit payload.",
            "## How",
            "- Re-read the rules packet before any local edit.",
            "## Risk / Rollback",
            "- Revert the PR text update if it overstates the diff.",
            "## Testing",
            "- Ran `python -m unittest discover tests`.",
        ]
    )
    return {
        "pr": {
            "number": 7,
            "title": "docs(pr-writeup): tighten lint coverage",
            "url": "https://example.invalid/pr/7",
            "body": body,
        },
        "expected_template_sections": [
            "Why",
            "What changed",
            "How",
            "Risk / Rollback",
            "Testing",
        ],
        "current_body_sections": [
            "Why",
            "What changed",
            "How",
            "Risk / Rollback",
            "Testing",
        ],
        "changed_file_groups": {
            "runtime": {"count": 0, "sample_files": []},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 2, "sample_files": ["SKILL.md", "references/pr-writeup-contract.md"]},
            "tests": {"count": 1, "sample_files": ["tests/test_lint_pr_writeup.py"]},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
    }


class LintPrWriteupTests(unittest.TestCase):
    def test_collect_findings_flags_title_and_template_errors(self) -> None:
        context = broken_context()
        findings = lint.collect_findings(context)

        self.assertTrue(
            any("Title does not match" in message for message in findings["errors"])
        )
        self.assertIn(
            "Body is missing template sections: Risk / Rollback, Testing.",
            findings["errors"],
        )
        self.assertIn("Changed areas: runtime, docs", findings["info"])

    def test_main_emits_findings_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context_path = tmp / "context.json"
            output_path = tmp / "lint.json"
            context_path.write_text(json.dumps(clean_context()), encoding="utf-8")

            argv = [
                "lint_pr_writeup.py",
                "--context",
                str(context_path),
                "--output",
                str(output_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(lint.main(), 0)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["findings"]["errors"], [])
            self.assertEqual(payload["findings"]["warnings"], [])
            self.assertNotIn("audit_report", payload)
            self.assertEqual(payload["url"], "https://example.invalid/pr/7")


if __name__ == "__main__":
    unittest.main()
