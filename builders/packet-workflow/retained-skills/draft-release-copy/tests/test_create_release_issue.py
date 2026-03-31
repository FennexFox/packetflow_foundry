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

import create_release_issue as create_release_issue


class CreateReleaseIssueTests(unittest.TestCase):
    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_dry_run_reuses_existing_issue_and_plans_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            body_path = tmp / "body.md"
            result_path = tmp / "issue-result.json"
            body_path.write_text("# Body\n", encoding="utf-8")

            def fake_run_command(args: list[str], cwd: Path, check: bool = True) -> str:
                if args[:4] == ["gh", "repo", "view", "--json"]:
                    return json.dumps({"nameWithOwner": "owner/repo"})
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in with project scope."
                if args[:3] == ["gh", "issue", "list"]:
                    return json.dumps(
                        [
                            {
                                "number": 12,
                                "title": "[Release] v1.2.3",
                                "url": "https://example.invalid/issues/12",
                                "state": "OPEN",
                            }
                        ]
                    )
                self.fail(f"Unexpected command: {args}")

            stdout = io.StringIO()
            with mock.patch.object(create_release_issue, "run_command", side_effect=fake_run_command), mock.patch.object(
                sys,
                "argv",
                [
                    "create_release_issue.py",
                    "--title",
                    "[Release] v1.2.3",
                    "--body-file",
                    str(body_path),
                    "--repo-root",
                    str(repo_root),
                    "--reuse-existing",
                    "--sync-existing-body",
                    "--project-mode",
                    "auto-add-first",
                    "--result-output",
                    str(result_path),
                    "--dry-run",
                ],
            ), redirect_stdout(stdout):
                exit_code = create_release_issue.main()

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["mutation_type"], "gh_issue_edit_existing")
            self.assertEqual(payload["existing_issue_number"], 12)
            self.assertTrue(payload["project_scope_available"])
            self.assertTrue(payload["project_flag_used"])
            self.assertEqual(
                payload["command"][:5],
                ["gh", "issue", "edit", "12", "--title"],
            )
            self.assertIn("--add-project", payload["command"])
            self.assertEqual(self.read_json(result_path)["mutation_type"], "gh_issue_edit_existing")

    def test_sync_existing_body_requires_reuse_existing_before_any_gh_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            body_path = tmp / "body.md"
            body_path.write_text("# Body\n", encoding="utf-8")

            stderr = io.StringIO()
            with mock.patch.object(
                create_release_issue,
                "run_command",
                side_effect=AssertionError("gh command should not run for invalid local input contract"),
            ), mock.patch.object(
                sys,
                "argv",
                [
                    "create_release_issue.py",
                    "--title",
                    "[Release] v1.2.3",
                    "--body-file",
                    str(body_path),
                    "--repo-root",
                    str(repo_root),
                    "--sync-existing-body",
                ],
            ), redirect_stderr(stderr):
                exit_code = create_release_issue.main()

            self.assertEqual(exit_code, 1)
            self.assertIn("--sync-existing-body requires --reuse-existing", stderr.getvalue())

    def test_missing_body_file_stops_before_any_gh_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            missing_body_path = tmp / "missing.md"

            stderr = io.StringIO()
            with mock.patch.object(
                create_release_issue,
                "run_command",
                side_effect=AssertionError("gh command should not run when body file is missing"),
            ), mock.patch.object(
                sys,
                "argv",
                [
                    "create_release_issue.py",
                    "--title",
                    "[Release] v1.2.3",
                    "--body-file",
                    str(missing_body_path),
                    "--repo-root",
                    str(repo_root),
                ],
            ), redirect_stderr(stderr):
                exit_code = create_release_issue.main()

            self.assertEqual(exit_code, 1)
            self.assertIn("body file not found", stderr.getvalue())

    def test_require_scope_stops_without_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            body_path = tmp / "body.md"
            body_path.write_text("# Body\n", encoding="utf-8")
            recorded_calls: list[list[str]] = []

            def fake_run_command(args: list[str], cwd: Path, check: bool = True) -> str:
                recorded_calls.append(args)
                if args[:3] == ["gh", "auth", "status"]:
                    return "Logged in."
                self.fail(f"Unexpected command: {args}")

            stderr = io.StringIO()
            with mock.patch.object(create_release_issue, "run_command", side_effect=fake_run_command), mock.patch.object(
                sys,
                "argv",
                [
                    "create_release_issue.py",
                    "--title",
                    "[Release] v1.2.3",
                    "--body-file",
                    str(body_path),
                    "--repo-root",
                    str(repo_root),
                    "--project-mode",
                    "require-scope",
                    "--reuse-existing",
                ],
            ), redirect_stderr(stderr):
                exit_code = create_release_issue.main()

            self.assertEqual(exit_code, 1)
            self.assertIn("project scope is required but not available", stderr.getvalue())
            self.assertEqual(recorded_calls, [["gh", "auth", "status"]])

    def test_require_scope_stops_cleanly_when_gh_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_root = tmp / "repo"
            repo_root.mkdir()
            body_path = tmp / "body.md"
            body_path.write_text("# Body\n", encoding="utf-8")

            stderr = io.StringIO()
            with mock.patch.object(create_release_issue.subprocess, "run", side_effect=FileNotFoundError("gh")), mock.patch.object(
                sys,
                "argv",
                [
                    "create_release_issue.py",
                    "--title",
                    "[Release] v1.2.3",
                    "--body-file",
                    str(body_path),
                    "--repo-root",
                    str(repo_root),
                    "--project-mode",
                    "require-scope",
                ],
            ), redirect_stderr(stderr):
                exit_code = create_release_issue.main()

            self.assertEqual(exit_code, 1)
            self.assertIn("project scope is required but not available", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
