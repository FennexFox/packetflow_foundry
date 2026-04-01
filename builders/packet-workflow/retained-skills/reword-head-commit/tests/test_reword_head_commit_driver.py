from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reword_head_commit_test_support import commit_file, load_json, make_repo, run_git, write_rules_file

import reword_head_commit  # type: ignore  # noqa: E402


class RewordHeadCommitDriverTests(unittest.TestCase):
    def seed_repo(self) -> tuple[object, Path]:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        rules_text = "\n".join(
            [
                "## Format",
                "`<type>(<scope>): <subject>`",
                "## Types",
                "- `fix`",
                "## Scopes",
                "scope is required",
                "## Subject Rules",
                "50 characters or fewer",
            ]
        )
        write_rules_file(repo, rules_text)
        commit_file(
            repo,
            ".github/instructions/commit-message.instructions.md",
            rules_text,
            "fix(repo): add commit rules",
        )
        commit_file(
            repo,
            "src/app.py",
            "print('hi')\n",
            "fix(app): seed",
            author_name="Author",
            author_email="author@example.com",
            author_date="2026-03-27T00:00:00Z",
        )
        return temp_dir, repo

    def run_driver(self, *args: str, cwd: Path | None = None) -> tuple[int, dict]:
        stdout = io.StringIO()
        chdir_context = contextlib.chdir(cwd) if cwd is not None else contextlib.nullcontext()
        with (
            mock.patch.object(sys, "argv", ["reword_head_commit.py", *args]),
            chdir_context,
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = reword_head_commit.main()
        return exit_code, json.loads(stdout.getvalue())

    def test_dry_run_reports_force_push_likely_when_upstream_exists(self) -> None:
        _temp_dir, repo = self.seed_repo()
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp) / "remote.git"
            remote.mkdir()
            run_git(remote, "init", "--bare")
            run_git(repo, "remote", "add", "origin", str(remote))
            run_git(repo, "push", "-u", "origin", "HEAD")

            message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
            message_path.parent.mkdir(parents=True, exist_ok=True)
            message_path.write_text("fix(app): rename seed\n", encoding="utf-8")

            exit_code, summary = self.run_driver("--repo", str(repo), "--message-file", str(message_path))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "dry-run")
        validation = load_json(Path(summary["validation_path"]))
        apply_result = load_json(Path(summary["apply_result_path"]))
        self.assertTrue(validation["force_push_likely"])
        self.assertTrue(apply_result["force_push_likely"])

    def test_apply_amends_head_without_changing_parent_or_tree(self) -> None:
        _temp_dir, repo = self.seed_repo()
        old_head = run_git(repo, "rev-parse", "HEAD")
        old_parent = run_git(repo, "show", "-s", "--format=%P", old_head)
        old_tree = run_git(repo, "show", "-s", "--format=%T", old_head)
        old_author = run_git(repo, "show", "-s", "--format=%an|%ae|%aI", old_head)
        old_committer = run_git(repo, "show", "-s", "--format=%cn|%ce|%cI", old_head)
        message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text(
            "fix(app): rename seed\n\n- clarify the head commit message\n",
            encoding="utf-8",
        )

        exit_code, summary = self.run_driver("--repo", str(repo), "--message-file", str(message_path), "--apply")

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ok")
        new_head = summary["new_head"]
        self.assertIsInstance(new_head, str)
        self.assertNotEqual(new_head, old_head)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%P", new_head), old_parent)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%T", new_head), old_tree)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%an|%ae|%aI", new_head), old_author)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%cn|%ce|%cI", new_head), old_committer)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%B", new_head), "fix(app): rename seed\n\n- clarify the head commit message")
        apply_result = load_json(Path(summary["apply_result_path"]))
        self.assertTrue(apply_result["amend_succeeded"])
        self.assertTrue(apply_result["tree_unchanged"])

    def test_apply_exports_committer_identity_for_amend(self) -> None:
        _temp_dir, repo = self.seed_repo()
        commit_file(
            repo,
            "src/committer.py",
            "print('committer')\n",
            "fix(app): add committer coverage",
            author_name="Author",
            author_email="author@example.com",
            author_date="2026-03-28T00:00:00Z",
            committer_name="Committer",
            committer_email="committer@example.com",
            committer_date="2026-03-29T00:00:00Z",
        )
        message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text("fix(app): rename committer coverage\n", encoding="utf-8")

        captured_env: dict[str, str] = {}

        def fake_git_result(
            repo_root: Path,
            args: list[str],
            *,
            env: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            captured_env.clear()
            captured_env.update(env or {})
            self.assertEqual(args[:2], ["commit", "--amend"])
            return subprocess.CompletedProcess(["git", *args], 0, "", "")

        with mock.patch.object(reword_head_commit, "git_result", side_effect=fake_git_result):
            exit_code, summary = self.run_driver(
                "--repo",
                str(repo),
                "--message-file",
                str(message_path),
                "--apply",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ok")
        apply_result = load_json(Path(summary["apply_result_path"]))
        self.assertTrue(apply_result["amend_succeeded"])
        head_commit = run_git(repo, "rev-parse", "HEAD")
        expected_author = run_git(repo, "show", "-s", "--format=%an|%ae|%aI", head_commit).split("|")
        expected_committer = run_git(repo, "show", "-s", "--format=%cn|%ce|%cI", head_commit).split("|")
        self.assertEqual(captured_env["GIT_AUTHOR_NAME"], expected_author[0])
        self.assertEqual(captured_env["GIT_AUTHOR_EMAIL"], expected_author[1])
        self.assertEqual(captured_env["GIT_AUTHOR_DATE"], expected_author[2])
        self.assertEqual(captured_env["GIT_COMMITTER_NAME"], expected_committer[0])
        self.assertEqual(captured_env["GIT_COMMITTER_EMAIL"], expected_committer[1])
        self.assertEqual(captured_env["GIT_COMMITTER_DATE"], expected_committer[2])

    def test_apply_preserves_distinct_committer_metadata(self) -> None:
        _temp_dir, repo = self.seed_repo()
        old_head = commit_file(
            repo,
            "src/committer.py",
            "print('committer')\n",
            "fix(app): add committer coverage",
            author_name="Author",
            author_email="author@example.com",
            author_date="2026-03-28T00:00:00Z",
            committer_name="Committer",
            committer_email="committer@example.com",
            committer_date="2026-03-29T00:00:00Z",
        )
        old_author = run_git(repo, "show", "-s", "--format=%an|%ae|%aI", old_head)
        old_committer = run_git(repo, "show", "-s", "--format=%cn|%ce|%cI", old_head)
        message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text("fix(app): rename committer coverage\n", encoding="utf-8")

        exit_code, summary = self.run_driver("--repo", str(repo), "--message-file", str(message_path), "--apply")

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ok")
        new_head = summary["new_head"]
        self.assertIsInstance(new_head, str)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%an|%ae|%aI", new_head), old_author)
        self.assertEqual(run_git(repo, "show", "-s", "--format=%cn|%ce|%cI", new_head), old_committer)

    def test_express_path_rejects_non_explicit_rules(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(repo, "src/app.py", "print('hi')\n", "fix(app): seed")
        commit_file(repo, "src/worker.py", "print('bye')\n", "fix(app): follow-up")
        commit_file(repo, "src/final.py", "print('done')\n", "fix(app): latest")
        exit_code, summary = self.run_driver("--repo", str(repo), "--message", "fix(app): rename latest")

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "invalid")
        validation = load_json(Path(summary["validation_path"]))
        self.assertEqual(validation["rules_reliability"], "derived")
        self.assertIn("explicit_rules_required", {item["code"] for item in validation["errors"]})

    def test_dirty_worktree_blocks_validation(self) -> None:
        _temp_dir, repo = self.seed_repo()
        (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
        exit_code, summary = self.run_driver("--repo", str(repo), "--message", "fix(app): rename seed")

        self.assertEqual(exit_code, 1)
        validation = load_json(Path(summary["validation_path"]))
        self.assertIn("dirty_worktree", {item["code"] for item in validation["errors"]})

    def test_active_git_operation_blocks_validation(self) -> None:
        _temp_dir, repo = self.seed_repo()
        git_dir = Path(run_git(repo, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = repo / git_dir
        (git_dir / "MERGE_HEAD").write_text("deadbeef\n", encoding="utf-8")
        self.addCleanup(lambda: (git_dir / "MERGE_HEAD").unlink(missing_ok=True))
        exit_code, summary = self.run_driver("--repo", str(repo), "--message", "fix(app): rename seed")

        self.assertEqual(exit_code, 1)
        validation = load_json(Path(summary["validation_path"]))
        self.assertIn("active_git_operation", {item["code"] for item in validation["errors"]})

    def test_invalid_message_returns_validation_summary_instead_of_generic_failure(self) -> None:
        _temp_dir, repo = self.seed_repo()

        exit_code, summary = self.run_driver("--repo", str(repo), "--message", "")

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "invalid")
        validation = load_json(Path(summary["validation_path"]))
        apply_result = load_json(Path(summary["apply_result_path"]))
        self.assertIn("missing_new_message", {item["code"] for item in validation["errors"]})
        self.assertEqual(apply_result["status"], "blocked")
        self.assertIsNone(apply_result["operation"]["new_subject"])

    def test_invalid_apply_does_not_report_attempted_amend(self) -> None:
        _temp_dir, repo = self.seed_repo()

        exit_code, summary = self.run_driver("--repo", str(repo), "--message", "", "--apply")

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["status"], "invalid")
        apply_result = load_json(Path(summary["apply_result_path"]))
        eval_log = load_json(Path(summary["evaluation_log_path"]))
        self.assertTrue(apply_result["apply_requested"])
        self.assertFalse(apply_result["apply_attempted"])
        self.assertEqual(apply_result["mutation_type"], "none")
        self.assertFalse(eval_log["safety"]["apply_attempted"])
        self.assertEqual(eval_log["safety"]["mutation_type"], "none")

    def test_relative_message_file_is_resolved_from_repo_root(self) -> None:
        _temp_dir, repo = self.seed_repo()
        message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text("fix(app): rename seed\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as outside_dir:
            exit_code, summary = self.run_driver(
                "--repo",
                str(repo),
                "--message-file",
                ".codex/tmp/packet-workflow/reword-head-commit/message.txt",
                cwd=Path(outside_dir),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "dry-run")


if __name__ == "__main__":
    unittest.main()
