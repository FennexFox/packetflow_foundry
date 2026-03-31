from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

sys.modules.pop("write_evaluation_log", None)
import write_evaluation_log as eval_log  # noqa: E402


def context() -> dict:
    return {
        "repo_root": str(Path.cwd()),
        "repo_slug": "owner/repo",
        "changed_files": ["README.md", "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs"],
        "expected_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "current_body_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "pr": {
            "number": 7,
            "title": "docs(pr-writeup): tighten lint coverage",
            "body": "body",
            "url": "https://example.invalid/pr/7",
            "headRefName": "codex/guard",
            "headRefOid": "abc123def456",
            "baseRefName": "main",
        },
    }


def orchestrator() -> dict:
    return {
        "review_mode": "targeted-delegation",
        "recommended_worker_count": 2,
        "packet_files": [
            "global_packet.json",
            "rules_packet.json",
            "runtime_packet.json",
            "synthesis_packet.json",
            "orchestrator.json",
        ],
        "shared_packet": "global_packet.json",
    }


class WriteEvaluationLogGhFixPrWriteupTests(unittest.TestCase):
    def test_build_phase_merges_packet_metrics_and_common_path_fields(self) -> None:
        log = eval_log.build_base_log(Path(eval_log.__file__), context(), orchestrator(), None)
        result = {
            "review_mode": "broad-delegation",
            "recommended_worker_count": 3,
            "rewrite_strategy": "full-rewrite",
            "qa_required": True,
            "qa_reason": "broad-delegation full rewrite requires QA cross-check",
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "packet_metrics": {
                "packet_count": 6,
                "estimated_local_only_tokens": 2400,
                "estimated_packet_tokens": 900,
                "estimated_delegation_savings": 1500,
            },
        }

        eval_log.apply_phase_update(log, "build", result, 0.25)

        data = log["skill_specific"]["data"]
        self.assertEqual(data["packet_count"], 6)
        self.assertEqual(data["rewrite_strategy"], "full-rewrite")
        self.assertTrue(data["qa_required"])
        self.assertTrue(data["common_path_sufficient"])
        self.assertEqual(data["raw_reread_count"], 0)
        self.assertEqual(data["estimated_packet_tokens"], 900)
        self.assertEqual(data["estimated_delegation_savings"], 1500)
        self.assertEqual(log["baseline"]["estimated_local_only_tokens"], 2400)
        self.assertEqual(log["baseline"]["estimated_token_savings"], 1500)
        self.assertEqual(log["measurement"]["token_source"], "estimated")

    def test_validate_and_apply_merge_qa_state(self) -> None:
        log = eval_log.build_base_log(Path(eval_log.__file__), context(), orchestrator(), None)

        eval_log.apply_phase_update(
            log,
            "validate",
            {
                "valid": True,
                "qa_required": True,
                "qa_reason": "worker-local claim conflict",
                "validation_commands": ["candidate lint", "gh auth status"],
                "stop_reasons": [],
            },
            0.1,
        )
        eval_log.apply_phase_update(
            log,
            "apply",
            {
                "dry_run": True,
                "qa_required": True,
                "qa_clear": True,
                "apply_succeeded": True,
                "mutation_type": "gh_pr_edit",
            },
            0.2,
        )

        data = log["skill_specific"]["data"]
        self.assertTrue(data["qa_required"])
        self.assertEqual(data["qa_reason"], "worker-local claim conflict")
        self.assertTrue(data["qa_ran"])
        self.assertEqual(data["validation_commands"], ["candidate lint", "gh auth status"])


if __name__ == "__main__":
    unittest.main()
