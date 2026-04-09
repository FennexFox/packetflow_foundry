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
    def test_default_output_path_uses_repo_root(self) -> None:
        repo_root = Path("repo-root")

        resolved = eval_log.default_output_path(
            repo_root,
            "weekly-update",
            "2026-04-04T10:00:00Z__weekly-update__abc:def",
        )

        self.assertEqual(
            resolved,
            repo_root
            / ".codex"
            / "tmp"
            / "evaluation_logs"
            / "weekly-update"
            / "2026-04-04T10-00-00Z__weekly-update__abc-def.json",
        )

    def test_find_branch_and_head_sha_ignore_non_dict_analysis_ref(self) -> None:
        context = {
            "analysis_ref": "main",
            "current_branch": "develop",
            "head_sha": "abc1234",
            "pr": {
                "headRefName": "feature/fallback",
                "headRefOid": "deadbeef",
            },
        }

        self.assertEqual(eval_log.find_branch(context), "develop")
        self.assertEqual(eval_log.find_head_sha(context), "abc1234")

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
        }

        payload = eval_log.skill_specific_data("weekly-update", context, orchestrator, None)

        self.assertEqual(payload["review_mode"], "targeted-delegation")
        self.assertEqual(payload["selected_packets"], ["mapping_packet", "changes_packet", "risks_packet"])
        self.assertNotIn("worker_count", payload)
        self.assertNotIn("worker_mix", payload)
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["actual_incident"], 1)
        self.assertEqual(payload["candidate_counts_by_proposed_classification"]["blocker_or_risk"], 1)
        self.assertEqual(payload["raw_reread_reason_counts"], {"conflicting_signals": 1})
        self.assertEqual(payload["coverage_gap_count"], 1)
        self.assertFalse(payload["common_path_sufficient"])
        self.assertEqual(payload["raw_reread_count"], 1)

    def test_build_base_log_leaves_eval_only_worker_metadata_unset_for_lean_runtime_packets(self) -> None:
        context = {
            "repo_root": str(Path("repo-root")),
            "current_branch": "batch_3",
            "reporting_window": {"start_utc": "2026-03-20T00:00:00Z", "end_utc": "2026-03-27T00:00:00Z"},
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "packet_files": ["global_packet.json", "mapping_packet.json", "orchestrator.json"],
            "shared_packet": "global_packet.json",
        }

        payload = eval_log.build_base_log(SCRIPT_DIR / "write_evaluation_log.py", context, orchestrator, None)

        self.assertEqual(payload["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(payload["orchestration"]["planned_workers"]["roles"], [])
        self.assertEqual(payload["orchestration"]["actual_workers"]["summary"]["executed_count"], 0)
        self.assertEqual(payload["orchestration"]["override_signals"], [])
        self.assertNotIn("worker_count", payload["skill_specific"]["data"])
        self.assertNotIn("worker_mix", payload["skill_specific"]["data"])

    def test_build_phase_merges_packet_sizing_efficiency_and_common_path_signals(self) -> None:
        log = {
            "skill": {"name": "weekly-update"},
            "measurement": {},
            "baseline": {},
            "orchestration": {},
            "skill_specific": {"data": {}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "planned_workers": {
                "count": 2,
                "roles": ["repo_mapper", "large_diff_auditor"],
                "workers": [
                    {
                        "name": "mapping-repo-mapper",
                        "agent_type": "repo_mapper",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["mapping_packet.json"],
                        "responsibility": "Map repo surfaces",
                    },
                    {
                        "name": "risks-large-diff-auditor",
                        "agent_type": "large_diff_auditor",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["risks_packet.json"],
                        "responsibility": "Audit risks",
                    },
                ],
            },
            "selected_packets": ["mapping_packet", "changes_packet", "risks_packet"],
            "candidate_counts_by_proposed_classification": {"actual_incident": 1, "blocker_or_risk": 2},
            "raw_reread_reason_counts": {"conflicting_signals": 1},
            "coverage_gap_count": 2,
            "common_path_sufficient": False,
            "raw_reread_count": 1,
            "packet_sizing": {
                "packet_count": 6,
                "total_packet_bytes": 4096,
                "largest_packet_bytes": 1024,
                "largest_two_packets_bytes": 1800,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 1200,
                    "packet_tokens": 400,
                    "savings_tokens": 800,
                    "main_model_input_cost_nanousd": 1000,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                }
            },
        }

        eval_log.apply_phase_update(log, "build", result, 1.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
        self.assertEqual(log["skill_specific"]["data"]["selected_packets"], ["mapping_packet", "changes_packet", "risks_packet"])
        self.assertNotIn("packet_count", log["skill_specific"]["data"])
        self.assertNotIn("estimated_packet_tokens", log["skill_specific"]["data"])
        self.assertNotIn("estimated_delegation_savings", log["skill_specific"]["data"])
        self.assertFalse(log["skill_specific"]["data"]["common_path_sufficient"])
        self.assertTrue(log["orchestration"]["raw_reread_required"])
        self.assertEqual(log["packet_sizing"]["packet_count"], 6)
        self.assertEqual(log["packet_sizing"]["total_packet_bytes"], 4096)
        self.assertEqual(log["efficiency"]["packet_compaction"]["local_only_tokens"], 1200)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 800)
        self.assertEqual(log["latency"]["packet_builder_seconds"], 1.5)

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
