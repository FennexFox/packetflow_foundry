from __future__ import annotations

import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # type: ignore  # noqa: E402
import reword_plan_contract as contract  # type: ignore  # noqa: E402


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
            "planned_workers": {"count": 2, "roles": ["docs_verifier", "evidence_summarizer"], "workers": []},
            "rules_reliability": "explicit",
        }

        log = eval_log.build_base_log(Path(__file__), context, orchestrator, None)
        data = log["skill_specific"]["data"]
        self.assertEqual(data["branch"], "feature/reword")
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["rules_reliability"], "explicit")
        self.assertNotIn("packet_count", data)

        build_result = {
            "review_mode": "targeted-delegation",
            "planned_workers": {
                "count": 2,
                "roles": ["docs_verifier", "evidence_summarizer"],
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
                        "name": "commit-intent",
                        "agent_type": "evidence_summarizer",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["commit-01.json", "commit-02.json", "global_packet.json"],
                        "responsibility": "Commit rewrite summary",
                    },
                ],
            },
            "commit_packet_count": 2,
            "active_packet_count": 3,
            "applied_override_signals": ["aggregate_churn_threshold"],
            "delegation_non_use_cases": contract.DELEGATION_NON_USE_CASES,
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "raw_reread_reasons": [],
            "packet_sizing": {
                "packet_count": 4,
                "packet_size_bytes": 1400,
                "largest_packet_bytes": 600,
                "largest_two_packets_bytes": 950,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 500,
                    "packet_tokens": 240,
                    "savings_tokens": 260,
                    "main_model_input_cost_nanousd": 325000,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                },
            },
        }
        eval_log.apply_phase_update(log, "build", build_result, 0.1)
        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["aggregate_churn_threshold"])
        self.assertFalse(log["orchestration"]["raw_reread_required"])
        self.assertEqual(log["input_size"]["active_areas"], 3)
        self.assertEqual(log["input_size"]["candidate_batches"], 2)
        self.assertEqual(log["skill_specific"]["data"]["delegation_non_use_cases"], contract.DELEGATION_NON_USE_CASES)
        self.assertTrue(log["skill_specific"]["data"]["common_path_sufficient"])
        self.assertEqual(log["skill_specific"]["data"]["raw_reread_count"], 0)
        self.assertEqual(log["packet_sizing"]["packet_count"], 4)
        self.assertEqual(log["efficiency"]["packet_compaction"]["packet_tokens"], 240)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 260)

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
