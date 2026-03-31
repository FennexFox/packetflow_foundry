from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402


class GitSplitAndCommitEvaluationLogTests(unittest.TestCase):
    def test_skill_specific_data_includes_common_path_and_packet_metrics_fields(self) -> None:
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
        self.assertIsNone(payload["packet_count"])

    def test_build_phase_merges_packet_metrics_and_reread_signals(self) -> None:
        log = {
            "measurement": {},
            "baseline": {},
            "orchestration": {},
            "input_size": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "recommended_worker_count": 2,
            "recommended_workers": [{"agent_type": "docs_verifier"}, {"agent_type": "repo_mapper"}],
            "active_packets": [
                "rules_packet.json",
                "worktree_packet.json",
                "candidate-batch-01.json",
            ],
            "active_packet_count": 3,
            "candidate_batch_count": 1,
            "split_file_count": 0,
            "applied_override_signals": ["diff_stat_threshold"],
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "raw_reread_reasons": [],
            "packet_metrics": {
                "packet_count": 5,
                "packet_size_bytes": 1024,
                "largest_packet_bytes": 420,
                "largest_two_packets_bytes": 700,
                "estimated_local_only_tokens": 500,
                "estimated_packet_tokens": 250,
                "estimated_delegation_savings": 250,
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["worker_count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["diff_stat_threshold"])
        self.assertEqual(log["input_size"]["active_areas"], 3)
        self.assertEqual(log["input_size"]["candidate_batches"], 1)
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 5)
        self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 250)
        self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 250)
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 500)
        self.assertEqual(log["baseline"]["estimated_delegation_savings"], 250)
        self.assertEqual(log["measurement"]["efficiency_source"], "estimated")

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
