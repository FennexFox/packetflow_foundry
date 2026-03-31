from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import apply_public_docs_sync as apply_sync  # noqa: E402
import validate_public_docs_sync as validator  # noqa: E402


def write_repo_files(repo_root: Path) -> None:
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True, exist_ok=True)
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                "# Project",
                "",
                "| Setting | Default | Purpose |",
                "| --- | --- | --- |",
                "| `EnableThing` | `false` | Turn the feature on. |",
                "",
                "See the [Guide](./missing.md).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "CONTRIBUTING.md").write_text(
        "Public docs live in README.old.md\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (repo_root / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").write_text(
        "\n".join(
            [
                'name: "Bug Report"',
                'description: "Tell us what broke."',
                'title: "Bug: "',
                'labels: ["bug"]',
                "body:",
                "  - type: textarea",
                "",
            ]
        ),
        encoding="utf-8",
    )


def sample_context(repo_root: Path, state_file: Path) -> dict[str, object]:
    return {
        "skill_name": "public-docs-sync",
        "context_id": "ctx-1",
        "context_fingerprint": "fp-1",
        "repo_root": str(repo_root),
        "repo_hash": "hash-1",
        "repo_slug": "owner/repo",
        "branch": "main",
        "head_commit": "abc123",
        "effective_base_commit": "base123",
        "public_doc_paths": [
            "README.md",
            "CONTRIBUTING.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
        ],
        "public_doc_inventory": {
            "README.md": {
                "kind": "markdown",
                "exists": True,
                "missing_links": [{"target": "./missing.md"}],
            },
            "CONTRIBUTING.md": {
                "kind": "markdown",
                "exists": True,
                "missing_links": [],
            },
            ".github/ISSUE_TEMPLATE/bug_report.yml": {
                "kind": "yaml",
                "exists": True,
                "missing_links": [],
            },
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
        "packet_candidates": {
            "claims_packet": {"active": True},
            "workflow_packet": {"active": True},
            "forms_batch_packet": {"active": True},
        },
        "relevant_ref": {"source": "merge-base", "base_commit": "base123"},
        "github_evidence_digest": "digest-1",
        "state_file": str(state_file),
        "evidence_summary": {"urls": ["https://example.test/pr/1"]},
        "baseline": {"base_commit": "base123"},
    }


def build_validation(context: dict[str, object], plan: dict[str, object]) -> dict[str, object]:
    with patch.object(validator, "run_git", return_value="abc123"):
        return validator.validate_public_docs_sync_plan(context, plan)


def sample_plan(allow_marker_update: bool = True) -> dict[str, object]:
    return {
        "context_id": "ctx-1",
        "context_fingerprint": "fp-1",
        "overall_confidence": "high",
        "doc_update_status": "completed",
        "allow_marker_update": allow_marker_update,
        "actions": [
            {
                "type": "settings_default_sync",
                "summary": "Sync the README settings defaults.",
                "path": "README.md",
                "details": {"setting": "EnableThing"},
            },
            {
                "type": "relative_link_fix",
                "summary": "Fix the README guide link.",
                "path": "README.md",
                "details": {
                    "target": "./missing.md",
                    "replacement_target": "./docs/guide.md",
                },
            },
            {
                "type": "public_doc_reference_sync",
                "summary": "Update the README reference in CONTRIBUTING.",
                "path": "CONTRIBUTING.md",
                "details": {
                    "match_text": "README.old.md",
                    "replacement_text": "README.md",
                },
            },
            {
                "type": "issue_template_metadata_sync",
                "summary": "Sync bug-report labels.",
                "path": ".github/ISSUE_TEMPLATE/bug_report.yml",
                "details": {
                    "field": "labels",
                    "value": ["bug", "player-report"],
                },
            },
        ],
        "stop_reasons": [],
        "selected_packets": ["claims_packet", "workflow_packet", "forms_batch_packet"],
        "remaining_manual_reviews": [],
    }


class ApplyPublicDocsSyncTests(unittest.TestCase):
    def test_dry_run_consumes_validator_output_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            repo_root.mkdir()
            state_file = Path(tmp_dir) / "state.json"
            write_repo_files(repo_root)
            context = sample_context(repo_root, state_file)
            validation = build_validation(context, sample_plan())
            readme_before = (repo_root / "README.md").read_text(encoding="utf-8")

            with patch.object(apply_sync, "run_git", return_value="abc123"):
                payload = apply_sync.apply_validated_plan(validation, dry_run=True, state_file=state_file)

            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["validation_source"], "validator_normalized_plan")
            self.assertEqual(payload["deterministic_edit_count"], 4)
            self.assertFalse(payload["marker_written"])
            self.assertEqual((repo_root / "README.md").read_text(encoding="utf-8"), readme_before)
            self.assertFalse(state_file.exists())

    def test_apply_executes_all_supported_deterministic_edit_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            repo_root.mkdir()
            state_file = Path(tmp_dir) / "state.json"
            write_repo_files(repo_root)
            context = sample_context(repo_root, state_file)
            validation = build_validation(context, sample_plan())

            with patch.object(apply_sync, "run_git", return_value="abc123"):
                payload = apply_sync.apply_validated_plan(validation, dry_run=False, state_file=state_file)

            readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
            contributing_text = (repo_root / "CONTRIBUTING.md").read_text(encoding="utf-8")
            issue_template_text = (repo_root / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")

            self.assertTrue(payload["apply_succeeded"])
            self.assertTrue(payload["marker_written"])
            self.assertEqual(payload["doc_edit_count"], 3)
            self.assertIn("| `EnableThing` | `true` | Turn the feature on. |", readme_text)
            self.assertIn("[Guide](./docs/guide.md)", readme_text)
            self.assertIn("README.md", contributing_text)
            self.assertIn('labels: ["bug", "player-report"]', issue_template_text)
            self.assertTrue(state_file.exists())

    def test_apply_skips_marker_write_when_manual_reviews_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            repo_root.mkdir()
            state_file = Path(tmp_dir) / "state.json"
            write_repo_files(repo_root)
            context = sample_context(repo_root, state_file)
            plan = sample_plan()
            plan["actions"].append("Finish the release-status wording.")
            plan["remaining_manual_reviews"] = ["Finalize the public narrative."]
            validation = build_validation(context, plan)

            with patch.object(apply_sync, "run_git", return_value="abc123"):
                payload = apply_sync.apply_validated_plan(validation, dry_run=False, state_file=state_file)

            self.assertTrue(payload["apply_succeeded"])
            self.assertFalse(payload["can_update_marker"])
            self.assertFalse(payload["marker_written"])
            self.assertFalse(state_file.exists())
            self.assertIn("| `EnableThing` | `true` | Turn the feature on. |", (repo_root / "README.md").read_text(encoding="utf-8"))

    def test_apply_rejects_stale_head_before_file_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            repo_root.mkdir()
            state_file = Path(tmp_dir) / "state.json"
            write_repo_files(repo_root)
            context = sample_context(repo_root, state_file)
            validation = build_validation(context, sample_plan())

            with (
                patch.object(apply_sync, "run_git", return_value="different-head"),
                self.assertRaisesRegex(RuntimeError, "stale context"),
            ):
                apply_sync.apply_validated_plan(validation, dry_run=False, state_file=state_file)

    def test_apply_uses_embedded_validation_snapshot_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            repo_root.mkdir()
            state_file = Path(tmp_dir) / "state.json"
            write_repo_files(repo_root)
            context = sample_context(repo_root, state_file)
            validation = build_validation(context, sample_plan())

            self.assertIn("apply_context_snapshot", validation)
            self.assertNotIn("context", validation)
            with patch.object(apply_sync, "run_git", return_value="abc123"):
                payload = apply_sync.apply_validated_plan(validation, dry_run=True, state_file=state_file)

            self.assertEqual(payload["apply_context_snapshot"]["repo_root"], str(repo_root))


if __name__ == "__main__":
    unittest.main()
