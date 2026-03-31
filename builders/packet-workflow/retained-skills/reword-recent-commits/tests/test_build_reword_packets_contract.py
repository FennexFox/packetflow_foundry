from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reword_test_support import commit_file, make_repo, write_json

import build_reword_packets  # type: ignore  # noqa: E402
from reword_plan_contract import (  # noqa: E402
    COMMON_PATH_CONTRACT,
    RAW_REREAD_ALLOWED_REASONS,
    build_context_fingerprint,
    compute_packet_metrics,
    estimate_tokens_from_bytes,
    json_bytes,
)


class BuildRewordPacketsContractTest(unittest.TestCase):
    def run_script(self, rules: dict, plan: dict) -> tuple[int, Path, dict, dict]:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        rules_path = tmp_path / "rules.json"
        plan_path = tmp_path / "plan.json"
        output_dir = tmp_path / "packets"
        result_path = tmp_path / "build-result.json"
        write_json(rules_path, rules)
        write_json(plan_path, plan)

        stdout = io.StringIO()
        argv = [
            "build_reword_packets.py",
            "--rules",
            str(rules_path),
            "--plan",
            str(plan_path),
            "--output-dir",
            str(output_dir),
            "--result-output",
            str(result_path),
        ]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = build_reword_packets.main()

        orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return exit_code, output_dir, orchestrator, result

    def test_broad_review_mode_uses_flat_contract_and_packet_ids(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        head_commit = commit_file(repo, "README.md", "seed\n", "chore(repo): seed")
        branch = build_reword_packets.branch_state(repo)["branch"] or "main"

        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix", "chore", "docs"],
                "scope_required": True,
                "subject_length_limit": 72,
                "body_rules": ["use bullets"],
                "references_rules": [],
                "scope_suggestions": ["infra"],
            },
            "rule_derivation": {
                "format_source": "commit_message_instructions",
                "allowed_types_source": "commit_message_instructions",
                "scope_required_source": "commit_message_instructions",
                "subject_length_limit_source": "commit_message_instructions",
                "repo_defaults_source": "commit_message_instructions",
            },
            "recent_scope_vocabulary": ["infra", "docs"],
            "recent_subject_samples": ["fix(parser): seed"],
            "rules_reliability": "explicit",
        }
        commits = []
        for index in range(1, 7):
            commits.append(
                {
                    "index": index,
                    "hash": f"{index}" * 40,
                    "short_hash": f"{index}" * 12,
                    "parent_hashes": ["0" * 40],
                    "subject": f"fix(parser): normalize case {index}",
                    "body": "",
                    "full_message": f"fix(parser): normalize case {index}",
                    "author_name": "Codex",
                    "author_email": "codex@example.com",
                    "author_date": "2026-03-27T00:00:00Z",
                    "files": ["src/parser.py", "docs/notes.md"] if index == 1 else [f"src/module_{index}.py"],
                    "shortstat": "1 file changed, 2 insertions(+), 1 deletion(-)",
                    "new_message": "",
                }
            )
        plan = {
            "repo_root": str(repo),
            "branch": branch,
            "detached_head": False,
            "count": len(commits),
            "head_commit": head_commit,
            "base_commit": head_commit,
            "active_operation": None,
            "commits": commits,
        }

        exit_code, output_dir, orchestrator, result = self.run_script(rules, plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(orchestrator["review_mode"], "broad-delegation")
        self.assertFalse(orchestrator["decision_ready_packets"])
        self.assertEqual(orchestrator["worker_return_contract"], "generic")
        self.assertEqual(orchestrator["worker_output_shape"], "flat")
        self.assertTrue(orchestrator["common_path_sufficient"])
        self.assertEqual(orchestrator["raw_reread_reasons"], [])
        self.assertEqual(orchestrator["common_path_contract"], COMMON_PATH_CONTRACT)
        self.assertEqual(orchestrator["reread_reason_values"], RAW_REREAD_ALLOWED_REASONS)
        self.assertEqual(
            orchestrator["task_packet_names"],
            ["rules_packet.json", "commit-01.json", "commit-02.json", "commit-03.json", "commit-04.json", "commit-05.json", "commit-06.json"],
        )
        self.assertEqual(
            orchestrator["task_packet_ids"],
            ["rules_packet", "commit-01", "commit-02", "commit-03", "commit-04", "commit-05", "commit-06"],
        )
        self.assertEqual(
            orchestrator["packet_worker_map"],
            {
                "rules_packet": ["docs_verifier"],
                "commit-01": ["evidence_summarizer"],
                "commit-02": ["evidence_summarizer"],
                "commit-03": ["evidence_summarizer"],
                "commit-04": ["evidence_summarizer"],
                "commit-05": ["evidence_summarizer"],
                "commit-06": ["evidence_summarizer"],
            },
        )
        self.assertEqual(
            orchestrator["worker_output_fields"],
            ["commit_indexes", "primary_intent", "suggested_type_scope", "body_needed", "evidence_files", "ambiguity", "confidence", "reread_control"],
        )
        self.assertEqual(orchestrator["context_fingerprint"], build_context_fingerprint(plan, rules))
        self.assertEqual(orchestrator["rules_reliability"], "explicit")

        global_packet = json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8"))
        self.assertFalse(global_packet["decision_ready_packets"])
        self.assertEqual(global_packet["worker_return_contract"], "generic")
        self.assertEqual(global_packet["worker_output_shape"], "flat")
        self.assertTrue(global_packet["common_path_sufficient"])
        self.assertEqual(global_packet["raw_reread_reasons"], [])
        self.assertNotIn("candidate_field_bundles", global_packet)

        commit_packet = json.loads((output_dir / "commit-01.json").read_text(encoding="utf-8"))
        self.assertEqual(commit_packet["body_guidance"], {"body_recommended": True, "reason": "More than one file changed."})
        self.assertEqual(commit_packet["scope_candidates"][0], "parser")
        self.assertEqual(commit_packet["rules_reliability"], "explicit")

        packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
        rules_packet = json.loads((output_dir / "rules_packet.json").read_text(encoding="utf-8"))
        commit_packet_payloads = {
            name: json.loads((output_dir / name).read_text(encoding="utf-8"))
            for name in orchestrator["task_packet_names"]
            if name.startswith("commit-")
        }
        expected_metrics = compute_packet_metrics(
            {
                "global_packet.json": global_packet,
                "rules_packet.json": rules_packet,
                **commit_packet_payloads,
            },
            local_only_sources={"rules": rules, "plan": plan},
            shared_packets=COMMON_PATH_CONTRACT["shared_packets"],
        )
        self.assertEqual(packet_metrics, expected_metrics)
        self.assertEqual(result["packet_metrics"], packet_metrics)
        self.assertTrue(result["common_path_sufficient"])
        self.assertEqual(result["raw_reread_reasons"], [])
        self.assertEqual(
            packet_metrics["estimated_local_only_tokens"],
            estimate_tokens_from_bytes(json_bytes(rules) + json_bytes(plan)),
        )
        largest_commit_bytes = max(json_bytes(payload) for payload in commit_packet_payloads.values())
        self.assertEqual(
            packet_metrics["estimated_packet_tokens"],
            estimate_tokens_from_bytes(json_bytes(rules_packet) + largest_commit_bytes),
        )

    def test_local_mode_surfaces_root_rewrite_blocker(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        head_commit = commit_file(repo, "src/app.py", "print('hi')\n", "fix(app): seed")
        branch = build_reword_packets.branch_state(repo)["branch"] or "main"
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix"],
                "scope_required": True,
                "subject_length_limit": 72,
                "body_rules": [],
                "references_rules": [],
                "scope_suggestions": ["app"],
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
        }
        plan = {
            "repo_root": str(repo),
            "branch": branch,
            "detached_head": False,
            "count": 1,
            "head_commit": head_commit,
            "base_commit": None,
            "active_operation": None,
            "commits": [
                {
                    "index": 1,
                    "hash": head_commit,
                    "short_hash": head_commit[:12],
                    "parent_hashes": [],
                    "subject": "fix(app): seed",
                    "body": "",
                    "full_message": "fix(app): seed",
                    "author_name": "Codex",
                    "author_email": "codex@example.com",
                    "author_date": "2026-03-27T00:00:00Z",
                    "files": ["src/app.py"],
                    "shortstat": "1 file changed, 1 insertion(+)",
                    "new_message": "",
                }
            ],
        }

        exit_code, _output_dir, orchestrator, result = self.run_script(rules, plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(orchestrator["review_mode"], "local-only")
        self.assertEqual(orchestrator["recommended_worker_count"], 0)
        self.assertTrue(orchestrator["rewrite_blockers"]["root_rewrite_unsupported"])
        self.assertTrue(result["common_path_sufficient"])

    def test_missing_subject_and_files_emit_allowed_reread_reason(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        head_commit = commit_file(repo, "README.md", "seed\n", "chore(repo): seed")
        branch = build_reword_packets.branch_state(repo)["branch"] or "main"
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix"],
                "scope_required": True,
                "subject_length_limit": 72,
                "body_rules": [],
                "references_rules": [],
                "scope_suggestions": ["core"],
            },
            "rule_derivation": {
                "format_source": "commit_message_instructions",
                "allowed_types_source": "commit_message_instructions",
                "scope_required_source": "commit_message_instructions",
                "subject_length_limit_source": "commit_message_instructions",
                "repo_defaults_source": "commit_message_instructions",
            },
            "recent_scope_vocabulary": ["core"],
            "recent_subject_samples": [],
        }
        plan = {
            "repo_root": str(repo),
            "branch": branch,
            "detached_head": False,
            "count": 1,
            "head_commit": head_commit,
            "base_commit": head_commit,
            "active_operation": None,
            "commits": [
                {
                    "index": 1,
                    "hash": head_commit,
                    "short_hash": head_commit[:12],
                    "parent_hashes": ["0" * 40],
                    "subject": "",
                    "body": "",
                    "full_message": "",
                    "author_name": "Codex",
                    "author_email": "codex@example.com",
                    "author_date": "2026-03-27T00:00:00Z",
                    "files": [],
                    "shortstat": "",
                    "new_message": "",
                }
            ],
        }

        exit_code, _output_dir, orchestrator, result = self.run_script(rules, plan)

        self.assertEqual(exit_code, 0)
        self.assertFalse(orchestrator["common_path_sufficient"])
        self.assertFalse(result["common_path_sufficient"])
        self.assertGreaterEqual(result["raw_reread_count"], 1)
        self.assertTrue(result["raw_reread_reasons"])
        for reason in result["raw_reread_reasons"]:
            self.assertIn(reason, RAW_REREAD_ALLOWED_REASONS)

    def test_larger_commit_packet_drives_packet_path_estimate(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        head_commit = commit_file(repo, "README.md", "seed\n", "chore(repo): seed")
        branch = build_reword_packets.branch_state(repo)["branch"] or "main"
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix", "docs"],
                "scope_required": True,
                "subject_length_limit": 72,
                "body_rules": [],
                "references_rules": [],
                "scope_suggestions": ["core"],
            },
            "rule_derivation": {
                "format_source": "commit_message_instructions",
                "allowed_types_source": "commit_message_instructions",
                "scope_required_source": "commit_message_instructions",
                "subject_length_limit_source": "commit_message_instructions",
                "repo_defaults_source": "commit_message_instructions",
            },
            "recent_scope_vocabulary": ["core"],
            "recent_subject_samples": ["fix(core): seed"],
        }
        plan = {
            "repo_root": str(repo),
            "branch": branch,
            "detached_head": False,
            "count": 2,
            "head_commit": head_commit,
            "base_commit": head_commit,
            "active_operation": None,
            "commits": [
                {
                    "index": 1,
                    "hash": "1" * 40,
                    "short_hash": "1" * 12,
                    "parent_hashes": ["0" * 40],
                    "subject": "fix(core): small",
                    "body": "",
                    "full_message": "fix(core): small",
                    "author_name": "Codex",
                    "author_email": "codex@example.com",
                    "author_date": "2026-03-27T00:00:00Z",
                    "files": ["src/small.py"],
                    "shortstat": "1 file changed, 1 insertion(+)",
                    "new_message": "",
                },
                {
                    "index": 2,
                    "hash": "2" * 40,
                    "short_hash": "2" * 12,
                    "parent_hashes": ["1" * 40],
                    "subject": "docs(core): much larger payload",
                    "body": "body\n" * 20,
                    "full_message": "docs(core): much larger payload\n\n" + ("body\n" * 20),
                    "author_name": "Codex",
                    "author_email": "codex@example.com",
                    "author_date": "2026-03-27T00:00:00Z",
                    "files": ["docs/guide.md", "docs/appendix.md", "docs/changelog.md"],
                    "shortstat": "3 files changed, 30 insertions(+)",
                    "new_message": "",
                },
            ],
        }

        exit_code, output_dir, _orchestrator, _result = self.run_script(rules, plan)

        self.assertEqual(exit_code, 0)
        packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
        rules_packet = json.loads((output_dir / "rules_packet.json").read_text(encoding="utf-8"))
        commit_01 = json.loads((output_dir / "commit-01.json").read_text(encoding="utf-8"))
        commit_02 = json.loads((output_dir / "commit-02.json").read_text(encoding="utf-8"))
        self.assertGreater(json_bytes(commit_02), json_bytes(commit_01))
        self.assertEqual(
            packet_metrics["estimated_packet_tokens"],
            estimate_tokens_from_bytes(json_bytes(rules_packet) + json_bytes(commit_02)),
        )


if __name__ == "__main__":
    unittest.main()
