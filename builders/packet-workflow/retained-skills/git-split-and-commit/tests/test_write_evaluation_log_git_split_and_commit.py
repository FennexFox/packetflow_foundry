from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
while str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402
import commit_packet_contract as contract  # noqa: E402


class GitSplitAndCommitEvaluationLogTests(unittest.TestCase):
    def test_skill_specific_data_includes_common_path_fields(self) -> None:
        orchestrator = {
            "candidate_batch_count": 2,
            "split_file_count": 1,
            "decision_ready_packets": True,
            "worker_return_contract": "classification-oriented",
            "worker_output_shape": "hierarchical",
            "packet_order": [
                "global_packet.json",
                "rules_packet.json",
                "worktree_packet.json",
                "candidate-batch-01.json",
                "split-file-01.json",
            ],
            "common_path_sufficient": True,
            "raw_reread_reasons": [],
        }

        payload = eval_log.skill_specific_data("git-split-and-commit", {}, orchestrator, None)

        self.assertEqual(payload["commit_buckets_planned"], 2)
        self.assertEqual(payload["split_file_count"], 1)
        self.assertTrue(payload["decision_ready_packets"])
        self.assertEqual(payload["raw_reread_count"], 0)
        self.assertTrue(payload["common_path_sufficient"])
        self.assertNotIn("packet_count", payload)

    def test_build_phase_merges_packet_sizing_efficiency_and_reread_signals(self) -> None:
        log = {
            "measurement": {},
            "baseline": {},
            "orchestration": {},
            "input_size": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "planned_workers": {
                "count": 2,
                "roles": ["docs_verifier", "repo_mapper"],
                "workers": [
                    {
                        "name": "rules",
                        "agent_type": "docs_verifier",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["global_packet.json", "rules_packet.json"],
                        "responsibility": "Rules summary",
                    },
                    {
                        "name": "worktree",
                        "agent_type": "repo_mapper",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["global_packet.json", "worktree_packet.json"],
                        "responsibility": "Worktree summary",
                    },
                ],
            },
            "active_packets": [
                "rules_packet.json",
                "worktree_packet.json",
                "candidate-batch-01.json",
            ],
            "active_packet_count": 3,
            "candidate_batch_count": 1,
            "split_file_count": 0,
            "applied_override_signals": ["diff_stat_threshold"],
            "delegation_non_use_cases": contract.DELEGATION_NON_USE_CASES,
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "raw_reread_reasons": [],
            "packet_sizing": {
                "packet_count": 5,
                "packet_size_bytes": 1024,
                "largest_packet_bytes": 420,
                "largest_two_packets_bytes": 700,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 500,
                    "packet_tokens": 250,
                    "savings_tokens": 250,
                    "main_model_input_cost_nanousd": 312500,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                },
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["diff_stat_threshold"])
        self.assertEqual(log["input_size"]["active_areas"], 3)
        self.assertEqual(log["input_size"]["candidate_batches"], 1)
        self.assertEqual(log["skill_specific"]["data"]["delegation_non_use_cases"], contract.DELEGATION_NON_USE_CASES)
        self.assertEqual(log["packet_sizing"]["packet_count"], 5)
        self.assertEqual(log["efficiency"]["packet_compaction"]["packet_tokens"], 250)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 250)

    def test_candidate_batch_packet_names_are_counted_as_batches(self) -> None:
        orchestrator = {
            "packet_order": [
                "global_packet.json",
                "rules_packet.json",
                "worktree_packet.json",
                "candidate-batch-01.json",
                "split-file-01.json",
            ]
        }

        self.assertEqual(eval_log.batch_packet_count(orchestrator), 1)
        self.assertEqual(eval_log.item_packet_count(orchestrator), 2)


if __name__ == "__main__":
    unittest.main()
