import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lint_release_copy as lint_release_copy


class LintReleaseCopyTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def run_lint(self, context: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_path = tmp / "context.json"
            output_path = tmp / "lint.json"
            self.write_json(context_path, context)

            with mock.patch.object(
                sys,
                "argv",
                [
                    "lint_release_copy.py",
                    "--context",
                    str(context_path),
                    "--output",
                    str(output_path),
                ],
            ):
                exit_code = lint_release_copy.main()

            self.assertEqual(exit_code, 0)
            return self.read_json(output_path)

    def test_lint_flags_software_gate_claims_and_missing_topics(self) -> None:
        context = {
            "target_version": "1.2.3",
            "base_tag": "v1.2.2",
            "publish_configuration": {
                "mod_version": "1.2.3",
                "short_description": "Software path fixed for office demand buyers.",
                "long_description": "Diagnostics are stable now.",
                "change_log": "- Publish metadata updated for this release.",
            },
            "base_tag_publish_configuration": {
                "change_log": "- Prior release telemetry note.",
            },
            "readme": {
                "intro_text": "This release confirms the software fix.",
                "sections": {
                    "Current Release": "Software fix confirmed for diagnostics and buyer fallback.",
                    "Current Status": "No experimental disclaimer remains.",
                },
                "settings_defaults": {},
            },
            "setting_defaults": {},
            "local_release_helper": {
                "status": "present",
            },
            "changed_files": [
                "ExampleProduct/Setting.cs",
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
                "ExampleProduct/Systems/VirtualOfficeResourceBuyerFixSystem.cs",
            ],
            "changed_file_stats": {
                "ExampleProduct/Setting.cs": {"churn": 140},
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs": {"churn": 160},
                "ExampleProduct/Systems/VirtualOfficeResourceBuyerFixSystem.cs": {"churn": 150},
            },
            "commit_subjects": [
                "Tighten diagnostic flow for buyers",
                "Buyer fallback cleanup",
            ],
            "evidence": {
                "software_track_status": "pending",
                "comparable_evidence": "",
                "anchor_comparison": "",
                "release_pr_validation_note": "",
            },
        }

        result = self.run_lint(context)

        error_codes = {item["code"] for item in result["findings"]["errors"]}
        warning_codes = {item["code"] for item in result["findings"]["warnings"]}

        self.assertIn("unsupported_strong_software_claim", error_codes)
        self.assertIn("release_gate_validation_incomplete", warning_codes)
        self.assertIn("missing_changelog_topic", warning_codes)
        self.assertIn("checklist_field_unresolved", warning_codes)
        self.assertTrue(result["checks"]["target_version_matches_publish"])
        self.assertFalse(result["checks"]["evidence_complete"])
        self.assertTrue(result["checks"]["helper_handoff_allowed"])
        self.assertTrue(result["checks"]["rewrite_publish_recommended"])
        self.assertTrue(result["checks"]["rewrite_readme_recommended"])

    def test_lint_reports_missing_helper_and_version_mismatch(self) -> None:
        context = {
            "target_version": "2.0.0",
            "base_tag": "v1.9.9",
            "publish_configuration": {
                "mod_version": "1.9.9",
                "short_description": "Experimental path remains under investigation.",
                "long_description": "",
                "change_log": "- Diagnostics logging cleanup.",
            },
            "base_tag_publish_configuration": {
                "change_log": "- Previous release note.",
            },
            "readme": {
                "intro_text": "Experimental path remains under investigation.",
                "sections": {
                    "Current Release": "",
                    "Current Status": "",
                },
                "settings_defaults": {},
            },
            "setting_defaults": {},
            "local_release_helper": {
                "status": "missing_local_release_script",
            },
            "changed_files": [],
            "changed_file_stats": {},
            "commit_subjects": [],
            "evidence": None,
        }

        result = self.run_lint(context)

        error_codes = {item["code"] for item in result["findings"]["errors"]}
        info_codes = {item["code"] for item in result["findings"]["info"]}

        self.assertIn("target_version_mismatch", error_codes)
        self.assertIn("missing_local_release_script", info_codes)
        self.assertFalse(result["checks"]["target_version_matches_publish"])
        self.assertFalse(result["checks"]["helper_handoff_allowed"])


if __name__ == "__main__":
    unittest.main()
