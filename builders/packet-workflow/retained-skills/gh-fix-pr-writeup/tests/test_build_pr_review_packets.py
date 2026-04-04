from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_pr_review_packets as packets  # noqa: E402


def base_context(*, broad: bool) -> dict:
    changed_files = [
        "ExampleProduct/Mod.cs",
        "README.md",
    ]
    if broad:
        changed_files.extend(
            [
                ".github/instructions/pull-request.instructions.md",
                ".github/workflows/release.yml",
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
                "ExampleProduct/Setting.cs",
                "MAINTAINING.md",
                "CONTRIBUTING.md",
                "ExampleProduct/ExampleProduct.csproj",
                "docs/faq.md",
                ".github/scripts/check_release.py",
                "tests/test_writeup_rules.py",
            ]
        )
    sample_groups = {
        "runtime": {
            "count": 2 if broad else 1,
            "sample_files": [
                "ExampleProduct/Mod.cs",
                *(["ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs"] if broad else []),
            ],
        },
        "automation": {
            "count": 2 if broad else 0,
            "sample_files": [
                *([ ".github/instructions/pull-request.instructions.md"] if broad else []),
                *([".github/workflows/release.yml"] if broad else []),
            ],
        },
        "docs": {
            "count": 3 if broad else 1,
            "sample_files": ["README.md", *(["MAINTAINING.md"] if broad else [])],
        },
        "tests": {
            "count": 2 if broad else 0,
            "sample_files": [*(["tests/writeup_packets_test.py", "tests/test_writeup_rules.py"] if broad else [])],
        },
        "config": {
            "count": 1 if broad else 0,
            "sample_files": ["ExampleProduct/ExampleProduct.csproj"] if broad else [],
        },
        "other": {"count": 0, "sample_files": []},
    }
    body = "\n".join(
        [
            "## Why",
            "The current writeup is too vague.",
            "## What changed",
            "- Reworked the PR body structure.",
            "## How",
            "Updated the template sections.",
            "## Risk / Rollback",
            "Minimal risk.",
            "## Testing",
            "Not run.",
        ]
    )
    return {
        "repo_root": str(Path.cwd()),
        "repo_slug": "owner/repo",
        "pr": {
            "number": 42,
            "title": "docs: polish PR text",
            "url": "https://example.com/pr/42",
            "body": body,
            "headRefName": "codex/writeup",
            "headRefOid": "abc123",
            "baseRefName": "main",
            "closingIssuesReferences": [{"number": 9}],
        },
        "changed_files": changed_files,
        "changed_file_groups": sample_groups,
        "diff_stat": f" {len(changed_files)} files changed, 280 insertions(+), 35 deletions(-)" if broad else " 4 files changed, 28 insertions(+), 5 deletions(-)",
        "checks": {
            "title_matches_conventional_commit": False,
            "body_has_template_sections": True,
        },
        "expected_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "current_body_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
        "rule_files": {"pull_request_template": ".github/pull_request_template.md"},
        "instruction_snippets": {
            "pull_request_title_rules_excerpt": "Use Conventional Commit titles.",
            "pull_request_template_sections": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
            "commit_types_excerpt": "feat, fix, docs",
        },
    }


def lint_payload() -> dict:
    return {
        "findings": {
            "errors": ["Template guidance text is still present in `How`."],
            "warnings": ["`Testing` does not cite any exact command or concrete verification step."],
            "info": [],
            "detected": {},
            "drafting_basis": {
                "rewrite_strategy": "full-rewrite",
                "active_rule_gates": ["title_pattern", "required_sections", "testing_evidence"],
                "current_failures": {
                    "errors": ["Template guidance text is still present in `How`."],
                    "warnings": ["`Testing` does not cite any exact command or concrete verification step."],
                },
                "title_direction": {"status": "rewrite", "current_title": "docs: polish PR text", "constraint": "<type>(<scope>): <summary>"},
                "required_sections_status": {
                    "required": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
                    "present": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
                    "missing": [],
                    "ordered": True,
                },
                "section_rewrite_requirements": [{"section": "How", "reason": "Template guidance text is still present in `How`."}],
                "supported_claims": [{"cluster": "runtime", "basis": "runtime files changed", "evidence_anchor": "ExampleProduct/Mod.cs"}],
                "unsupported_claim_risks": ["defaults_thresholds"],
                "testing_evidence_status": {"present": True, "has_exact_command": False, "status": "needs-recheck"},
                "issue_ref_status": {"metadata_refs": ["9"], "body_refs": [], "matched_refs": [], "status": "missing-body-ref"},
                "coverage_gaps": ["testing claims need an exact command or concrete verification step."],
            },
        },
        "drafting_basis": {
            "rewrite_strategy": "full-rewrite",
            "active_rule_gates": ["title_pattern", "required_sections", "testing_evidence"],
            "current_failures": {
                "errors": ["Template guidance text is still present in `How`."],
                "warnings": ["`Testing` does not cite any exact command or concrete verification step."],
            },
            "title_direction": {"status": "rewrite", "current_title": "docs: polish PR text", "constraint": "<type>(<scope>): <summary>"},
            "required_sections_status": {
                "required": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
                "present": ["Why", "What changed", "How", "Risk / Rollback", "Testing"],
                "missing": [],
                "ordered": True,
            },
            "section_rewrite_requirements": [{"section": "How", "reason": "Template guidance text is still present in `How`."}],
            "supported_claims": [{"cluster": "runtime", "basis": "runtime files changed", "evidence_anchor": "ExampleProduct/Mod.cs"}],
            "unsupported_claim_risks": ["defaults_thresholds"],
            "testing_evidence_status": {"present": True, "has_exact_command": False, "status": "needs-recheck"},
            "issue_ref_status": {"metadata_refs": ["9"], "body_refs": [], "matched_refs": [], "status": "missing-body-ref"},
            "coverage_gaps": ["testing claims need an exact command or concrete verification step."],
        },
    }


class BuildPrReviewPacketsTests(unittest.TestCase):
    def run_builder(self, context: dict, lint: dict) -> tuple[Path, dict]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        tmp = Path(temp_dir.name)
        context_path = tmp / "context.json"
        lint_path = tmp / "lint.json"
        output_dir = tmp / "packets"
        result_path = tmp / "build-result.json"
        context_path.write_text(json.dumps(context), encoding="utf-8")
        lint_path.write_text(json.dumps(lint), encoding="utf-8")
        argv = [
            "build_pr_review_packets.py",
            "--context",
            str(context_path),
            "--lint",
            str(lint_path),
            "--output-dir",
            str(output_dir),
            "--result-output",
            str(result_path),
        ]
        with patch.object(sys, "argv", argv):
            self.assertEqual(packets.main(), 0)
        return output_dir, json.loads(result_path.read_text(encoding="utf-8"))

    def test_broad_full_rewrite_emits_packet_heavy_profile_and_qa_gate(self) -> None:
        output_dir, build_result = self.run_builder(base_context(broad=True), lint_payload())
        orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
        global_packet = json.loads((output_dir / "global_packet.json").read_text(encoding="utf-8"))
        rules_packet = json.loads((output_dir / "rules_packet.json").read_text(encoding="utf-8"))
        synthesis_packet = json.loads((output_dir / "synthesis_packet.json").read_text(encoding="utf-8"))
        packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))

        self.assertEqual(orchestrator["orchestrator_profile"], "packet-heavy-orchestrator")
        self.assertEqual(orchestrator["shared_local_packet"], "synthesis_packet.json")
        self.assertEqual(orchestrator["packet_worker_map"], packets.PACKET_WORKER_MAP)
        self.assertEqual(global_packet["packet_worker_map"], packets.PACKET_WORKER_MAP)
        self.assertNotIn("packet_size_bytes", orchestrator)
        self.assertNotIn("estimated_packet_tokens", orchestrator)
        self.assertIn("packet_size_bytes", packet_metrics)
        self.assertGreater(packet_metrics["estimated_delegation_savings"], 0)
        self.assertLess(packet_metrics["estimated_packet_tokens"], packet_metrics["estimated_local_only_tokens"])
        self.assertEqual(build_result["qa_required"], True)
        self.assertEqual(synthesis_packet["qa_required"], True)
        self.assertEqual(synthesis_packet["rewrite_strategy"], "full-rewrite")
        self.assertEqual(synthesis_packet["focused_packet_hint"], "testing_packet.json")
        self.assertNotIn("repo_instruction_excerpts", synthesis_packet)
        self.assertNotIn("current_failures", rules_packet)
        self.assertIn("repo_instruction_excerpts", rules_packet)
        self.assertIn("current_failures", synthesis_packet)
        self.assertEqual(orchestrator["common_path_contract"]["required_packets"], ["rules_packet.json", "synthesis_packet.json"])

    def test_apply_override_adjustment_handles_broad_mode_group_count(self) -> None:
        review_mode, worker_count, adjustments = packets.apply_override_adjustment(
            review_mode="broad-delegation",
            worker_count=3,
            group_count=5,
            diff_totals={"churn": 10},
            runtime_active=True,
            process_active=True,
            testing_relevant=True,
            override_signals=[],
        )

        self.assertEqual(review_mode, "broad-delegation")
        self.assertEqual(worker_count, 4)
        self.assertEqual(adjustments, [])

    def test_small_full_rewrite_does_not_force_qa(self) -> None:
        output_dir, build_result = self.run_builder(base_context(broad=False), lint_payload())
        orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
        synthesis_packet = json.loads((output_dir / "synthesis_packet.json").read_text(encoding="utf-8"))
        self.assertEqual(build_result["review_mode_baseline"], "local-only")
        self.assertEqual(build_result["review_mode"], "targeted-delegation")
        self.assertIn("delegation_savings_floor", build_result["review_mode_adjustments"])
        self.assertEqual(orchestrator["review_mode_baseline"], "local-only")
        self.assertIn("delegation_savings_floor", orchestrator["review_mode_adjustments"])
        self.assertFalse(build_result["qa_required"])
        self.assertFalse(synthesis_packet["qa_required"])
        self.assertIsNone(synthesis_packet["qa_reason"])

    def test_common_path_contract_and_metrics_result_are_written(self) -> None:
        output_dir, build_result = self.run_builder(base_context(broad=False), lint_payload())
        packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(build_result["common_path_sufficient"])
        self.assertEqual(build_result["raw_reread_count"], 0)
        self.assertEqual(packet_metrics["common_path_packets"][:2], ["rules_packet.json", "synthesis_packet.json"])
        self.assertTrue(packet_metrics["packet_insufficiency_is_failure"])
        self.assertIn("synthesis_packet.json", build_result["packet_files"])


if __name__ == "__main__":
    unittest.main()
