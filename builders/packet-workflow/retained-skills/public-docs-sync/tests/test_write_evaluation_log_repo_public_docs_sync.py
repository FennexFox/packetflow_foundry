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


class RepoPublicDocsSyncEvaluationLogTests(unittest.TestCase):
    def test_skill_specific_data_reads_lint_and_runtime_contract_fields(self) -> None:
        lint_report = {
            "errors": ["hard drift"],
            "warnings": ["review required"],
            "infos": ["info"],
            "auto_apply_candidates": [{"kind": "settings_default_sync"}],
            "classifications": {
                "hard_drift": [{"message": "hard drift"}],
                "review_required": [{"message": "review required"}],
                "link_error": [{"message": "broken link"}],
                "stale_baseline": [{"message": "stale baseline"}],
            },
        }
        context = {
            "baseline": {"mode": "saved", "fallback_reason": None},
            "packet_candidates": {"claims_packet": {"active": True}},
            "deterministic_edit_count": 2,
            "manual_review_count": 1,
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "packet_order": ["global_packet.json", "claims_packet.json"],
            "selected_packets": ["claims_packet.json"],
        }

        payload = eval_log.skill_specific_data("public-docs-sync", context, orchestrator, lint_report)

        self.assertEqual(payload["hard_drift_count"], 1)
        self.assertEqual(payload["review_required_count"], 1)
        self.assertEqual(payload["link_error_count"], 1)
        self.assertEqual(payload["stale_baseline_count"], 1)
        self.assertEqual(payload["auto_apply_candidate_count"], 1)
        self.assertEqual(payload["selected_packets"], ["claims_packet.json"])
        self.assertNotIn("worker_count", payload)
        self.assertNotIn("worker_mix", payload)

    def test_build_base_log_leaves_eval_only_worker_metadata_unset_for_lean_runtime_packets(self) -> None:
        context = {
            "repo_root": str(Path("repo-root")),
            "current_branch": "batch_3",
            "packet_candidates": {},
            "baseline": {},
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "packet_order": ["global_packet.json", "claims_packet.json", "orchestrator.json"],
            "shared_packet": "global_packet.json",
        }

        payload = eval_log.build_base_log(SCRIPT_DIR / "write_evaluation_log.py", context, orchestrator, None)

        self.assertEqual(payload["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(payload["orchestration"]["planned_workers"]["roles"], [])
        self.assertEqual(payload["orchestration"]["override_signals"], [])
        self.assertNotIn("worker_count", payload["skill_specific"]["data"])
        self.assertNotIn("worker_mix", payload["skill_specific"]["data"])

    def test_build_phase_merges_packet_sizing_efficiency_and_active_packet_counts(self) -> None:
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
                        "name": "claims-docs-verifier",
                        "agent_type": "docs_verifier",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["claims_packet.json"],
                        "responsibility": "Verify claims packet",
                    },
                    {
                        "name": "workflow-repo-mapper",
                        "agent_type": "repo_mapper",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["workflow_packet.json"],
                        "responsibility": "Map workflow packet",
                    },
                ],
            },
            "selected_packets": ["claims_packet.json", "workflow_packet.json"],
            "active_packets": ["claims_packet", "workflow_packet"],
            "active_packet_count": 2,
            "applied_override_signals": ["high_churn"],
            "auto_apply_candidate_count": 3,
            "packet_sizing": {
                "packet_count": 4,
                "packet_size_bytes": 1024,
                "largest_packet_bytes": 400,
                "largest_two_packets_bytes": 700,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 500,
                    "packet_tokens": 250,
                    "savings_tokens": 250,
                    "main_model_input_cost_nanousd": 625000,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                }
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.25)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["high_churn"])
        self.assertEqual(log["input_size"]["active_areas"], 2)
        self.assertEqual(log["skill_specific"]["data"]["auto_apply_candidate_count"], 3)
        self.assertNotIn("packet_count", log["skill_specific"]["data"])
        self.assertEqual(log["packet_sizing"]["packet_count"], 4)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 250)


if __name__ == "__main__":
    unittest.main()
