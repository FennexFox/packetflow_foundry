from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import apply_pr_writeup as apply_pr_writeup  # noqa: E402
import validate_pr_writeup_edit as validator  # noqa: E402


def collected_context(repo_root: Path) -> dict:
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
        },
        "changed_files": [
            "README.md",
            "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
        ],
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 1, "sample_files": ["README.md"]},
            "tests": {"count": 0, "sample_files": []},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
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
        "checks": {
            "title_matches_conventional_commit": True,
            "title_length": 42,
            "body_has_template_sections": True,
        },
    }


def replacement_body() -> str:
    return "\n".join(
        [
            "## Why",
            "Clarify the shipped behavior and add a guarded PR edit path.",
            "## What changed",
            "- Added a pre-edit snapshot guard before applying PR text.",
            "- Confirmed the updated writeup after apply.",
            "## How",
            "- Re-fetched the live PR snapshot before gh pr edit.",
            "## Risk / Rollback",
            "- Revert the PR text update if the replacement is inaccurate.",
            "## Testing",
            "- Ran `python -m unittest discover tests`.",
        ]
    )


class ApplyPrWriteupTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def validation_payload(self, repo_root: Path) -> dict:
        context = collected_context(repo_root)
        normalized_edit = {
            "repo_root": str(repo_root),
            "repo_slug": "owner/repo",
            "pr_number": 7,
            "title": "docs(pr-writeup): add guarded apply helper",
            "body": replacement_body(),
            "validated_snapshot": {
                "title": context["pr"]["title"],
                "body": context["pr"]["body"],
                "url": context["pr"]["url"],
                "headRefName": context["pr"]["headRefName"],
                "headRefOid": context["pr"]["headRefOid"],
                "baseRefName": context["pr"]["baseRefName"],
                "changed_files": context["changed_files"],
            },
            "validation_commands": ["candidate lint", "gh auth status"],
            "review_mode": "targeted-delegation",
            "qa_gate": {
                "required": False,
                "reason": None,
                "qa_clear": False,
                "worker_claim_conflict": False,
                "raw_reread_reasons": [],
                "qa_summary": None,
            },
        }
        return {
            "valid": True,
            "can_apply": True,
            "normalized_edit": normalized_edit,
            "normalized_edit_fingerprint": validator.json_fingerprint(normalized_edit),
            "context_file_fingerprint": "unused-by-apply",
            "apply_gate_status": {
                "status": "pass",
                "applicable_stop_categories": ["stale_context", "validator_mismatch", "missing_auth", "unresolved_stop_reason"],
                "covered_stop_categories": ["stale_context", "validator_mismatch", "missing_auth", "unresolved_stop_reason"],
                "uncovered_stop_categories": [],
                "not_applicable_stop_categories": ["ambiguous_routing", "missing_required_evidence"],
                "local_stop_categories": ["invalid_candidate", "live_snapshot_unavailable", "unsupported_claims_detected", "qa_required"],
            },
        }

    def test_apply_rejects_qa_required_validation_without_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation = self.validation_payload(repo_root)
            validation["normalized_edit"]["qa_gate"] = {
                "required": True,
                "reason": "claim conflict requires QA cross-check",
                "qa_clear": False,
                "worker_claim_conflict": True,
                "raw_reread_reasons": [],
                "qa_summary": None,
            }
            validation["normalized_edit_fingerprint"] = validator.json_fingerprint(validation["normalized_edit"])
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, validation)

            stderr = io.StringIO()
            with mock.patch.object(
                apply_pr_writeup.tools,
                "run_command",
                side_effect=AssertionError("gh command should not run while QA gate is still closed"),
            ), mock.patch.object(
                sys,
                "argv",
                [
                    "apply_pr_writeup.py",
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(result_path),
                ],
            ), redirect_stderr(stderr):
                exit_code = apply_pr_writeup.main()

            self.assertEqual(exit_code, 1)
            payload = self.read_json(result_path)
            self.assertEqual(payload["stop_reason"], "validator_mismatch")
            self.assertIn("qa", stderr.getvalue().lower())

    def test_dry_run_stops_when_live_snapshot_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, self.validation_payload(repo_root))
            recorded_calls: list[list[str]] = []

            def fake_run_command(args: list[str], cwd: Path) -> str:
                recorded_calls.append(args)
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in to github.com"
                if args[:3] == ["gh", "pr", "view"]:
                    return json.dumps(collected_context(repo_root)["pr"])
                if args[:4] == ["gh", "pr", "diff", "7"]:
                    return "\n".join(
                        [
                            "README.md",
                            "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
                            "MAINTAINING.md",
                        ]
                    )
                raise AssertionError(f"Unexpected command: {args}")

            stderr = io.StringIO()
            with mock.patch.object(apply_pr_writeup.tools, "run_command", side_effect=fake_run_command), mock.patch.object(
                sys,
                "argv",
                [
                    "apply_pr_writeup.py",
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(result_path),
                    "--dry-run",
                ],
            ), redirect_stderr(stderr):
                exit_code = apply_pr_writeup.main()

            self.assertEqual(exit_code, 1)
            payload = self.read_json(result_path)
            self.assertEqual(payload["stop_reason"], "stale_context")
            self.assertEqual(payload["command"], None)
            stale_fields = payload["stale_fields"]
            self.assertEqual(stale_fields[0]["field"], "changed_files")
            self.assertEqual(
                recorded_calls,
                [
                    ["gh", "auth", "status"],
                    ["gh", "pr", "view", "7", "--json", "number,title,body,headRefName,headRefOid,baseRefName,url,closingIssuesReferences", "--repo", "owner/repo"],
                    ["gh", "pr", "diff", "7", "--name-only", "--repo", "owner/repo"],
                ],
            )
            self.assertIn("live PR snapshot changed", stderr.getvalue())

    def test_apply_rejects_tampered_validator_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            validation = self.validation_payload(repo_root)
            validation["normalized_edit"]["title"] = "docs(pr-writeup): tampered"
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            self.write_json(validation_path, validation)

            stderr = io.StringIO()
            with mock.patch.object(
                apply_pr_writeup.tools,
                "run_command",
                side_effect=AssertionError("gh command should not run for tampered validator output"),
            ), mock.patch.object(
                sys,
                "argv",
                [
                    "apply_pr_writeup.py",
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(result_path),
                ],
            ), redirect_stderr(stderr):
                exit_code = apply_pr_writeup.main()

            self.assertEqual(exit_code, 1)
            payload = self.read_json(result_path)
            self.assertEqual(payload["stop_reason"], "validator_mismatch")
            self.assertIn("validator mismatch", stderr.getvalue().lower())

    def test_apply_edits_after_snapshot_guard_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            context = collected_context(repo_root)
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            validation = self.validation_payload(repo_root)
            self.write_json(validation_path, validation)
            new_body = validation["normalized_edit"]["body"]
            new_title = validation["normalized_edit"]["title"]
            view_calls = 0

            def fake_run_command(args: list[str], cwd: Path) -> str:
                nonlocal view_calls
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in to github.com"
                if args[:3] == ["gh", "pr", "view"]:
                    view_calls += 1
                    if view_calls == 1:
                        return json.dumps(context["pr"])
                    confirmed = dict(context["pr"])
                    confirmed["title"] = new_title
                    confirmed["body"] = new_body
                    return json.dumps(confirmed)
                if args[:4] == ["gh", "pr", "diff", "7"]:
                    return "\n".join(context["changed_files"])
                if args[:3] == ["gh", "pr", "edit"]:
                    self.assertEqual(args[4], "--title")
                    self.assertEqual(args[5], new_title)
                    self.assertIn("--body-file", args)
                    return ""
                raise AssertionError(f"Unexpected command: {args}")

            stdout = io.StringIO()
            with mock.patch.object(apply_pr_writeup.tools, "run_command", side_effect=fake_run_command), mock.patch.object(
                sys,
                "argv",
                [
                    "apply_pr_writeup.py",
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(result_path),
                ],
            ), redirect_stdout(stdout):
                exit_code = apply_pr_writeup.main()

            self.assertEqual(exit_code, 0)
            payload = self.read_json(result_path)
            self.assertTrue(payload["apply_succeeded"])
            self.assertEqual(payload["command"][:3], ["gh", "pr", "edit"])
            self.assertEqual(payload["current_pr_url"], context["pr"]["url"])
            self.assertEqual(json.loads(stdout.getvalue())["apply_succeeded"], True)

    def test_apply_tolerates_crlf_body_normalization_in_confirmed_pr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            context = collected_context(repo_root)
            validation_path = tmp / "validation.json"
            result_path = tmp / "result.json"
            validation = self.validation_payload(repo_root)
            self.write_json(validation_path, validation)
            new_body = validation["normalized_edit"]["body"]
            new_title = validation["normalized_edit"]["title"]
            view_calls = 0

            def fake_run_command(args: list[str], cwd: Path) -> str:
                nonlocal view_calls
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in to github.com"
                if args[:3] == ["gh", "pr", "view"]:
                    view_calls += 1
                    if view_calls == 1:
                        return json.dumps(context["pr"])
                    confirmed = dict(context["pr"])
                    confirmed["title"] = new_title
                    confirmed["body"] = new_body.replace("\n", "\r\n") + "\r\n"
                    return json.dumps(confirmed)
                if args[:4] == ["gh", "pr", "diff", "7"]:
                    return "\n".join(context["changed_files"])
                if args[:3] == ["gh", "pr", "edit"]:
                    return ""
                raise AssertionError(f"Unexpected command: {args}")

            stdout = io.StringIO()
            with mock.patch.object(apply_pr_writeup.tools, "run_command", side_effect=fake_run_command), mock.patch.object(
                sys,
                "argv",
                [
                    "apply_pr_writeup.py",
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(result_path),
                ],
            ), redirect_stdout(stdout):
                exit_code = apply_pr_writeup.main()

            self.assertEqual(exit_code, 0)
            payload = self.read_json(result_path)
            self.assertTrue(payload["apply_succeeded"])
            self.assertEqual(payload["current_pr_url"], context["pr"]["url"])
            self.assertEqual(json.loads(stdout.getvalue())["apply_succeeded"], True)


if __name__ == "__main__":
    unittest.main()
