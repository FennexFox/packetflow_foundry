from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lint_public_docs_sync as lint_mod  # noqa: E402


def empty_findings() -> dict[str, object]:
    return {
        "errors": [],
        "warnings": [],
        "infos": [],
        "issues": [],
        "classifications": {
            "hard_drift": [],
            "review_required": [],
            "link_error": [],
            "stale_baseline": [],
        },
        "auto_apply_candidates": [],
        "packet_basis": {},
    }


class LintPublicDocsSyncTests(unittest.TestCase):
    def test_lint_detects_settings_drift_and_broken_links(self) -> None:
        context = {
            "settings": {
                "source_path": "ExampleProduct/Setting.cs",
                "defaults": {"EnableThing": {"default": "true"}},
            },
            "readme": {
                "path": "README.md",
                "settings_table": {"EnableThing": {"default": "false"}},
            },
            "public_doc_inventory": {
                "README.md": {
                    "missing_links": [{"target": "./missing.md", "resolved_path": "missing.md"}],
                }
            },
            "packet_candidates": {
                "claims_packet": {"review_docs": ["README.md"], "changed_paths": ["README.md"]},
            },
        }
        findings = empty_findings()

        lint_mod.lint_readme_settings(context, findings)
        lint_mod.lint_missing_links(context, findings)
        lint_mod.finalize_packet_basis(context, findings)

        self.assertEqual(len(findings["classifications"]["hard_drift"]), 1)
        self.assertEqual(len(findings["classifications"]["link_error"]), 1)
        self.assertEqual(findings["auto_apply_candidates"][0]["kind"], "settings_default_sync")
        self.assertEqual(findings["packet_basis"]["claims_packet"]["deterministic_action_candidates"][0]["canonical_type"], "settings_table_default_sync")
        self.assertFalse(findings["packet_basis"]["claims_packet"]["marker_gate_signals"]["marker_blocked_by_packet"])


if __name__ == "__main__":
    unittest.main()
