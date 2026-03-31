from __future__ import annotations

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

import apply_pr_create as apply_create  # noqa: E402
import pr_create_contract as contract  # noqa: E402


def request_payload(repo_root: Path) -> dict:
    normalized = {
        "repo_root": str(repo_root),
        "repo_slug": "owner/repo",
        "base": "main",
        "head": "feature/pr-create",
        "title": "feat(pr-create): create guarded PRs",
        "body": "\n".join(
            [
                "## Why",
                "Open a guarded PR from a pushed branch.",
                "## What changed",
                "- Added validator-normalized create flow.",
                "- Re-check duplicate and template state before create.",
                "## How",
                "- Keep create fail-closed on stale snapshots.",
                "## Risk / Rollback",
                "- Refresh branch state and rerun validation.",
                "## Testing",
                "- Not run.",
                "Refs: #42",
            ]
        ),
        "draft": True,
        "reviewers": ["alice"],
        "assignees": ["bob"],
        "labels": ["automation"],
        "milestone": "v1",
        "maintainer_can_modify": False,
        "validation_commands": ["candidate lint", "gh auth status"],
        "review_mode": "targeted-delegation",
        "qa_gate": {"required": False, "reason": None, "qa_clear": False},
        "validated_snapshot": {
            "local_head_oid": "abc123",
            "remote_head_oid": "abc123",
            "repo_slug": "owner/repo",
            "base_ref": "main",
            "head_ref": "feature/pr-create",
            "changed_files_fingerprint": contract.json_fingerprint(["src/creator.py"]),
            "template_path": "C:/repo/.github/pull_request_template.md",
            "template_fingerprint": contract.json_fingerprint("template"),
            "duplicate_check_summary": {
                "status": "clear",
                "matched_repo_slug": "owner/repo",
                "matched_head": "feature/pr-create",
                "existing_pr_number": None,
                "existing_pr_url": None,
                "existing_pr_count": 0,
            },
        },
    }
    return {
        "valid": True,
        "can_apply": True,
        "normalized_create_request": normalized,
        "normalized_create_request_fingerprint": contract.json_fingerprint(normalized),
        "apply_gate_status": contract.stop_status(),
        "stop_reasons": [],
    }


class ApplyPrCreateTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_apply_rejects_tampered_validator_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation = request_payload(repo_root)
            validation["normalized_create_request"]["title"] = "tampered"
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, validation)

            stdout = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["apply_pr_create.py", "--validation", str(validation_path), "--result-output", str(result_path)],
            ), redirect_stdout(stdout):
                exit_code = apply_create.main()

            self.assertEqual(exit_code, 1)
            payload = self.read_json(result_path)
            self.assertEqual(payload["stop_reason"], "fingerprint_mismatch")

    def test_dry_run_reports_command_without_calling_gh_pr_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, request_payload(repo_root))
            recorded_calls: list[list[str]] = []

            def fake_run_command(args: list[str], cwd: Path) -> str:
                recorded_calls.append(args)
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in to github.com"
                raise AssertionError(f"Unexpected command: {args}")

            with (
                mock.patch.object(apply_create.tools, "run_command", side_effect=fake_run_command),
                mock.patch.object(apply_create.tools, "local_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "remote_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "load_changed_files_between", return_value=["src/creator.py"]),
                mock.patch.object(
                    apply_create.tools,
                    "select_pr_template",
                    return_value={"selected_path": "C:/repo/.github/pull_request_template.md", "fingerprint": contract.json_fingerprint("template")},
                ),
                mock.patch.object(
                    apply_create.tools,
                    "duplicate_check_summary",
                    return_value={
                        "status": "clear",
                        "matched_repo_slug": "owner/repo",
                        "matched_head": "feature/pr-create",
                        "existing_pr_count": 0,
                    },
                ),
                mock.patch.object(
                    sys,
                    "argv",
                    ["apply_pr_create.py", "--validation", str(validation_path), "--result-output", str(result_path), "--dry-run"],
                ),
            ):
                exit_code = apply_create.main()

            self.assertEqual(exit_code, 0)
            payload = self.read_json(result_path)
            self.assertTrue(payload["apply_succeeded"])
            self.assertTrue(payload["dry_run"])
            self.assertEqual(recorded_calls, [["gh", "auth", "status"]])

    def test_apply_stops_when_duplicate_check_changes_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, request_payload(repo_root))

            with (
                mock.patch.object(apply_create.tools, "run_command", return_value="Logged in to github.com"),
                mock.patch.object(apply_create.tools, "local_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "remote_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "load_changed_files_between", return_value=["src/creator.py"]),
                mock.patch.object(
                    apply_create.tools,
                    "select_pr_template",
                    return_value={"selected_path": "C:/repo/.github/pull_request_template.md", "fingerprint": contract.json_fingerprint("template")},
                ),
                mock.patch.object(
                    apply_create.tools,
                    "duplicate_check_summary",
                    return_value={
                        "status": "existing-open-pr",
                        "matched_repo_slug": "owner/repo",
                        "matched_head": "feature/pr-create",
                        "existing_pr_number": 9,
                        "existing_pr_url": "https://example.invalid/pr/9",
                        "existing_pr_count": 1,
                    },
                ),
                mock.patch.object(
                    sys,
                    "argv",
                    ["apply_pr_create.py", "--validation", str(validation_path), "--result-output", str(result_path)],
                ),
            ):
                exit_code = apply_create.main()

            self.assertEqual(exit_code, 1)
            payload = self.read_json(result_path)
            self.assertEqual(payload["stop_reason"], "stale_snapshot")

    def test_apply_verifies_created_pr_matches_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            validation = request_payload(repo_root)
            self.write_json(validation_path, validation)
            command_calls: list[list[str]] = []

            def fake_run_command(args: list[str], cwd: Path) -> str:
                command_calls.append(args)
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in to github.com"
                if args[:3] == ["gh", "pr", "create"]:
                    return "https://example.invalid/pr/10"
                raise AssertionError(f"Unexpected command: {args}")

            created_pr = {
                "number": 10,
                "url": "https://example.invalid/pr/10",
                "title": validation["normalized_create_request"]["title"],
                "body": validation["normalized_create_request"]["body"],
                "headRefName": "feature/pr-create",
                "baseRefName": "main",
                "isDraft": True,
                "labels": [{"name": "automation"}],
                "assignees": [{"login": "bob"}],
                "reviewRequests": [{"requestedReviewer": {"login": "alice"}}],
                "milestone": {"title": "v1"},
                "maintainerCanModify": False,
            }

            with (
                mock.patch.object(apply_create.tools, "run_command", side_effect=fake_run_command),
                mock.patch.object(apply_create.tools, "local_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "remote_head_oid", return_value="abc123"),
                mock.patch.object(apply_create.tools, "load_changed_files_between", return_value=["src/creator.py"]),
                mock.patch.object(
                    apply_create.tools,
                    "select_pr_template",
                    return_value={"selected_path": "C:/repo/.github/pull_request_template.md", "fingerprint": contract.json_fingerprint("template")},
                ),
                mock.patch.object(
                    apply_create.tools,
                    "duplicate_check_summary",
                    side_effect=[
                        {
                            "status": "clear",
                            "matched_repo_slug": "owner/repo",
                            "matched_head": "feature/pr-create",
                            "existing_pr_count": 0,
                        }
                    ],
                ),
                mock.patch.object(apply_create.tools, "load_open_prs_for_head", return_value=[created_pr]),
                mock.patch.object(
                    sys,
                    "argv",
                    ["apply_pr_create.py", "--validation", str(validation_path), "--result-output", str(result_path)],
                ),
            ):
                exit_code = apply_create.main()

            self.assertEqual(exit_code, 0)
            payload = self.read_json(result_path)
            self.assertTrue(payload["apply_succeeded"])
            self.assertEqual(payload["created_pr_number"], 10)
            self.assertIn(["gh", "pr", "create"], [call[:3] for call in command_calls])


if __name__ == "__main__":
    unittest.main()
