from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from reword_test_support import commit_file, load_json, make_repo, run_git

import reword_recent_commits  # type: ignore  # noqa: E402
import reword_runtime_paths  # type: ignore  # noqa: E402
from reword_plan_contract import branch_state  # noqa: E402


class RewordRecentCommitsDriverTests(unittest.TestCase):
    def seed_repo(self) -> tuple[object, Path]:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(
            repo,
            ".github/instructions/commit-message.instructions.md",
            "\n".join(
                [
                    "## Format",
                    "`<type>(<scope>): <subject>`",
                    "## Types",
                    "- `fix`",
                    "- `docs`",
                    "## Scopes",
                    "scope is required",
                ]
            ),
            "docs(repo): add commit rules",
        )
        commit_file(repo, "src/a.py", "one\n", "fix(core): seed")
        commit_file(repo, "src/b.py", "two\n", "fix(parser): follow-up")
        return temp_dir, repo

    def run_driver(self, *args: str) -> tuple[int, dict]:
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["reword_recent_commits.py", *args]), contextlib.redirect_stdout(stdout):
            exit_code = reword_recent_commits.main()
        return exit_code, json.loads(stdout.getvalue())

    def write_messages(self, template_path: Path) -> None:
        template = load_json(template_path)
        template["commits"][0]["new_message"] = "fix(core): rewrite seed"
        template["commits"][1]["new_message"] = "fix(parser): rewrite follow-up"
        template_path.write_text(json.dumps(template, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def test_prepare_only_uses_repo_codex_tmp_artifact_root_without_dirtying_repo(self) -> None:
        _temp_dir, repo = self.seed_repo()

        exit_code, summary = self.run_driver("--repo", str(repo), "--count", "2", "--prepare-only")

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "prepared")
        artifact_root = Path(summary["artifact_root"])
        template_path = Path(summary["message_template_path"])
        artifact_parent = reword_runtime_paths.resolve_runtime_namespace_root(repo)
        self.assertTrue(artifact_root.is_relative_to(artifact_parent))
        self.assertTrue(template_path.is_file())
        self.assertFalse(branch_state(repo)["working_tree_dirty"])
        self.assertEqual(run_git(repo, "status", "--short"), "")

    def test_messages_file_dry_run_validates_and_finalizes_eval_log(self) -> None:
        _temp_dir, repo = self.seed_repo()
        _, prepare_summary = self.run_driver("--repo", str(repo), "--count", "2", "--prepare-only")
        template_path = Path(prepare_summary["message_template_path"])
        self.write_messages(template_path)
        head_before = run_git(repo, "rev-parse", "HEAD")

        exit_code, summary = self.run_driver(
            "--repo",
            str(repo),
            "--count",
            "2",
            "--messages-file",
            str(template_path),
            "--dry-run",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "dry-run")
        self.assertEqual(summary["next_action"], "apply")
        validated = load_json(Path(summary["validated_path"]))
        apply_result = load_json(Path(summary["apply_result_path"]))
        eval_log = load_json(Path(summary["evaluation_log_path"]))
        self.assertTrue(validated["valid"])
        self.assertEqual(apply_result["status"], "dry-run")
        self.assertFalse(eval_log["safety"]["apply_attempted"])
        self.assertTrue(eval_log["safety"]["validation_passed"])
        self.assertEqual(eval_log["quality"]["result_status"], "dry-run")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), head_before)

    def test_messages_file_apply_updates_head(self) -> None:
        _temp_dir, repo = self.seed_repo()
        _, prepare_summary = self.run_driver("--repo", str(repo), "--count", "2", "--prepare-only")
        template_path = Path(prepare_summary["message_template_path"])
        self.write_messages(template_path)
        head_before = run_git(repo, "rev-parse", "HEAD")

        exit_code, summary = self.run_driver(
            "--repo",
            str(repo),
            "--count",
            "2",
            "--messages-file",
            str(template_path),
            "--apply",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["next_action"], "done")
        self.assertNotEqual(summary["new_head"], head_before)
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), summary["new_head"])
        subjects = run_git(repo, "log", "-n", "2", "--reverse", "--format=%s").splitlines()
        self.assertEqual(subjects, ["fix(core): rewrite seed", "fix(parser): rewrite follow-up"])
        eval_log = load_json(Path(summary["evaluation_log_path"]))
        self.assertTrue(eval_log["safety"]["apply_succeeded"])


if __name__ == "__main__":
    unittest.main()
