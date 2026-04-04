from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402


class WriteEvaluationLogReleaseCopyTests(unittest.TestCase):
    def test_build_phase_merges_packet_metrics_as_eval_only(self) -> None:
        log = {
            "skill": {"name": "draft-release-copy"},
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
            "packet_metrics": {
                "packet_count": 8,
                "largest_packet_bytes": 1200,
                "largest_two_packets_bytes": 2100,
                "estimated_local_only_tokens": 1800,
                "estimated_packet_tokens": 950,
                "estimated_delegation_savings": 850,
                "packet_size_bytes": {"worker_facing_total": 3800, "raw_local_source_bytes": 7200},
            },
        }

        eval_log.apply_phase_update(log, "build", result, duration=0.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["worker_count"], 2)
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 8)
        self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 950)
        self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 850)
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 1800)
        self.assertEqual(log["baseline"]["estimated_token_savings"], 850)
        self.assertEqual(log["baseline"]["estimated_delegation_savings"], 850)
        self.assertEqual(log["measurement"]["token_source"], "estimated")


if __name__ == "__main__":
    unittest.main()
