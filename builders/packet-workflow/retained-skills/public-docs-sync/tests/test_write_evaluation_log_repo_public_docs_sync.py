from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
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
            "recommended_worker_count": 1,
            "recommended_workers": [{"agent_type": "large_diff_auditor"}],
            "applied_override_signals": ["lint"],
        }

        payload = eval_log.skill_specific_data("public-docs-sync", context, orchestrator, lint_report)

        self.assertEqual(payload["hard_drift_count"], 1)
        self.assertEqual(payload["review_required_count"], 1)
        self.assertEqual(payload["link_error_count"], 1)
        self.assertEqual(payload["stale_baseline_count"], 1)
        self.assertEqual(payload["auto_apply_candidate_count"], 1)
        self.assertEqual(payload["worker_mix"], ["large_diff_auditor"])

    def test_build_phase_merges_packet_metrics_and_active_packet_counts(self) -> None:
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
            "selected_packets": ["claims_packet.json", "workflow_packet.json"],
            "active_packets": ["claims_packet", "workflow_packet"],
            "active_packet_count": 2,
            "applied_override_signals": ["high_churn"],
            "auto_apply_candidate_count": 3,
            "packet_metrics": {
                "packet_count": 4,
                "packet_size_bytes": 1024,
                "largest_packet_bytes": 400,
                "largest_two_packets_bytes": 700,
                "estimated_local_only_tokens": 500,
                "estimated_packet_tokens": 250,
                "estimated_delegation_savings": 250,
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.25)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["worker_count"], 2)
        self.assertEqual(log["orchestration"]["override_signals"], ["high_churn"])
        self.assertEqual(log["input_size"]["active_areas"], 2)
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 4)
        self.assertEqual(log["skill_specific"]["data"]["auto_apply_candidate_count"], 3)
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 500)
        self.assertEqual(log["baseline"]["estimated_delegation_savings"], 250)
        self.assertEqual(log["measurement"]["efficiency_source"], "estimated")


if __name__ == "__main__":
    unittest.main()
