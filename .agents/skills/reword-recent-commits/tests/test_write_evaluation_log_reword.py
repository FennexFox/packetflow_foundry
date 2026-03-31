from __future__ import annotations

import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # type: ignore  # noqa: E402


class WriteEvaluationLogRewordTests(unittest.TestCase):
    def test_reword_skill_specific_data_and_phase_merges(self) -> None:
        context = {
            "repo_root": "C:/repo",
            "repo_slug": "example/repo",
            "branch": "feature/reword",
            "count": 2,
            "head_commit": "a" * 40,
            "base_commit": "b" * 40,
            "rules_reliability": "explicit",
            "context_fingerprint": "f" * 64,
            "commits": [{}, {}],
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "commit_packet_count": 2,
            "decision_ready_packets": False,
            "worker_return_contract": "generic",
            "worker_output_shape": "flat",
            "packet_files": ["global_packet.json", "rules_packet.json", "commit-01.json", "commit-02.json", "orchestrator.json"],
            "recommended_worker_count": 2,
            "rules_reliability": "explicit",
        }

        log = eval_log.build_base_log(Path(__file__), context, orchestrator, None)
        data = log["skill_specific"]["data"]
        self.assertEqual(data["branch"], "feature/reword")
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["rules_reliability"], "explicit")
        self.assertIsNone(data["packet_count"])

        build_result = {
            "review_mode": "targeted-delegation",
            "recommended_worker_count": 2,
            "recommended_workers": [{"agent_type": "docs_verifier"}, {"agent_type": "evidence_summarizer"}],
            "commit_packet_count": 2,
            "active_packet_count": 3,
            "applied_override_signals": ["aggregate_churn_threshold"],
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "raw_reread_reasons": [],
            "packet_metrics": {
                "packet_count": 4,
                "packet_size_bytes": 1400,
                "largest_packet_bytes": 600,
                "largest_two_packets_bytes": 950,
                "estimated_local_only_tokens": 500,
                "estimated_packet_tokens": 240,
                "estimated_delegation_savings": 260,
            },
        }
        eval_log.apply_phase_update(log, "build", build_result, 0.1)
        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["worker_count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["aggregate_churn_threshold"])
        self.assertFalse(log["orchestration"]["raw_reread_required"])
        self.assertEqual(log["input_size"]["active_areas"], 3)
        self.assertEqual(log["input_size"]["candidate_batches"], 2)
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 4)
        self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 240)
        self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 260)
        self.assertTrue(log["skill_specific"]["data"]["common_path_sufficient"])
        self.assertEqual(log["skill_specific"]["data"]["raw_reread_count"], 0)
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 500)
        self.assertEqual(log["baseline"]["estimated_token_savings"], 260)
        self.assertEqual(log["baseline"]["estimated_delegation_savings"], 260)
        self.assertEqual(log["measurement"]["efficiency_source"], "estimated")

        validate_result = {
            "valid": True,
            "context_fingerprint": "f" * 64,
            "rules_reliability": "explicit",
            "counters": {"commits_validated": 2},
            "stop_reasons": [],
        }
        eval_log.apply_phase_update(log, "validate", validate_result, 0.2)
        self.assertTrue(log["safety"]["validation_run"])
        self.assertTrue(log["safety"]["validation_passed"])
        self.assertEqual(log["skill_specific"]["data"]["validation_commands"], ["validate_reword_plan.py"])

        apply_result = {
            "dry_run": False,
            "apply_succeeded": True,
            "fingerprint_match": True,
            "new_head": "c" * 40,
            "applied_commit_hashes": ["1" * 40, "2" * 40],
            "force_push_needed": True,
            "cleanup_succeeded": True,
            "rules_reliability": "explicit",
            "counters": {"commits_rewritten": 2},
            "mutations": [{"kind": "rewrite_history"}],
            "mutation_type": "rewrite_history",
        }
        eval_log.apply_phase_update(log, "apply", apply_result, 0.3)
        self.assertTrue(log["safety"]["apply_attempted"])
        self.assertTrue(log["safety"]["apply_succeeded"])
        self.assertEqual(log["skill_specific"]["data"]["new_head"], "c" * 40)
        self.assertEqual(log["skill_specific"]["data"]["applied_commit_hashes"], ["1" * 40, "2" * 40])
        self.assertTrue(log["skill_specific"]["data"]["cleanup_succeeded"])


if __name__ == "__main__":
    unittest.main()
