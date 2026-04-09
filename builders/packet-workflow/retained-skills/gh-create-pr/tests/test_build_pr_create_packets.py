from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_pr_create_packets as builder  # noqa: E402
from pr_create_test_support import REPO_TEMPLATE_SECTIONS  # noqa: E402

def collected_context() -> dict:
    return {
        "repo_root": str(Path.cwd()),
        "repo_slug": "owner/repo",
        "resolved_head": "feature/pr-create",
        "resolved_base": "main",
        "local_head_oid": "abc123",
        "remote_head_oid": "abc123",
        "changed_files": ["src/creator.py", "README.md", "tests/test_creator.py"],
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["src/creator.py"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 1, "sample_files": ["README.md"]},
            "tests": {"count": 1, "sample_files": ["tests/test_creator.py"]},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
        "template_selection": {
            "status": "selected",
            "selected_path": "C:/repo/.github/pull_request_template.md",
            "fingerprint": "sha256:template",
        },
        "expected_template_sections": list(REPO_TEMPLATE_SECTIONS),
        "duplicate_check_hint": {"status": "clear", "matched_repo_slug": "owner/repo", "matched_head": "feature/pr-create"},
        "issue_reference_hints": {
            "numbers": ["42"],
            "branch": "feature/pr-create",
            "branch_numbers": ["42"],
            "commit_subjects": [],
            "commit_numbers": [],
            "operator_supplied": ["42"],
        },
        "testing_signal_candidates": {
            "exact_commands": ["python -m unittest"],
            "operator_supplied": ["python -m unittest"],
            "supports_positive_testing_claims": True,
            "test_files_changed": True,
        },
        "create_options": {"reviewers": [], "assignees": [], "labels": [], "milestone": None, "draft": False, "no_maintainer_edit": False},
        "diff_stat": " 3 files changed, 5 insertions(+), 1 deletion(-)",
        "repo_profile_name": "default",
        "repo_profile_path": "profiles/default/profile.json",
        "repo_profile_summary": "Default profile",
        "repo_profile": {"name": "default"},
        "recent_commit_subjects": ["feat(pr-create): add guarded creator #42"],
    }


def lint_report() -> dict:
    return {
        "findings": {
            "errors": [],
            "warnings": [],
            "override_signals": {
                "high_churn": False,
                "multi_group_core_files": False,
                "generated_not_majority": False,
            },
        },
        "drafting_basis": {
            "active_rule_gates": ["title_pattern", "required_sections"],
            "required_sections_status": {"required": list(REPO_TEMPLATE_SECTIONS)},
            "supported_claims": [{"cluster": "runtime", "basis": "runtime files changed", "evidence_anchor": "src/creator.py"}],
            "issue_reference_hints": {"numbers": ["42"]},
            "testing_evidence_status": {"exact_commands": ["python -m unittest"]},
            "coverage_gaps": [],
            "focused_packet_hint": "runtime_packet.json",
        },
    }


class BuildPrCreatePacketsTests(unittest.TestCase):
    def test_build_packet_payloads_emits_packet_heavy_outputs(self) -> None:
        packets, build_result = builder.build_packet_payloads(collected_context(), lint_report())

        self.assertIn("rules_packet.json", packets)
        self.assertIn("runtime_packet.json", packets)
        self.assertIn("testing_packet.json", packets)
        self.assertIn("synthesis_packet.json", packets)
        self.assertIn("orchestrator.json", packets)
        self.assertIn("packet_sizing.json", packets)
        self.assertEqual(build_result["shared_local_packet"], "synthesis_packet.json")
        self.assertEqual(packets["orchestrator.json"]["routing_contract"], builder.contract.ROUTING_CONTRACT)
        self.assertEqual(packets["global_packet.json"]["routing_contract"], builder.contract.ROUTING_CONTRACT)
        self.assertNotIn("review_mode_baseline", packets["orchestrator.json"])
        self.assertNotIn("review_mode_adjustments", packets["orchestrator.json"])
        self.assertNotIn("recommended_workers", packets["orchestrator.json"])
        self.assertNotIn("optional_workers", packets["orchestrator.json"])
        self.assertNotIn("review_overrides", packets["global_packet.json"])
        self.assertEqual(packets["process_packet.json"]["issue_reference_hints"]["operator_supplied"], ["42"])
        self.assertEqual(packets["synthesis_packet.json"]["issue_reference_hints"]["numbers"], ["42"])
        self.assertEqual(packets["testing_packet.json"]["testing_signal_candidates"]["operator_supplied"], ["python -m unittest"])
        self.assertIn(
            "restart/reload, rollout, and consumer migration/compatibility claims are blocked by default",
            packets["rules_packet.json"]["strict_claim_gates"],
        )
        self.assertIn(
            "unchecked template checklist items are not treated as asserted claims until checked or rewritten as prose",
            packets["rules_packet.json"]["strict_claim_gates"],
        )
        self.assertEqual(build_result["review_mode_baseline"], "targeted-delegation")
        self.assertIn("planned_workers", build_result)
        self.assertIn("optional_workers", build_result)
        self.assertEqual(build_result["planned_workers"]["count"], 2)
        self.assertEqual(build_result["delegation_non_use_cases"], builder.contract.DELEGATION_NON_USE_CASES)


if __name__ == "__main__":
    unittest.main()
