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
    def test_build_base_log_leaves_eval_only_worker_metadata_unset_for_lean_runtime_packets(self) -> None:
        context = {
            "repo_root": str(Path("repo-root")),
            "current_branch": "batch_3",
            "publish_configuration": {},
        }
        orchestrator = {
            "review_mode": "targeted-delegation",
            "packet_files": ["global_packet.json", "release_packet.json", "orchestrator.json"],
            "shared_packet": "global_packet.json",
        }

        payload = eval_log.build_base_log(SCRIPT_DIR / "write_evaluation_log.py", context, orchestrator, None)

        self.assertIsNone(payload["orchestration"]["worker_count"])
        self.assertEqual(payload["orchestration"]["worker_roles"], [])
        self.assertEqual(payload["orchestration"]["override_signals"], [])
        self.assertIsNone(payload["skill_specific"]["data"]["worker_count"])
        self.assertEqual(payload["skill_specific"]["data"]["worker_mix"], [])

    def test_build_phase_merges_packet_metrics_as_eval_only(self) -> None:
        log = {
            "skill": {"name": "draft-release-copy"},
            "quality": {},
            "safety": {},
            "outputs": {},
            "orchestration": {},
            "baseline": {},
            "measurement": {"token_source": "unavailable"},
            "skill_specific": {"data": {"worker_count": 0}},
        }
        result = {
            "review_mode": "targeted-delegation",
            "recommended_worker_count": 2,
            "qa_gate_guidance": {
                "required_for_default_plan": True,
                "reason": "broad-delegation plan mutates multiple release-copy surfaces; local QA clear is required before apply.",
            },
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
        self.assertEqual(log["skill_specific"]["data"]["worker_count"], 2)
        self.assertEqual(log["skill_specific"]["data"]["packet_count"], 8)
        self.assertEqual(log["skill_specific"]["data"]["estimated_packet_tokens"], 950)
        self.assertEqual(log["skill_specific"]["data"]["estimated_delegation_savings"], 850)
        self.assertTrue(log["skill_specific"]["data"]["qa_required"])
        self.assertIn("local QA clear", log["skill_specific"]["data"]["qa_reason"])
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 1800)
        self.assertEqual(log["baseline"]["estimated_token_savings"], 850)
        self.assertEqual(log["baseline"]["estimated_delegation_savings"], 850)
        self.assertEqual(log["measurement"]["token_source"], "estimated")

    def test_validate_and_apply_merge_qa_state(self) -> None:
        log = eval_log.build_base_log(
            SCRIPT_DIR / "write_evaluation_log.py",
            {"repo_root": str(Path("repo-root")), "current_branch": "batch_3", "publish_configuration": {}},
            {
                "review_mode": "broad-delegation",
                "packet_files": ["global_packet.json", "release_packet.json", "orchestrator.json"],
                "shared_packet": "global_packet.json",
            },
            None,
        )

        eval_log.apply_phase_update(
            log,
            "validate",
            {
                "valid": True,
                "qa_required": True,
                "qa_reason": "broad-delegation plan mutates multiple release-copy surfaces; local QA clear is required before apply.",
                "qa_clear": False,
                "validation_commands": ["git rev-parse --short HEAD", "gh auth status"],
                "stop_reasons": [],
            },
            duration=0.1,
        )

        self.assertFalse(log["skill_specific"]["data"]["qa_ran"])

        eval_log.apply_phase_update(
            log,
            "apply",
            {
                "dry_run": True,
                "qa_required": True,
                "qa_clear": True,
                "apply_succeeded": True,
                "mutation_type": "release_copy_apply",
            },
            duration=0.2,
        )

        data = log["skill_specific"]["data"]
        self.assertTrue(data["qa_required"])
        self.assertIn("local QA clear", data["qa_reason"])
        self.assertTrue(data["qa_ran"])
        self.assertEqual(data["validation_commands"], ["git rev-parse --short HEAD", "gh auth status"])


if __name__ == "__main__":
    unittest.main()
