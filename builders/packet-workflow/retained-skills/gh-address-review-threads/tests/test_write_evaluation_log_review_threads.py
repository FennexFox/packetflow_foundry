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
    def test_build_phase_merges_packet_metrics_and_common_path_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            packet_metrics_path = tmp / "packet_metrics.json"
            packet_metrics_path.write_text(
                "{\n"
                '  "packet_count": 4,\n'
                '  "packet_size_bytes": 1200,\n'
                '  "largest_packet_bytes": 500,\n'
                '  "largest_two_packets_bytes": 900,\n'
                '  "estimated_local_only_tokens": 600,\n'
                '  "estimated_packet_tokens": 250,\n'
                '  "estimated_delegation_savings": 350\n'
                "}\n",
                encoding="utf-8",
            )
            log = {
                "skill": {"name": "gh-address-review-threads"},
                "quality": {},
                "safety": {},
                "outputs": {},
                "orchestration": {},
                "baseline": {},
                "measurement": {"token_source": "unavailable"},
                "skill_specific": {"data": {}},
            }
            result = {
                "review_mode": "targeted-delegation",
                "recommended_worker_count": 2,
                "recommended_workers": [{"agent_type": "packet_explorer"}, {"agent_type": "packet_explorer"}],
                "override_signals": [{"reason": "core_files_across_groups"}],
                "common_path_sufficient": True,
                "thread_batch_count": 1,
                "singleton_thread_packet_count": 2,
                "outdated_transition_candidates": 1,
                "outdated_recheck_ambiguous": 1,
                "thread_counts": {"unresolved": 3, "unresolved_outdated": 1},
                "packet_metrics_file": str(packet_metrics_path),
            }

            eval_log.apply_phase_update(log, "build", result, duration=0.25)

            self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
            self.assertEqual(log["orchestration"]["worker_count"], 2)
            self.assertEqual(log["orchestration"]["worker_roles"], ["packet_explorer", "packet_explorer"])
            self.assertEqual(log["orchestration"]["override_signals"], ["core_files_across_groups"])
            self.assertFalse(log["orchestration"]["raw_reread_required"])
            self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 600)
            self.assertEqual(log["baseline"]["estimated_token_savings"], 350)
            self.assertEqual(log["skill_specific"]["data"]["packet_count"], 4)
            self.assertEqual(log["skill_specific"]["data"]["outdated_transition_candidates"], 1)
            self.assertEqual(log["skill_specific"]["data"]["outdated_recheck_ambiguous"], 1)
            self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 250)
            self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 350)
            self.assertTrue(log["skill_specific"]["data"]["common_path_sufficient"])
            self.assertEqual(log["measurement"]["token_source"], "estimated")

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
