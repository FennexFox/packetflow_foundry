import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import release_copy_plan_tools as plan_tools
import validate_release_copy as validate_release_copy_plan


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


class ValidateReleaseCopyPlanTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def build_context(self, tmp: Path, *, existing_issue: dict | None = None) -> dict:
        repo_root = tmp / "repo"
        publish_path = repo_root / "ExampleProduct" / "Properties" / "PublishConfiguration.xml"
        readme_path = repo_root / "README.md"
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        publish_path.write_text(PUBLISH_XML, encoding="utf-8")
        readme_path.write_text(README_MD, encoding="utf-8")

        context = {
            "repo_root": str(repo_root),
            "repo_slug": "owner/repo",
            "head_commit": "abc1234",
            "base_tag": "v1.2.2",
            "target_version": "1.2.3",
            "rule_files": {
                "publish_configuration": str(publish_path),
                "readme": str(readme_path),
            },
            "publish_configuration": {
                "path": str(publish_path),
                "mod_version": "1.2.3",
                "short_description": "Current short description",
                "long_description": "Current long description.",
                "change_log": "- Current release note.",
            },
            "readme": {
                "path": str(readme_path),
                "intro_text": "# ExampleProduct\n\nIntro text.",
                "sections": {
                    "Current Release": "Current release block.",
                    "Current Status": "Current status block.",
                },
            },
            "source_fingerprints": {
                "publish_configuration": plan_tools.json_fingerprint(PUBLISH_XML),
                "readme": plan_tools.json_fingerprint(README_MD),
            },
            "existing_release_issue": existing_issue,
            "evidence": None,
            "local_release_helper": {"status": "present"},
            "project_title_default": "ExampleProduct Tracker",
        }
        context["freshness_tuple"] = plan_tools.expected_freshness_tuple(context)
        context["context_fingerprint"] = plan_tools.expected_context_fingerprint(context)
        return context

    def base_lint(self, *, evidence_complete: bool, tracks: dict[str, bool] | None = None) -> dict:
        return {
            "findings": {"errors": [], "warnings": [], "info": []},
            "checks": {
                "evidence_complete": evidence_complete,
                "applicable_validation_tracks": tracks or {"software_gate": False, "telemetry_validation": False},
            },
        }

    def base_plan(self, context: dict, *, evidence_status: str = "not-applicable", issue_action: dict | None = None) -> dict:
        return {
            "context_fingerprint": context["context_fingerprint"],
            "freshness_tuple": context["freshness_tuple"],
            "overall_confidence": "high",
            "stop_reasons": [],
            "evidence_status": evidence_status,
            "draft_basis": {
                "common_path_sufficient": True,
                "raw_reread_count": 0,
                "reread_reasons": [],
                "focused_packets_used": [],
                "compensatory_reread_detected": False,
                "synthesis_packet_fingerprint": "sha256:synthesis",
            },
            "publish_update": {"mode": "noop"},
            "readme_update": {"mode": "noop"},
            "issue_action": issue_action or {"mode": "noop"},
        }

    def run_validator(self, context: dict, lint: dict, plan: dict, **patches: object) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_path = tmp / "context.json"
            lint_path = tmp / "lint.json"
            plan_path = tmp / "plan.json"
            output_path = tmp / "validation.json"
            self.write_json(context_path, context)
            self.write_json(lint_path, lint)
            self.write_json(plan_path, plan)

            patchers = [
                mock.patch.object(validate_release_copy_plan.plan_tools, "current_head_commit", return_value=context["head_commit"]),
            ]
            for name, value in patches.items():
                patchers.append(mock.patch(name, value))

            with ExitStack() as stack:
                for patcher in patchers:
                    stack.enter_context(patcher)
                stack.enter_context(
                    mock.patch.object(
                        sys,
                        "argv",
                        [
                            "validate_release_copy_plan.py",
                            "--context",
                            str(context_path),
                            "--lint",
                            str(lint_path),
                            "--plan",
                            str(plan_path),
                            "--output",
                            str(output_path),
                        ],
                    )
                )
                validate_release_copy_plan.main()

            return json.loads(output_path.read_text(encoding="utf-8"))

    def test_validator_stops_on_release_gate_before_any_gh_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(tmp)
            lint = self.base_lint(
                evidence_complete=False,
                tracks={"software_gate": True, "telemetry_validation": False},
            )
            plan = self.base_plan(
                context,
                evidence_status="complete",
                issue_action={
                    "mode": "create",
                    "title": "[Release] v1.2.3",
                    "body_markdown": "Checklist body",
                    "project_mode": "auto-add-first",
                },
            )

            payload = self.run_validator(
                context,
                lint,
                plan,
                **{
                    "validate_release_copy.issue_tools.run_command": mock.Mock(
                        side_effect=AssertionError("gh auth should not run before local release-gate failure")
                    )
                },
            )

            self.assertFalse(payload["valid"])
            self.assertIn("release_gate_incomplete", payload["stop_reasons"])
            self.assertEqual(payload["apply_gate_status"]["status"], "fail")

    def test_validator_warns_and_strips_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(tmp)
            lint = self.base_lint(evidence_complete=True)
            plan = self.base_plan(context)
            plan["extra_top_level"] = "ignore me"
            plan["publish_update"] = {
                "mode": "replace-fields",
                "short_description": "Updated short description",
                "extra_publish_field": "ignore me too",
            }

            payload = self.run_validator(context, lint, plan)

            self.assertTrue(payload["valid"])
            warning_codes = {item["code"] for item in payload["warning_details"]}
            self.assertIn("W_RELEASE_PLAN_IGNORED_FIELD", warning_codes)
            self.assertNotIn("extra_top_level", payload["normalized_plan"])
            self.assertNotIn("extra_publish_field", payload["normalized_plan"]["publish_update"]["fields"])

    def test_validator_stops_on_compensatory_reread(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(tmp)
            lint = self.base_lint(evidence_complete=True)
            plan = self.base_plan(context)
            plan["draft_basis"]["raw_reread_count"] = 1
            plan["draft_basis"]["reread_reasons"] = ["unsupported_layout"]
            plan["draft_basis"]["compensatory_reread_detected"] = True

            payload = self.run_validator(context, lint, plan)

            self.assertFalse(payload["valid"])
            self.assertIn("synthesis_packet_insufficient", payload["stop_reasons"])

    def test_validator_stops_on_packet_insufficiency_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(tmp)
            lint = self.base_lint(evidence_complete=True)
            plan = self.base_plan(context)
            plan["draft_basis"]["raw_reread_count"] = 1
            plan["draft_basis"]["reread_reasons"] = ["packet_insufficiency"]

            payload = self.run_validator(context, lint, plan)

            self.assertFalse(payload["valid"])
            self.assertIn("synthesis_packet_insufficient", payload["stop_reasons"])

    def test_validator_detects_stale_existing_issue_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(
                tmp,
                existing_issue={
                    "number": 42,
                    "title": "[Release] v1.2.3",
                    "url": "https://example.invalid/issues/42",
                    "state": "OPEN",
                    "body": "Original body",
                },
            )
            lint = self.base_lint(evidence_complete=True)
            plan = self.base_plan(
                context,
                issue_action={
                    "mode": "sync-existing-body",
                    "title": "[Release] v1.2.3",
                    "body_markdown": "Updated body",
                    "project_mode": "auto-add-first",
                },
            )

            with mock.patch.object(
                validate_release_copy_plan.issue_tools,
                "run_command",
                return_value="Logged in with project scope.",
            ), mock.patch.object(
                validate_release_copy_plan.plan_tools,
                "fetch_issue_snapshot",
                return_value={
                    "number": 42,
                    "title": "[Release] v1.2.3",
                    "url": "https://example.invalid/issues/42",
                    "state": "OPEN",
                    "body": "Changed body",
                },
            ), mock.patch.object(
                validate_release_copy_plan.plan_tools,
                "current_head_commit",
                return_value=context["head_commit"],
            ):
                payload = validate_release_copy_plan.validate_plan_contract(context, lint, plan)

            self.assertFalse(payload["valid"])
            self.assertIn("stale_issue_snapshot", payload["stop_reasons"])

    def test_validator_emits_apply_safe_normalized_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context = self.build_context(tmp)
            lint = self.base_lint(evidence_complete=True)
            plan = self.base_plan(context)
            plan["publish_update"] = {
                "mode": "replace-fields",
                "short_description": "Updated short description",
                "change_log": "- Fresh release note.",
            }
            plan["readme_update"] = {
                "mode": "replace-sections",
                "sections": {
                    "Current Release": "Updated release block.",
                    "Current Status": "Updated status block.",
                },
            }

            payload = self.run_validator(context, lint, plan)

            self.assertTrue(payload["valid"])
            self.assertTrue(payload["can_apply"])
            self.assertEqual(payload["apply_gate_status"]["status"], "pass")
            self.assertEqual(payload["normalized_plan"]["publish_update"]["fields"]["short_description"], "Updated short description")
            self.assertEqual(payload["normalized_plan"]["readme_update"]["sections"]["Current Release"], "Updated release block.")


if __name__ == "__main__":
    unittest.main()
