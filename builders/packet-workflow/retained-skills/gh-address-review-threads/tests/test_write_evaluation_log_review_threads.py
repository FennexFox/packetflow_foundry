from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)
    sys.path.insert(0, candidate)

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # type: ignore  # noqa: E402


class WriteEvaluationLogReviewThreadsTests(unittest.TestCase):
    def test_build_phase_merges_packet_sizing_efficiency_and_common_path_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            log = {
                "skill": {"name": "gh-address-review-threads"},
                "quality": {},
                "safety": {},
                "outputs": {},
                "orchestration": {},
                "baseline": {},
                "measurement": {},
                "skill_specific": {"data": {}},
            }
            result = {
                "review_mode": "targeted-delegation",
                "planned_workers": {
                    "count": 2,
                    "roles": ["packet_explorer"],
                    "workers": [
                        {
                            "name": "batch-01",
                            "agent_type": "packet_explorer",
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "packets": ["global_packet.json", "thread-batch-01.json"],
                            "responsibility": "Review clustered thread batch",
                        },
                        {
                            "name": "thread-03",
                            "agent_type": "packet_explorer",
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "packets": ["global_packet.json", "thread-03.json"],
                            "responsibility": "Review singleton thread",
                        },
                    ],
                },
                "override_signals": [{"reason": "core_files_across_groups"}],
                "common_path_sufficient": True,
                "thread_batch_count": 1,
                "singleton_thread_packet_count": 2,
                "active_areas": ["docs", "runtime"],
                "outdated_transition_candidates": 1,
                "outdated_recheck_ambiguous": 1,
                "thread_counts": {"unresolved": 3, "unresolved_outdated": 1},
                "packet_sizing": {
                    "packet_count": 4,
                    "packet_size_bytes": 1200,
                    "largest_packet_bytes": 500,
                    "largest_two_packets_bytes": 900,
                },
                "efficiency": {
                    "packet_compaction": {
                        "local_only_tokens": 600,
                        "packet_tokens": 250,
                        "savings_tokens": 350,
                        "main_model_input_cost_nanousd": 437500,
                        "provenance": "estimated",
                        "pricing_snapshot_id": "openai-2026-04-09",
                    }
                },
            }

            eval_log.apply_phase_update(log, "build", result, duration=0.25)

            self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
            self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
            self.assertEqual(log["orchestration"]["planned_workers"]["roles"], ["packet_explorer"])
            self.assertEqual(log["orchestration"]["override_signals"], ["core_files_across_groups"])
            self.assertFalse(log["orchestration"]["raw_reread_required"])
            self.assertEqual(log["input_size"]["candidate_batches"], 1)
            self.assertEqual(log["input_size"]["active_areas"], 2)
            self.assertEqual(log["packet_sizing"]["packet_count"], 4)
            self.assertEqual(log["skill_specific"]["data"]["outdated_transition_candidates"], 1)
            self.assertEqual(log["skill_specific"]["data"]["outdated_recheck_ambiguous"], 1)
            self.assertTrue(log["skill_specific"]["data"]["common_path_sufficient"])
            self.assertEqual(log["efficiency"]["packet_compaction"]["packet_tokens"], 250)
            self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 350)

    def test_build_phase_tracks_pre_and_post_sizing_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log = {
                "skill": {"name": "gh-address-review-threads"},
                "quality": {},
                "safety": {},
                "outputs": {},
                "orchestration": {},
                "baseline": {},
                "measurement": {"latency_source": "unavailable"},
                "latency": {
                    "collector_seconds": None,
                    "linter_seconds": None,
                    "packet_builder_seconds": None,
                    "packet_builder_seconds_pre": None,
                    "packet_builder_seconds_post": None,
                    "model_seconds": None,
                    "validator_seconds": None,
                    "apply_seconds": None,
                    "total_seconds": None,
                },
                "skill_specific": {"data": {}},
            }
            pre_result = {
                "review_mode": "targeted-delegation",
                "thread_batch_count": 0,
                "singleton_thread_packet_count": 2,
                "thread_counts": {"unresolved": 2, "unresolved_outdated": 0},
                "packet_sizing": {"packet_count": 3},
                "efficiency": {"packet_compaction": {"local_only_tokens": 600, "packet_tokens": 260, "savings_tokens": 340}},
            }
            post_result = {
                "review_mode": "broad-delegation",
                "thread_batch_count": 1,
                "singleton_thread_packet_count": 2,
                "thread_counts": {"unresolved": 2, "unresolved_outdated": 0},
                "packet_sizing": {"packet_count": 4},
                "efficiency": {"packet_compaction": {"local_only_tokens": 700, "packet_tokens": 300, "savings_tokens": 400}},
            }

            eval_log.apply_phase_update(log, "build", pre_result, duration=0.4, phase_label="pre")
            eval_log.apply_phase_update(log, "build", post_result, duration=0.6, phase_label="post")

            self.assertEqual(log["latency"]["packet_builder_seconds_pre"], 0.4)
            self.assertEqual(log["latency"]["packet_builder_seconds_post"], 0.6)
            self.assertEqual(log["latency"]["packet_builder_seconds"], 1.0)
            self.assertEqual(log["skill_specific"]["data"]["build_phase_count"], 2)
            self.assertEqual(log["skill_specific"]["data"]["build_phases"]["pre"]["packet_count"], 3)
            self.assertEqual(log["skill_specific"]["data"]["build_phases"]["post"]["packet_count"], 4)
            self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 400)
            self.assertEqual(log["measurement"]["latency_source"], "measured")

    def test_apply_phase_merges_review_thread_counters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log = {
                "skill": {"name": "gh-address-review-threads"},
                "quality": {},
                "safety": {},
                "outputs": {},
                "orchestration": {},
                "skill_specific": {"data": {}},
            }
            result = {
                "dry_run": True,
                "fingerprint_match": True,
                "mutations": [
                    {"kind": "add_reply", "thread_id": "t-1", "phase": "complete"},
                    {"kind": "resolve_thread", "thread_id": "t-1", "phase": "complete"},
                ],
                "counters": {
                    "adopted_unmarked_reply_count": 1,
                    "skipped_outdated_count": 2,
                    "invalid_complete_count": 1,
                    "resolve_after_complete_count": 1,
                    "threads_accepted": 1,
                    "threads_rejected": 0,
                    "threads_deferred": 0,
                    "threads_defer_outdated": 2,
                },
                "reconciliation_summary": {
                    "outdated_transition_candidates": 1,
                    "outdated_auto_resolved": 1,
                    "outdated_recheck_ambiguous": 0,
                },
            }

            eval_log.apply_phase_update(log, "apply", result, duration=0.5)

            self.assertEqual(log["quality"]["result_status"], "dry-run")
            self.assertTrue(log["safety"]["fingerprint_match"])
            self.assertEqual(log["skill_specific"]["data"]["adopted_unmarked_reply_count"], 1)
            self.assertEqual(log["skill_specific"]["data"]["skipped_outdated_count"], 2)
            self.assertEqual(log["skill_specific"]["data"]["invalid_complete_count"], 1)
            self.assertEqual(log["skill_specific"]["data"]["resolve_after_complete_count"], 1)
            self.assertEqual(log["skill_specific"]["data"]["outdated_transition_candidates"], 1)
            self.assertEqual(log["skill_specific"]["data"]["outdated_auto_resolved"], 1)
            self.assertEqual(log["skill_specific"]["data"]["outdated_recheck_ambiguous"], 0)
            self.assertEqual(log["skill_specific"]["data"]["threads_resolved"], 1)


if __name__ == "__main__":
    unittest.main()
