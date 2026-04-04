import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import apply_release_copy as apply_release_copy_plan
import release_copy_plan_tools as plan_tools


PUBLISH_XML = """<Configuration>
  <ShortDescription Value="Current short description" />
  <LongDescription>Current long description.</LongDescription>
  <ModVersion Value="1.2.3" />
  <ChangeLog>- Current release note.</ChangeLog>
</Configuration>
"""

README_MD = """# ExampleProduct

Intro text.

## Current Release
Current release block.

## Current Status
Current status block.
"""


class ApplyReleaseCopyPlanTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def build_normalized_plan(self, tmp: Path, *, issue_action: dict | None = None) -> tuple[dict, Path, Path]:
        repo_root = tmp / "repo"
        publish_path = repo_root / "ExampleProduct" / "Properties" / "PublishConfiguration.xml"
        readme_path = repo_root / "README.md"
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        publish_path.write_text(PUBLISH_XML, encoding="utf-8")
        readme_path.write_text(README_MD, encoding="utf-8")

        normalized_plan = {
            "repo_root": str(repo_root),
            "repo_slug": "owner/repo",
            "context_fingerprint": "sha256:context",
            "freshness_tuple": {
                "head_commit": "abc1234",
                "base_tag": "v1.2.2",
                "target_version": "1.2.3",
                "evidence_fingerprint": plan_tools.json_fingerprint({}),
                "existing_release_issue": None,
            },
            "source_fingerprints": {
                "publish_configuration": plan_tools.json_fingerprint(PUBLISH_XML),
                "readme": plan_tools.json_fingerprint(README_MD),
            },
            "rule_files": {
                "publish_configuration": str(publish_path),
                "readme": str(readme_path),
            },
            "local_release_helper_status": "present",
            "overall_confidence": "high",
            "stop_reasons": [],
            "evidence_status": "not-applicable",
            "draft_basis": {
                "common_path_sufficient": True,
                "raw_reread_count": 0,
                "reread_reasons": [],
                "focused_packets_used": [],
                "compensatory_reread_detected": False,
                "synthesis_packet_fingerprint": "sha256:synthesis",
            },
            "publish_update": {
                "mode": "replace-fields",
                "fields": {
                    "short_description": "Updated short description",
                    "change_log": "- Fresh release note.",
                },
            },
            "readme_update": {
                "mode": "replace-sections",
                "intro_text": "# ExampleProduct\n\nUpdated intro text.",
                "sections": {
                    "Current Release": "Updated release block.",
                    "Current Status": "Updated status block.",
                },
            },
            "issue_action": issue_action or {"mode": "noop", "title": "", "body_markdown": "", "project_mode": "auto-add-first", "project_title": "ExampleProduct Tracker"},
            "validated_existing_issue_snapshot": None,
            "validation_commands": ["git rev-parse --short HEAD"],
        }
        return normalized_plan, publish_path, readme_path

    def validation_payload(self, normalized_plan: dict) -> dict:
        return {
            "valid": True,
            "can_apply": True,
            "errors": [],
            "warnings": [],
            "stop_reasons": [],
            "normalized_plan": normalized_plan,
            "normalized_plan_fingerprint": plan_tools.json_fingerprint(normalized_plan),
            "apply_gate_status": {
                "status": "pass",
                "applicable_stop_categories": ["stale_context", "validator_mismatch", "unresolved_stop_reason"],
                "covered_stop_categories": ["stale_context", "validator_mismatch", "unresolved_stop_reason"],
                "uncovered_stop_categories": [],
                "not_applicable_stop_categories": ["ambiguous_routing", "missing_auth", "missing_required_evidence"],
                "local_stop_categories": [],
            },
        }

    def run_apply(self, validation: dict, *, dry_run: bool = False, current_head: str = "abc1234") -> tuple[int, str, dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            validation_path = tmp / "validation.json"
            result_path = tmp / "apply.json"
            self.write_json(validation_path, validation)

            argv = [
                "apply_release_copy_plan.py",
                "--validation",
                str(validation_path),
                "--result-output",
                str(result_path),
            ]
            if dry_run:
                argv.append("--dry-run")

            stdout = io.StringIO()
            with mock.patch.object(
                apply_release_copy_plan.plan_tools,
                "current_head_commit",
                return_value=current_head,
            ), mock.patch.object(
                sys,
                "argv",
                argv,
            ), redirect_stdout(stdout):
                exit_code = apply_release_copy_plan.main()

            return exit_code, stdout.getvalue(), json.loads(result_path.read_text(encoding="utf-8"))

    def test_apply_dry_run_uses_validator_output_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            normalized_plan, publish_path, readme_path = self.build_normalized_plan(tmp)
            validation = self.validation_payload(normalized_plan)

            exit_code, _stdout, payload = self.run_apply(validation, dry_run=True)

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["validation_source"], "validator_normalized_plan")
            self.assertEqual(payload["raw_reread_count"], 0)
            self.assertFalse(payload["compensatory_reread_detected"])
            self.assertEqual(payload["deterministic_file_edit_count"], 2)
            self.assertFalse(payload["issue_action_attempted"])
            self.assertEqual(publish_path.read_text(encoding="utf-8"), PUBLISH_XML)
            self.assertEqual(readme_path.read_text(encoding="utf-8"), README_MD)
            mutation_kinds = [item["kind"] for item in payload["mutations"]]
            self.assertEqual(mutation_kinds, ["publish_configuration", "readme"])

    def test_apply_supports_numeric_mod_version_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            normalized_plan, publish_path, _readme_path = self.build_normalized_plan(tmp)
            normalized_plan["publish_update"]["fields"]["mod_version"] = "10.0.0"
            validation = self.validation_payload(normalized_plan)

            exit_code, _stdout, payload = self.run_apply(validation)

            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["apply_succeeded"])
            publish_mutation = next(item for item in payload["mutations"] if item["kind"] == "publish_configuration")
            self.assertIn("mod_version", publish_mutation["fields"])
            self.assertIn('<ModVersion Value="10.0.0" />', publish_path.read_text(encoding="utf-8"))

    def test_apply_rejects_tampered_validator_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            normalized_plan, _publish_path, _readme_path = self.build_normalized_plan(tmp)
            validation = self.validation_payload(normalized_plan)
            validation["normalized_plan"]["publish_update"]["fields"]["short_description"] = "Tampered"

            exit_code, _stdout, payload = self.run_apply(validation)

            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["stop_reason"], "validator_mismatch")

    def test_apply_rolls_back_files_when_issue_action_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            issue_action = {
                "mode": "create",
                "title": "[Release] v1.2.3",
                "body_markdown": "Checklist body",
                "project_mode": "auto-add-first",
                "project_title": "ExampleProduct Tracker",
            }
            normalized_plan, publish_path, readme_path = self.build_normalized_plan(tmp, issue_action=issue_action)
            validation = self.validation_payload(normalized_plan)
            validation["apply_gate_status"]["applicable_stop_categories"].append("missing_auth")
            validation["apply_gate_status"]["covered_stop_categories"].append("missing_auth")
            validation["apply_gate_status"]["not_applicable_stop_categories"] = ["ambiguous_routing", "missing_required_evidence"]

            with mock.patch.object(
                apply_release_copy_plan.issue_tools,
                "run_command",
                return_value="Logged in with project scope.",
            ), mock.patch.object(
                apply_release_copy_plan.issue_tools,
                "execute_issue_action",
                side_effect=RuntimeError("gh issue create failed"),
            ):
                exit_code, _stdout, payload = self.run_apply(validation)

            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["stop_reason"], "apply_failed")
            self.assertTrue(payload["rollback_needed"])
            self.assertTrue(payload["issue_action_attempted"])
            self.assertEqual(payload["deterministic_file_edit_count"], 2)
            self.assertEqual(sorted(payload["rolled_back_files"]), sorted([str(publish_path), str(readme_path)]))
            self.assertEqual(publish_path.read_text(encoding="utf-8"), PUBLISH_XML)
            self.assertEqual(readme_path.read_text(encoding="utf-8"), README_MD)

    def test_apply_stops_on_stale_issue_snapshot_before_file_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            issue_action = {
                "mode": "sync-existing-body",
                "title": "[Release] v1.2.3",
                "body_markdown": "Checklist body",
                "project_mode": "auto-add-first",
                "project_title": "ExampleProduct Tracker",
            }
            normalized_plan, publish_path, readme_path = self.build_normalized_plan(tmp, issue_action=issue_action)
            normalized_plan["validated_existing_issue_snapshot"] = {
                "number": 42,
                "title": "[Release] v1.2.3",
                "state": "OPEN",
                "url": "https://example.invalid/issues/42",
                "body_fingerprint": plan_tools.json_fingerprint("Original body"),
            }
            normalized_plan["freshness_tuple"]["existing_release_issue"] = normalized_plan["validated_existing_issue_snapshot"]
            validation = self.validation_payload(normalized_plan)
            validation["apply_gate_status"]["applicable_stop_categories"].append("missing_auth")
            validation["apply_gate_status"]["covered_stop_categories"].append("missing_auth")
            validation["apply_gate_status"]["not_applicable_stop_categories"] = ["ambiguous_routing", "missing_required_evidence"]

            with mock.patch.object(
                apply_release_copy_plan.issue_tools,
                "run_command",
                return_value="Logged in with project scope.",
            ), mock.patch.object(
                apply_release_copy_plan.plan_tools,
                "fetch_issue_snapshot",
                return_value={
                    "number": 42,
                    "title": "[Release] v1.2.3",
                    "url": "https://example.invalid/issues/42",
                    "state": "OPEN",
                    "body": "Changed body",
                },
            ):
                exit_code, _stdout, payload = self.run_apply(validation)

            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["stop_reason"], "stale_issue_snapshot")
            self.assertFalse(payload["issue_action_attempted"])
            self.assertEqual(publish_path.read_text(encoding="utf-8"), PUBLISH_XML)
            self.assertEqual(readme_path.read_text(encoding="utf-8"), README_MD)


if __name__ == "__main__":
    unittest.main()
