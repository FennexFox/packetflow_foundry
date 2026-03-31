from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
script_dir = str(SCRIPT_DIR)
while script_dir in sys.path:
    sys.path.remove(script_dir)
sys.path.insert(0, script_dir)

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402


class WeeklyUpdateEvaluationLogTests(unittest.TestCase):
    def test_skill_specific_data_reads_weekly_update_contract_fields(self) -> None:
        context = {
            "reporting_window": {"start_utc": "2026-03-20T00:00:00Z", "end_utc": "2026-03-27T00:00:00Z"},
            "source_gaps": ["release notes may be truncated"],
            "candidate_inventory": [
                {"proposed_classification": "actual_incident", "raw_reread_reason": None},
                {"proposed_classification": "blocker_or_risk", "raw_reread_reason": "conflicting_signals"},
                {"proposed_classification": "artifact_only", "raw_reread_reason": None},
            ],
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "selected_packets": ["mapping_packet", "changes_packet", "risks_packet"],
            "recommended_worker_count": 2,
            "recommended_workers": [
                {"agent_type": "repo_mapper"},
                {"agent_type": "large_diff_auditor"},
            ],
        }

        payload = eval_log.skill_specific_data("weekly-update", context, orchestrator, None)

        self.assertEqual(payload["review_mode"], "targeted-delegation")
        self.assertEqual(payload["worker_count"], 2)
        self.assertEqual(payload["worker_mix"], ["repo_mapper", "large_diff_auditor"])
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["actual_incident"], 1)
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["blocker_or_risk"], 1)
        self.assertEqual(payload["raw_reread_reason_counts"], {"conflicting_signals": 1})
        self.assertEqual(payload["coverage_gap_count"], 1)
        self.assertFalse(payload["common_path_sufficient"])
        self.assertEqual(payload["raw_reread_count"], 1)

    def test_build_phase_merges_packet_metrics_and_common_path_signals(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {"efficiency_source": "unavailable"},
            "baseline": {},
            "orchestration": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "recommended_worker_count": 2,
            "recommended_workers": [{"agent_type": "repo_mapper"}, {"agent_type": "large_diff_auditor"}],
            "selected_packets": ["mapping_packet", "changes_packet", "risks_packet"],
            "candidate_counts_by_proposed_classification": {"actual_incident": 1, "blocker_or_risk": 2},
            "raw_reread_reason_counts": {"conflicting_signals": 1},
            "coverage_gap_count": 2,
            "common_path_sufficient": False,
            "raw_reread_count": 1,
            "packet_metrics": {
                "packet_count": 6,
                "packet_size_bytes": 4096,
                "largest_packet_bytes": 1024,
                "largest_two_packets_bytes": 1800,
                "estimated_local_only_tokens": 1200,
                "estimated_packet_tokens": 400,
                "estimated_delegation_savings": 800,
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["worker_count"], 2)
        self.assertEqual(log["skill_specific"]["data"]["selected_packets"], ["mapping_packet", "changes_packet", "risks_packet"])
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 6)
        self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 400)
        self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 800)
        self.assertFalse(log["skill_specific"]["data"]["common_path_sufficient"])
        self.assertTrue(log["orchestration"]["raw_reread_required"])
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 1200)
        self.assertEqual(log["baseline"]["estimated_token_savings"], 800)
        self.assertEqual(log["measurement"]["efficiency_source"], "estimated")

    def test_validate_and_apply_merge_plan_and_marker_fields(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "orchestration": {},
            "safety": {},
            "quality": {},
            "outputs": {},
            "skill_specific": {"data": {}},
        }

        eval_log.apply_phase_update(
            log,
            "validate",
            {
                "valid": True,
                "overall_confidence": "medium",
                "allow_marker_update": False,
                "stop_reasons": ["allow_marker_update=false"],
            },
            None,
        )
        eval_log.apply_phase_update(
            log,
            "apply",
            {
                "dry_run": True,
                "apply_succeeded": True,
                "overall_confidence": "medium",
                "allow_marker_update": False,
                "marker_update_attempted": False,
                "marker_update_written": False,
                "stop_reasons": ["allow_marker_update=false"],
            },
            None,
        )

        self.assertTrue(log["safety"]["validation_run"])
        self.assertEqual(log["skill_specific"]["data"]["plan_overall_confidence"], "medium")
        self.assertFalse(log["skill_specific"]["data"]["allow_marker_update"])
        self.assertFalse(log["skill_specific"]["data"]["marker_update_attempted"])
        self.assertFalse(log["skill_specific"]["data"]["marker_update_written"])
        self.assertEqual(log["quality"]["result_status"], "dry-run")


if __name__ == "__main__":
    unittest.main()
