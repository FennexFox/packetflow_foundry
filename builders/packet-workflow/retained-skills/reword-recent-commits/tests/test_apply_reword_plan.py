from __future__ import annotations

import contextlib
import copy
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from reword_test_support import commit_file, load_json, make_repo, run_git, write_json

import apply_reword_plan  # type: ignore  # noqa: E402
import collect_commit_rules  # type: ignore  # noqa: E402
import collect_recent_commits  # type: ignore  # noqa: E402
from reword_plan_contract import branch_state, detect_operation, validate_reword_plan_payload  # noqa: E402


class ApplyRewordPlanTests(unittest.TestCase):
    def assert_utc_timestamp_equal(self, actual: str, expected: str) -> None:
        def normalize(value: str) -> datetime:
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).astimezone(timezone.utc)

        self.assertEqual(normalize(actual), normalize(expected))

    def build_validated_plan(self) -> tuple[object, Path, dict, dict]:
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
        commit_file(repo, "src/a.py", "one\n", "fix(core): seed", author_name="One", author_email="one@example.com", author_date="2026-03-27T00:00:00Z")
        commit_file(repo, "src/b.py", "two\n", "fix(parser): follow-up", author_name="Two", author_email="two@example.com", author_date="2026-03-27T00:01:00Z")
        rules = collect_commit_rules.build_rules(repo)
        context = collect_recent_commits.build_plan(repo, 2, rules)
        raw_plan = copy.deepcopy(context)
        raw_plan["commits"][0]["new_message"] = "fix(core): rewrite seed"
        raw_plan["commits"][1]["new_message"] = "fix(parser): rewrite follow-up\n\n- Preserve replay safety."
        validated = validate_reword_plan_payload(
            context,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )
        self.assertTrue(validated["valid"])
        return temp_dir, repo, context, validated

    def run_apply(
        self,
        context: dict,
        validated: dict,
        *,
        dry_run: bool,
        temp_root: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        context_path = tmp_path / "context.json"
        plan_path = tmp_path / "validated.json"
        result_path = tmp_path / "result.json"
        write_json(context_path, context)
        write_json(plan_path, validated)

        stdout = io.StringIO()
        argv = [
            "apply_reword_plan.py",
            "--context",
            str(context_path),
            "--plan",
            str(plan_path),
            "--result-output",
            str(result_path),
        ]
        if dry_run:
            argv.append("--dry-run")
        if temp_root is not None:
            argv.extend(["--temp-root", str(temp_root)])
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.dict(os.environ, env or {}, clear=False),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = apply_reword_plan.main()
        return exit_code, load_json(result_path)

    def test_dry_run_leaves_head_unchanged(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        head_before = run_git(repo, "rev-parse", "HEAD")

        exit_code, result = self.run_apply(context, validated, dry_run=True)

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), head_before)
        self.assertEqual(result["stop_reasons"], [])

    def test_apply_rewrites_messages_and_preserves_author_metadata(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()

        exit_code, result = self.run_apply(context, validated, dry_run=False)

        self.assertEqual(exit_code, 0)
        self.assertTrue(result["apply_succeeded"])
        subjects = run_git(repo, "log", "-n", "2", "--reverse", "--format=%s").splitlines()
        self.assertEqual(subjects, ["fix(core): rewrite seed", "fix(parser): rewrite follow-up"])
        authors = run_git(repo, "log", "-n", "2", "--reverse", "--format=%an|%ae|%aI").splitlines()
        first_name, first_email, first_date = authors[0].split("|", 2)
        second_name, second_email, second_date = authors[1].split("|", 2)
        self.assertEqual(first_name, "One")
        self.assertEqual(first_email, "one@example.com")
        self.assert_utc_timestamp_equal(first_date, "2026-03-27T00:00:00+00:00")
        self.assertEqual(second_name, "Two")
        self.assertEqual(second_email, "two@example.com")
        self.assert_utc_timestamp_equal(second_date, "2026-03-27T00:01:00+00:00")
        self.assertEqual(result["counters"]["commits_rewritten"], 2)

    def test_apply_refuses_root_rewrite_context(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        head_commit = commit_file(repo, "src/app.py", "one\n", "fix(app): seed")
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix"],
                "scope_required": True,
                "scope_suggestions": ["app"],
                "subject_length_limit": 72,
                "subject_rules": [],
                "body_rules": [],
                "references_rules": [],
                "repo_defaults": [],
            },
            "rule_derivation": {
                "format_source": "commit_message_instructions",
                "allowed_types_source": "commit_message_instructions",
                "scope_required_source": "commit_message_instructions",
                "subject_length_limit_source": "commit_message_instructions",
                "repo_defaults_source": "commit_message_instructions",
            },
            "recent_scope_vocabulary": ["app"],
            "recent_subject_samples": ["fix(app): seed"],
            "rules_reliability": "explicit",
        }
        context = collect_recent_commits.build_plan(repo, 1, rules)
        validated = {
            "valid": True,
            "context_fingerprint": context["context_fingerprint"],
            "message_set_fingerprint": "x" * 64,
            "normalized_rewrite_actions": [
                {
                    "index": 1,
                    "hash": head_commit,
                    "new_message": "fix(app): rewrite seed",
                }
            ],
            "warnings": [],
            "counters": {},
            "rewrite_scope": {
                "branch": context["branch"],
                "count": 1,
                "head_commit": context["head_commit"],
                "base_commit": context["base_commit"],
            },
            "rules_reliability": rules["rules_reliability"],
            "fingerprint_match": True,
            "stop_reasons": [],
        }

        exit_code, result = self.run_apply(context, validated, dry_run=False)

        self.assertEqual(exit_code, 1)
        self.assertIn("root_rewrite_unsupported", result["stop_reasons"])

    def test_apply_detects_head_drift(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        commit_file(repo, "src/c.py", "three\n", "fix(extra): drift")

        exit_code, result = self.run_apply(context, validated, dry_run=False)

        self.assertEqual(exit_code, 1)
        self.assertTrue({"recent_hash_drift", "head_commit_drift"} & set(result["stop_reasons"]))

    def test_apply_reports_replay_failure_and_cleanup_state(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        original_git_result = apply_reword_plan.git_result

        def failing_git_result(repo_path: Path, args: list[str], *, env: dict[str, str] | None = None):
            if args[:2] == ["cherry-pick", "--no-commit"]:
                return mock.Mock(returncode=1, stdout="", stderr="simulated cherry-pick failure")
            return original_git_result(repo_path, args, env=env)

        with mock.patch.object(apply_reword_plan, "git_result", side_effect=failing_git_result):
            with mock.patch.object(
                apply_reword_plan,
                "cleanup_artifacts",
                return_value=(False, ["C:/tmp/reword-leftover"]),
            ):
                head_before = run_git(repo, "rev-parse", "HEAD")
                exit_code, result = self.run_apply(context, validated, dry_run=False)

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["stop_reasons"], ["replay_failed"])
        self.assertFalse(result["cleanup_succeeded"])
        self.assertEqual(result["leftover_paths"], ["C:/tmp/reword-leftover"])
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), head_before)

    def test_apply_uses_cli_temp_root_over_env(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        cli_temp_root = repo.parent / "cli-temp-root"
        env_temp_root = repo.parent / "env-temp-root"

        exit_code, result = self.run_apply(
            context,
            validated,
            dry_run=False,
            temp_root=cli_temp_root,
            env={apply_reword_plan.TEMP_ROOT_ENV_VAR: str(env_temp_root)},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["temp_root_parent"], str(cli_temp_root.resolve()))
        self.assertEqual(result["temp_root_source"], "cli")

    def test_apply_uses_env_temp_root_without_cli_override(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        env_temp_root = repo.parent / "env-temp-root"

        exit_code, result = self.run_apply(
            context,
            validated,
            dry_run=False,
            env={apply_reword_plan.TEMP_ROOT_ENV_VAR: str(env_temp_root)},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["temp_root_parent"], str(env_temp_root.resolve()))
        self.assertEqual(result["temp_root_source"], "env")

    def test_apply_reports_actionable_temp_root_permission_failure(self) -> None:
        _temp_dir, repo, context, validated = self.build_validated_plan()
        blocked_temp_root = repo.parent / "blocked-temp-root"
        blocked_temp_root.write_text("not a directory\n", encoding="utf-8")
        head_before = run_git(repo, "rev-parse", "HEAD")

        exit_code, result = self.run_apply(
            context,
            validated,
            dry_run=False,
            temp_root=blocked_temp_root,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(result["stop_reasons"], ["replay_failed"])
        self.assertEqual(result["temp_root_parent"], str(blocked_temp_root.resolve()))
        self.assertEqual(result["temp_root_source"], "cli")
        self.assertIn(str(blocked_temp_root.resolve()), result["error_message"])
        self.assertIn("--temp-root", result["error_message"])
        self.assertEqual(result["leftover_paths"], [])
        self.assertFalse(result["cleanup_attempted"])
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), head_before)


if __name__ == "__main__":
    unittest.main()
