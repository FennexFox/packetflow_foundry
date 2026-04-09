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

        self.assertEqual(payload["orchestration"]["planned_workers"]["count"], 0)
        self.assertEqual(payload["orchestration"]["planned_workers"]["roles"], [])
        self.assertEqual(payload["orchestration"]["override_signals"], [])
        self.assertNotIn("worker_count", payload["skill_specific"]["data"])
        self.assertNotIn("worker_mix", payload["skill_specific"]["data"])

    def test_build_phase_merges_packet_sizing_and_efficiency_as_eval_only(self) -> None:
        log = {
            "skill": {"name": "draft-release-copy"},
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
                "roles": ["docs_verifier", "large_diff_auditor"],
                "workers": [
                    {
                        "name": "rules",
                        "agent_type": "docs_verifier",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["checklist_packet.json", "global_packet.json", "readme_packet.json"],
                        "responsibility": "Extract release checklist constraints",
                    },
                    {
                        "name": "release-copy",
                        "agent_type": "large_diff_auditor",
                        "model": "gpt-5.4-mini",
                        "reasoning_effort": "medium",
                        "packets": ["changes_packet.json", "global_packet.json", "publish_packet.json"],
                        "responsibility": "Summarize release-copy drift",
                    },
                ],
            },
            "qa_gate_guidance": {
                "required_for_default_plan": True,
                "reason": "broad-delegation plan mutates multiple release-copy surfaces; local QA clear is required before apply.",
            },
            "packet_sizing": {
                "packet_count": 8,
                "largest_packet_bytes": 1200,
                "largest_two_packets_bytes": 2100,
                "packet_size_bytes": 3800,
            },
            "efficiency": {
                "packet_compaction": {
                    "local_only_tokens": 1800,
                    "packet_tokens": 950,
                    "savings_tokens": 850,
                    "main_model_input_cost_nanousd": 1062500,
                    "provenance": "estimated",
                    "pricing_snapshot_id": "openai-2026-04-09",
                },
            },
        }

        eval_log.apply_phase_update(log, "build", result, duration=0.5)

        self.assertEqual(log["orchestration"]["review_mode"], "targeted-delegation")
        self.assertEqual(log["orchestration"]["planned_workers"]["count"], 2)
        self.assertTrue(log["skill_specific"]["data"]["qa_required"])
        self.assertIn("local QA clear", log["skill_specific"]["data"]["qa_reason"])
        self.assertEqual(log["packet_sizing"]["packet_count"], 8)
        self.assertEqual(log["efficiency"]["packet_compaction"]["packet_tokens"], 950)
        self.assertEqual(log["efficiency"]["packet_compaction"]["savings_tokens"], 850)

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
