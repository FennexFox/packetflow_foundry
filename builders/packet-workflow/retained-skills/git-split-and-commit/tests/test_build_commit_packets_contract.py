from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_commit_packets  # type: ignore  # noqa: E402


class BuildCommitPacketsContractTest(unittest.TestCase):
    def run_script(self, rules: dict, worktree: dict) -> tuple[int, Path, dict, dict]:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        rules_path = tmp_path / "rules.json"
        worktree_path = tmp_path / "worktree.json"
        output_dir = tmp_path / "packets"
        result_path = tmp_path / "build-result.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        worktree_path.write_text(json.dumps(worktree), encoding="utf-8")

        stdout = io.StringIO()
        argv = [
            "build_commit_packets.py",
            "--rules",
            str(rules_path),
            "--worktree",
            str(worktree_path),
            "--output-dir",
            str(output_dir),
            "--result-output",
            str(result_path),
        ]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            exit_code = build_commit_packets.main()

        orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return exit_code, output_dir, orchestrator, result

    def test_split_file_packet_escalates_review_mode_and_routes_workers(self) -> None:
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix", "chore", "docs"],
                "scope_required": True,
                "subject_length_limit": 72,
                "scope_suggestions": ["infra"],
            },
            "recent_scope_vocabulary": ["infra"],
            "instruction_snippets": {},
        }
        worktree = {
            "repo_root": "C:/tmp/repo",
            "head_commit": "abc123",
            "branch": "main",
            "worktree_fingerprint": "sha256:deadbeef",
            "active_operation": None,
            "input_scope": "all-local-changes",
            "diff_shortstat": "1 file changed, 12 insertions(+), 12 deletions(-)",
            "changed_file_groups": {},
            "diff_stat": [],
            "validation_candidates": [
                {
                    "label": "unit-tests",
                    "paths": ["src/app.py"],
                    "command": "python -m unittest",
                }
            ],
            "files": [
                {
                    "path": "src/app.py",
                    "area": "runtime",
                    "generated": False,
                    "split_eligible": True,
                    "change_kind": "modified",
                    "path_tokens": ["app", "runtime"],
                    "hunks": [
                        {
                            "hunk_id": "H1",
                            "header": "@@ -1,2 +1,2 @@",
                            "old_start": 1,
                            "new_start": 1,
                            "tokens": ["alpha", "beta"],
                            "raw_body_lines": ["-old_alpha()", "+new_alpha()"],
                            "raw_patch": "@@ -1,2 +1,2 @@\n-old_alpha()\n+new_alpha()\n",
                            "removed_digest": "same-digest",
                            "added_digest": "same-digest",
                        },
                        {
                            "hunk_id": "H2",
                            "header": "@@ -40,2 +40,2 @@",
                            "old_start": 40,
                            "new_start": 40,
                            "tokens": ["gamma", "delta"],
                            "raw_body_lines": ["-old_gamma()", "+new_gamma()"],
                            "raw_patch": "@@ -40,2 +40,2 @@\n-old_gamma()\n+new_gamma()\n",
                            "removed_digest": "same-digest",
                            "added_digest": "same-digest",
                        },
                    ],
                }
            ],
        }

        exit_code, output_dir, orchestrator, result = self.run_script(rules, worktree)

        self.assertEqual(exit_code, 0)
        self.assertEqual(orchestrator["review_mode"], "targeted-delegation")
        self.assertEqual(orchestrator["orchestrator_profile"], "standard")
        self.assertTrue(orchestrator["decision_ready_packets"])
        self.assertEqual(orchestrator["worker_return_contract"], "classification-oriented")
        self.assertEqual(orchestrator["worker_output_shape"], "hierarchical")
        self.assertEqual(
            orchestrator["task_packet_names"],
            ["rules_packet", "worktree_packet", "candidate-batch-01", "split-file-01"],
        )
        self.assertEqual(
            orchestrator["packet_worker_map"],
            {
                "rules_packet": ["docs_verifier"],
                "worktree_packet": ["repo_mapper"],
                "candidate-batch-01": ["evidence_summarizer"],
                "split-file-01": ["large_diff_auditor"],
            },
        )
        self.assertEqual(
            orchestrator["packet_order"],
            ["global_packet.json", "rules_packet.json", "worktree_packet.json", "candidate-batch-01.json", "split-file-01.json"],
        )
        self.assertEqual(orchestrator["candidate_batch_map"], {"candidate-batch-01": ["src/app.py"]})
        self.assertEqual(orchestrator["split_candidate_paths"], ["src/app.py"])
        self.assertEqual(
            orchestrator["common_path_contract"]["shared_packets"],
            ["rules_packet.json", "worktree_packet.json"],
        )
        self.assertNotIn("packet_metrics", orchestrator)

        global_packet = json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8"))
        self.assertTrue(global_packet["decision_ready_packets"])
        self.assertEqual(global_packet["packet_worker_map"], orchestrator["packet_worker_map"])
        self.assertEqual(global_packet["task_packet_names"], orchestrator["task_packet_names"])
        self.assertEqual(global_packet["worker_footer_fields"], ["packet_ids", "candidate_ids", "primary_outcome", "overall_confidence", "coverage_gaps", "overall_risk"])
        self.assertEqual([bundle["name"] for bundle in global_packet["candidate_field_bundles"]], ["candidate"])
        self.assertEqual(
            global_packet["candidate_field_bundles"][0]["fields"],
            [
                "fact_summary",
                "proposal_classification",
                "classification_rationale",
                "supporting_references",
                "ambiguity",
                "confidence",
                "reread_control",
            ],
        )
        self.assertEqual(global_packet["domain_overlay"]["proposal_enum_values"], ["commit_bucket", "split_file", "reference_only", "ignore"])
        self.assertEqual(
            global_packet["domain_overlay"]["candidate_field_aliases"],
            {
                "fact_summary": "intent_summary",
                "proposal_classification": "recommended_type",
                "supporting_references": "supporting_paths",
                "ambiguity": "open_ambiguity",
                "reread_control": "raw_reread_reason",
            },
        )
        self.assertEqual(
            global_packet["domain_overlay"]["alias_notes"],
            {
                "supporting_paths": (
                    "Current domain aliases assume file/path-oriented evidence first; "
                    "`supporting_paths` is evidence-only and does not claim path ownership."
                )
            },
        )
        self.assertEqual(global_packet["common_path_contract"]["goal"], "Draft commit-plan.json without raw diff rereads on the common path.")

        split_packet = json.loads((output_dir / "split-file-01.json").read_text(encoding="utf-8"))
        self.assertEqual(split_packet["file"]["path"], "src/app.py")
        self.assertTrue(split_packet["file"]["reason"]["duplicate_digest_pairs"])
        self.assertEqual(len(split_packet["file"]["hunks"]), 2)
        self.assertEqual(split_packet["file"]["hunks"][0]["hunk_id"], "H1")
        self.assertEqual(split_packet["file"]["hunks"][1]["hunk_id"], "H2")
        self.assertIn("split_decision_basis", split_packet)
        self.assertIn("rematch_risk", split_packet)
        self.assertIn("whole_file_fallback_guidance", split_packet)

        batch_packet = json.loads((output_dir / "candidate-batch-01.json").read_text(encoding="utf-8"))
        self.assertEqual(batch_packet["recommended_type"], "fix")
        self.assertTrue(batch_packet["body_needed"])
        self.assertEqual(batch_packet["validation_candidates"], [{"label": "unit-tests", "paths": ["src/app.py"], "command": "python -m unittest"}])
        self.assertIn("cohesion_basis", batch_packet)
        self.assertIn("boundary_risks", batch_packet)
        self.assertIn("whole_file_recommendation", batch_packet)
        self.assertIn("coverage_gaps", batch_packet)
        self.assertIn("quality_escape_hints", batch_packet)
        self.assertIn("change_synopsis", batch_packet["files"][0])
        self.assertIn("validation_candidates", batch_packet["files"][0])

        worktree_packet = json.loads((output_dir / "worktree_packet.json").read_text(encoding="utf-8"))
        self.assertEqual(worktree_packet["candidate_batch_order"], ["candidate-batch-01.json"])
        self.assertEqual(worktree_packet["raw_reread_reasons"], [])
        self.assertTrue(worktree_packet["common_path_sufficient"])

        packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
        self.assertGreater(packet_metrics["packet_count"], 0)
        self.assertGreater(packet_metrics["estimated_local_only_tokens"], 0)
        self.assertGreater(packet_metrics["estimated_packet_tokens"], 0)

        self.assertTrue(result["common_path_sufficient"])
        self.assertEqual(result["raw_reread_count"], 0)
        self.assertEqual(result["active_packets"], ["rules_packet.json", "worktree_packet.json", "candidate-batch-01.json", "split-file-01.json"])
        self.assertIn("packet_metrics", result)

    def test_edge_case_build_result_uses_explicit_reread_reason(self) -> None:
        rules = {
            "rules": {
                "format": "<type>(<scope>): <subject>",
                "allowed_types": ["fix"],
                "scope_required": True,
                "subject_length_limit": 72,
                "scope_suggestions": ["core"],
            },
            "recent_scope_vocabulary": ["core"],
            "instruction_snippets": {},
        }
        worktree = {
            "repo_root": "C:/tmp/repo",
            "head_commit": "abc123",
            "branch": "main",
            "worktree_fingerprint": "sha256:deadbeef",
            "active_operation": None,
            "input_scope": "all-local-changes",
            "diff_shortstat": "1 file changed, 4 insertions(+), 4 deletions(-)",
            "changed_file_groups": {},
            "diff_stat": [],
            "validation_candidates": [],
            "files": [
                {
                    "path": "src/app.py",
                    "area": "runtime",
                    "generated": False,
                    "binary": False,
                    "split_eligible": True,
                    "change_kind": "modified",
                    "path_tokens": ["app"],
                    "hunks": [
                        {
                            "hunk_id": "H1",
                            "header": "@@ -1,2 +1,2 @@",
                            "old_start": 1,
                            "new_start": 1,
                            "tokens": [],
                            "raw_body_lines": ["-   ", "+   "],
                            "removed_digest": "same-digest",
                            "added_digest": "same-digest",
                        },
                        {
                            "hunk_id": "H2",
                            "header": "@@ -40,2 +40,2 @@",
                            "old_start": 40,
                            "new_start": 40,
                            "tokens": [],
                            "raw_body_lines": ["-   ", "+   "],
                            "removed_digest": "same-digest",
                            "added_digest": "same-digest",
                        },
                    ],
                }
            ],
        }

        exit_code, output_dir, _orchestrator, result = self.run_script(rules, worktree)

        self.assertEqual(exit_code, 0)
        self.assertFalse(result["common_path_sufficient"])
        self.assertEqual(result["raw_reread_reasons"], ["insufficient_excerpt_quality"])
        worktree_packet = json.loads((output_dir / "worktree_packet.json").read_text(encoding="utf-8"))
        self.assertEqual(worktree_packet["raw_reread_reasons"], ["insufficient_excerpt_quality"])
        self.assertEqual(worktree_packet["quality_escape_hints"][0]["reason"], "insufficient_excerpt_quality")


if __name__ == "__main__":
    unittest.main()
