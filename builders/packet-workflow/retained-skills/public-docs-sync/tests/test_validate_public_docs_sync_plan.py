from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_public_docs_sync as validator  # noqa: E402
import public_docs_sync_contract as contract  # noqa: E402


def sample_context() -> dict[str, object]:
    return {
        "context_id": "ctx-1",
        "context_fingerprint": "fp-1",
        "repo_root": "C:/repo",
        "repo_hash": "hash-1",
        "repo_slug": "owner/repo",
        "branch": "main",
        "head_commit": "abc123",
        "effective_base_commit": "base123",
        "state_file": "C:/repo/.codex/state.json",
        "github_evidence_required": False,
        "github_evidence_digest": "digest-1",
        "github_evidence": {
            "primary_pr": {"number": 42, "url": "https://example.test/pr/42"},
        },
        "relevant_ref": {
            "kind": "merge-base",
            "base_commit": "base123",
            "source": "merge-base",
            "primary_pr_number": 42,
            "primary_pr_url": "https://example.test/pr/42",
        },
        "packet_candidates": {
            "claims_packet": {"active": True},
            "workflow_packet": {"active": True},
            "forms_batch_packet": {"active": True},
        },
        "public_doc_paths": [
            "README.md",
            "CONTRIBUTING.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
        ],
        "public_doc_inventory": {
            "README.md": {
                "kind": "markdown",
                "missing_links": [{"target": "./missing.md"}],
            },
            "CONTRIBUTING.md": {"kind": "markdown"},
            ".github/ISSUE_TEMPLATE/bug_report.yml": {"kind": "yaml"},
        },
        "settings": {
            "source_path": "ExampleProduct/Setting.cs",
            "defaults": {
                "EnableThing": {
                    "default": "true",
                    "label": "Enable Thing",
                    "description": "Turn the feature on.",
                }
            },
        },
        "readme": {
            "path": "README.md",
            "settings_table": {
                "EnableThing": {
                    "default": "false",
                    "purpose": "Turn the feature on.",
                }
            },
        },
        "evidence_summary": {"urls": ["https://example.test/pr/1"]},
        "baseline": {"base_commit": "base123"},
    }


def sample_plan() -> dict[str, object]:
    return {
        "context_id": "ctx-1",
        "context_fingerprint": "fp-1",
        "overall_confidence": "high",
        "doc_update_status": "completed",
        "allow_marker_update": True,
        "actions": [
            {
                "type": "settings_default_sync",
                "summary": "Sync the README settings defaults.",
                "path": "README.md",
                "details": {"setting": "EnableThing"},
                "extra": "ignored",
            }
        ],
        "stop_reasons": [],
        "selected_packets": ["claims_packet"],
        "remaining_manual_reviews": [],
        "extra": "ignored",
    }


class ValidatePublicDocsSyncPlanTests(unittest.TestCase):
    def test_validator_normalizes_actions_and_embeds_minimal_apply_snapshot(self) -> None:
        with patch.object(validator, "run_git", return_value="abc123"):
            payload = validator.validate_public_docs_sync_plan(sample_context(), sample_plan())

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])
        self.assertTrue(payload["can_update_marker"])
        warning_codes = {item["code"] for item in payload["warning_details"]}
        self.assertIn(validator.VALIDATION_WARNING_CODES["unknown_top_level_field"], warning_codes)
        self.assertIn(validator.VALIDATION_WARNING_CODES["unknown_action_field"], warning_codes)
        normalized_action = payload["normalized_plan"]["actions"][0]
        self.assertEqual(normalized_action["action_mode"], "deterministic-edit")
        self.assertEqual(normalized_action["canonical_type"], "settings_table_default_sync")
        self.assertEqual(payload["action_summary"]["deterministic_edit_count"], 1)
        self.assertEqual(payload["apply_gate_status"]["apply_edits_status"], "pass")
        self.assertEqual(payload["apply_gate_status"]["marker_update_status"], "pass")
        self.assertEqual(payload["apply_gate_status"]["triggered_stop_categories"], [])
        self.assertNotIn("extra", payload["normalized_plan"])
        self.assertNotIn("extra", payload["normalized_plan"]["actions"][0])
        snapshot = payload["apply_context_snapshot"]
        self.assertEqual(
            sorted(snapshot),
            sorted(contract.APPLY_CONTEXT_SNAPSHOT_FIELDS),
        )
        self.assertEqual(
            set(payload["apply_gate_status"]["applicable_stop_categories"]),
            set(contract.STOP_CATEGORY_SCOPES),
        )
        self.assertNotIn("public_doc_inventory", snapshot)
        self.assertEqual(snapshot["primary_pr_number"], 42)
        self.assertTrue(payload["apply_context_snapshot_fingerprint"].startswith("sha256:"))

    def test_validator_blocks_marker_update_when_manual_reviews_remain(self) -> None:
        plan = sample_plan()
        plan["actions"].append("Finish the release-status prose.")
        plan["remaining_manual_reviews"] = ["Review the README narrative."]
        with patch.object(validator, "run_git", return_value="abc123"):
            payload = validator.validate_public_docs_sync_plan(sample_context(), plan)

        self.assertTrue(payload["valid"])
        self.assertTrue(payload["can_apply"])
        self.assertFalse(payload["can_update_marker"])
        self.assertEqual(payload["action_summary"]["manual_only_review_count"], 1)
        self.assertIn("narrative_drift_remaining", payload["apply_gate_status"]["triggered_stop_categories"])
        self.assertEqual(payload["apply_gate_status"]["marker_update_status"], "blocked")

    def test_validator_rejects_out_of_scope_deterministic_actions(self) -> None:
        plan = sample_plan()
        plan["actions"] = [
            {
                "type": "repo_wide_rewrite",
                "summary": "Rewrite the release narrative everywhere.",
                "path": "README.md",
            }
        ]
        with patch.object(validator, "run_git", return_value="abc123"):
            payload = validator.validate_public_docs_sync_plan(sample_context(), plan)

        self.assertFalse(payload["valid"])
        self.assertFalse(payload["can_apply"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["deterministic_scope_exceeded"], error_codes)
        self.assertIn("deterministic_scope_exceeded", payload["apply_gate_status"]["triggered_stop_categories"])

    def test_validator_flags_missing_required_evidence_with_fixed_code(self) -> None:
        context = sample_context()
        context["github_evidence_required"] = True
        context["github_evidence_digest"] = ""
        context["evidence_summary"] = {"urls": []}
        with patch.object(validator, "run_git", return_value="abc123"):
            payload = validator.validate_public_docs_sync_plan(context, sample_plan())

        self.assertFalse(payload["valid"])
        self.assertFalse(payload["can_apply"])
        error_codes = {item["code"] for item in payload["error_details"]}
        self.assertIn(validator.VALIDATION_ERROR_CODES["missing_required_evidence"], error_codes)
        self.assertEqual(
            validator.VALIDATION_ERROR_CODES["missing_required_evidence"],
            contract.VALIDATION_ERROR_CODES["missing_required_evidence"],
        )


if __name__ == "__main__":
    unittest.main()
