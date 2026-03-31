from __future__ import annotations

import copy
import unittest

from reword_test_support import commit_file, make_repo

import collect_commit_rules  # type: ignore  # noqa: E402
import collect_recent_commits  # type: ignore  # noqa: E402
import reword_runtime_paths  # type: ignore  # noqa: E402
from reword_plan_contract import branch_state, detect_operation, validate_reword_plan_payload  # noqa: E402


class ValidateRewordPlanTests(unittest.TestCase):
    def make_context(self) -> tuple[object, object, dict, dict]:
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
                    "## Subject Rules",
                    "72 characters or fewer",
                ]
            ),
            "docs(repo): add commit rules",
        )
        commit_file(repo, "src/a.py", "one\n", "fix(core): seed")
        commit_file(repo, "src/b.py", "two\n", "fix(parser): follow-up")
        rules = collect_commit_rules.build_rules(repo)
        plan = collect_recent_commits.build_plan(repo, 2, rules)
        return temp_dir, repo, rules, plan

    def test_validator_normalizes_order_and_warns_on_derived_rules(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(repo, "README.md", "seed\n", "docs(repo): seed")
        commit_file(repo, "src/a.py", "one\n", "fix(core): seed")
        commit_file(repo, "src/b.py", "two\n", "fix(parser): follow-up")
        rules = collect_commit_rules.build_rules(repo)
        plan = collect_recent_commits.build_plan(repo, 2, rules)
        raw_plan = copy.deepcopy(plan)
        raw_plan["commits"][0]["new_message"] = "fix(core): seed"
        raw_plan["commits"][1]["new_message"] = "fix(parser): follow-up"
        raw_plan["commits"].reverse()

        payload = validate_reword_plan_payload(
            plan,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )

        self.assertTrue(payload["valid"])
        self.assertEqual([item["index"] for item in payload["normalized_rewrite_actions"]], [1, 2])
        self.assertIn("derived_rules_only", {item["code"] for item in payload["warnings"]})

    def test_validator_rejects_dirty_worktree_and_stale_fingerprint(self) -> None:
        _temp_dir, repo, rules, plan = self.make_context()
        raw_plan = copy.deepcopy(plan)
        raw_plan["commits"][0]["new_message"] = "fix(core): rewrite first"
        raw_plan["commits"][1]["new_message"] = "fix(parser): rewrite second"
        (repo / "src" / "scratch.py").write_text("dirty\n", encoding="utf-8")
        plan["context_fingerprint"] = "stale"

        payload = validate_reword_plan_payload(
            plan,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )

        self.assertFalse(payload["valid"])
        self.assertIn("dirty_worktree", payload["stop_reasons"])
        self.assertIn("stale_context_fingerprint", {item["code"] for item in payload["errors"]})

    def test_validator_rejects_root_rewrite_unsupported(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(repo, "src/app.py", "one\n", "fix(app): seed")
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
        plan = collect_recent_commits.build_plan(repo, 1, rules)
        raw_plan = copy.deepcopy(plan)
        raw_plan["commits"][0]["new_message"] = "fix(app): rewrite seed"

        payload = validate_reword_plan_payload(
            plan,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )

        self.assertFalse(payload["valid"])
        self.assertIn("root_rewrite_unsupported", payload["stop_reasons"])

    def test_validator_rejects_missing_and_invalid_messages(self) -> None:
        _temp_dir, repo, rules, plan = self.make_context()
        raw_plan = {"commits": copy.deepcopy(plan["commits"])}
        raw_plan["commits"][0]["new_message"] = ""
        raw_plan["commits"][1]["new_message"] = "bad subject"

        payload = validate_reword_plan_payload(
            plan,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )

        self.assertFalse(payload["valid"])
        error_codes = {item["code"] for item in payload["errors"]}
        self.assertIn("missing_new_message", error_codes)
        self.assertIn("invalid_subject_format", error_codes)

    def test_repo_codex_tmp_artifact_root_does_not_mark_worktree_dirty(self) -> None:
        _temp_dir, repo, rules, plan = self.make_context()
        raw_plan = copy.deepcopy(plan)
        raw_plan["commits"][0]["new_message"] = "fix(core): rewrite first"
        raw_plan["commits"][1]["new_message"] = "fix(parser): rewrite second"
        artifact_path = (
            reword_runtime_paths.resolve_runtime_namespace_root(repo)
            / "test-run"
            / "message-template.json"
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("artifact\n", encoding="utf-8")

        payload = validate_reword_plan_payload(
            plan,
            rules,
            raw_plan,
            repo_state=branch_state(repo),
            active_operation=detect_operation(repo),
        )

        self.assertTrue(payload["valid"])
        self.assertNotIn("dirty_worktree", payload["stop_reasons"])


if __name__ == "__main__":
    unittest.main()
