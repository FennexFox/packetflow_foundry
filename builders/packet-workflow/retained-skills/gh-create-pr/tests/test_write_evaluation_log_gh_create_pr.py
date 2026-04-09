from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402
import pr_create_contract as contract  # noqa: E402


def context() -> dict:
    return {
        "repo_root": str(Path.cwd()),
        "repo_slug": "owner/repo",
        "changed_files": ["src/creator.py", "tests/test_creator.py"],
        "resolved_head": "feature/pr-create",
        "resolved_base": "main",
    }


def orchestrator() -> dict:
    return {
        "review_mode": "targeted-delegation",
        "packet_files": [
            "global_packet.json",
            "rules_packet.json",
            "runtime_packet.json",
            "synthesis_packet.json",
            "orchestrator.json",
        ],
        "shared_packet": "global_packet.json",
    }


class WriteEvaluationLogGhCreatePrTests(unittest.TestCase):
    def test_build_phase_reads_eval_only_fields_from_build_result(self) -> None:
        log = eval_log.build_base_log(Path(eval_log.__file__), context(), orchestrator(), None)
        result = {
            "review_mode": "targeted-delegation",
            "review_mode_baseline": "local-only",
            "review_mode_adjustments": ["delegation_savings_floor"],
            "override_signals": {"high_churn": False, "multi_group_core_files": True},
            "planned_workers": {
                "count": 2,
                "roles": ["packet_explorer", "evidence_summarizer"],
                "workers": [
                    {
                        "name": "runtime",
                        "agent_type": "packet_explorer",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["global_packet.json", "runtime_packet.json"],
                        "responsibility": "Runtime summary",
                    },
                    {
                        "name": "testing",
                        "agent_type": "evidence_summarizer",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "low",
                        "packets": ["global_packet.json", "testing_packet.json"],
                        "responsibility": "Testing summary",
                    },
                ],
            },
            "delegation_non_use_cases": contract.DELEGATION_NON_USE_CASES,
            "packet_sizing": {
                "packet_count": 6,
                "packet_size_bytes": 6870,
                "largest_packet_bytes": 2000,
                "largest_two_packets_bytes": 3942,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 1800,
                    "packet_tokens": 900,
                    "savings_tokens": 900,
                    "main_model_input_cost_nanousd": 1125000,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                },
            },
        }

        eval_log.apply_phase_update(log, "build", result, 0.2)

        self.assertEqual(log["orchestration"]["review_mode_baseline"], "local-only")
        self.assertEqual(log["orchestration"]["review_mode_adjustments"], ["delegation_savings_floor"])
        self.assertEqual(log["orchestration"]["override_signals"], ["multi_group_core_files"])
        self.assertEqual(log["orchestration"]["planned_workers"]["roles"], ["packet_explorer", "evidence_summarizer"])
        self.assertEqual(
            log["skill_specific"]["data"]["delegation_non_use_cases"],
            contract.DELEGATION_NON_USE_CASES,
        )
        self.assertEqual(log["packet_sizing"]["packet_count"], 6)
        self.assertEqual(log["efficiency"]["packet_compaction"]["local_only_tokens"], 1800)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 900)


if __name__ == "__main__":
    unittest.main()
