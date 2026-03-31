from __future__ import annotations

import unittest

from reword_test_support import commit_file, make_repo, run_git, write_rules_file

import collect_commit_rules  # type: ignore  # noqa: E402
import collect_recent_commits  # type: ignore  # noqa: E402


class CollectRewordContractsTests(unittest.TestCase):
    def test_collect_commit_rules_marks_explicit_reliability(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        write_rules_file(
            repo,
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
        )
        commit_file(repo, "README.md", "seed\n", "fix(repo): seed")

        payload = collect_commit_rules.build_rules(repo)

        self.assertEqual(payload["rules_reliability"], "explicit")
        self.assertEqual(payload["rules"]["format"], "<type>(<scope>): <subject>")
        self.assertEqual(payload["rules"]["allowed_types"], ["fix", "docs"])

    def test_collect_commit_rules_marks_fallback_without_explicit_guidance(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(repo, "README.md", "seed\n", "seed repo")

        payload = collect_commit_rules.build_rules(repo)

        self.assertEqual(payload["rules_reliability"], "fallback")
        self.assertEqual(payload["rules"]["format"], "<type>(<scope>): <subject>")

    def test_collect_recent_commits_attaches_context_fingerprint_for_root_commit_scope(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(repo, "src/app.py", "print('hi')\n", "fix(app): seed")
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

        self.assertIsNone(plan["base_commit"])
        self.assertEqual(plan["rules_reliability"], "explicit")
        self.assertTrue(plan["context_fingerprint"])

    def test_collect_recent_commits_detects_detached_head(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        write_rules_file(repo, "## Format\n`<type>(<scope>): <subject>`")
        first = commit_file(repo, "README.md", "seed\n", "fix(repo): seed")
        commit_file(repo, "src/app.py", "print('hi')\n", "fix(app): add app")
        run_git(repo, "checkout", first)
        rules = collect_commit_rules.build_rules(repo)

        plan = collect_recent_commits.build_plan(repo, 1, rules)

        self.assertTrue(plan["detached_head"])
        self.assertTrue(plan["context_fingerprint"])


if __name__ == "__main__":
    unittest.main()
