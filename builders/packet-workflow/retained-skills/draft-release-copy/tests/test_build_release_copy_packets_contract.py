import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release_copy_packets as packets
import release_copy_plan_contract as contract


BASELINE_WORKER_FACING_BYTES = 8832
TARGET_WORKER_FACING_BYTES = int(BASELINE_WORKER_FACING_BYTES * 0.75)


class BuildReleaseCopyPacketsContractTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def build_context(self) -> dict:
        return {
            "repo_slug": "owner/repo",
            "branch": "main",
            "head_commit": "abc1234",
            "base_tag": "v1.2.2",
            "target_version": "1.2.3",
            "revision_range": "v1.2.2..HEAD",
            "context_fingerprint": "sha256:context",
            "freshness_tuple": {
                "head_commit": "abc1234",
                "base_tag": "v1.2.2",
                "target_version": "1.2.3",
                "evidence_fingerprint": "sha256:evidence",
                "existing_release_issue": {
                    "number": 42,
                    "title": "[Release] v1.2.3",
                    "state": "OPEN",
                    "url": "https://example.invalid/issues/42",
                    "body_fingerprint": "sha256:issue",
                },
            },
            "existing_release_issue": {
                "number": 42,
                "title": "[Release] v1.2.3",
                "url": "https://example.invalid/issues/42",
                "state": "OPEN",
                "body": "Existing checklist body",
                "evidence": {
                    "software_track_status": "pending",
                },
                "checked_labels": ["PublishConfiguration wording reviewed against shipped behavior"],
            },
            "project_title_default": "ExampleProduct Tracker",
            "diff_stat": " 6 files changed, 180 insertions(+), 25 deletions(-)",
            "changed_files": [
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
                "ExampleProduct/Setting.cs",
                "README.md",
                "ExampleProduct/Properties/PublishConfiguration.xml",
                ".github/workflows/release.yml",
                "MAINTAINING.md",
            ],
            "changed_file_groups": {
                "runtime": {
                    "count": 2,
                    "sample_files": [
                        "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
                        "ExampleProduct/Setting.cs",
                    ],
                },
                "docs": {
                    "count": 2,
                    "sample_files": ["README.md", "MAINTAINING.md"],
                },
                "config": {
                    "count": 2,
                    "sample_files": [
                        "ExampleProduct/Properties/PublishConfiguration.xml",
                        ".github/workflows/release.yml",
                    ],
                },
                "automation": {"count": 0, "sample_files": []},
                "tests": {"count": 0, "sample_files": []},
                "other": {"count": 0, "sample_files": []},
            },
            "changed_file_stats": {
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs": {
                    "insertions": 120,
                    "deletions": 40,
                    "churn": 160,
                },
                "ExampleProduct/Setting.cs": {
                    "insertions": 40,
                    "deletions": 20,
                    "churn": 60,
                },
                "README.md": {"insertions": 10, "deletions": 4, "churn": 14},
                "ExampleProduct/Properties/PublishConfiguration.xml": {
                    "insertions": 6,
                    "deletions": 2,
                    "churn": 8,
                },
                ".github/workflows/release.yml": {
                    "insertions": 3,
                    "deletions": 1,
                    "churn": 4,
                },
                "MAINTAINING.md": {"insertions": 1, "deletions": 0, "churn": 1},
            },
            "commit_subjects": [
                "Tighten diagnostics wording for release",
                "Refresh release checklist guidance",
            ],
            "publish_configuration": {
                "short_description": "Current short description",
                "long_description": "Current long description.",
                "change_log": "- Current release note.",
                "mod_version": "1.2.3",
            },
            "base_tag_publish_configuration": {
                "change_log": "- Prior release note.",
            },
            "readme": {
                "intro_text": "# ExampleProduct\n\nIntro text.",
                "sections": {
                    "Current Release": "Current release block.",
                    "Current Status": "Current status block.",
                },
            },
            "release_checklist": {
                "title_prefix": "[Release] ",
                "fields": [
                    {"id": "target_version", "label": "Target version"},
                    {"id": "included_changes", "label": "Included changes"},
                ],
                "checkbox_labels": [
                    "PublishConfiguration wording reviewed against shipped behavior",
                    "Release notes reviewed",
                ],
            },
            "local_release_helper": {
                "status": "present",
                "repo_relative_path": "scripts/release.ps1",
            },
            "evidence": {
                "software_track_status": "pending",
                "comparable_evidence": "",
                "anchor_comparison": "",
                "release_pr_validation_note": "",
            },
        }

    def build_lint(self) -> dict:
        return {
            "checks": {
                "evidence_complete": False,
                "applicable_validation_tracks": {
                    "software_gate": True,
                    "telemetry_validation": False,
                },
                "helper_handoff_allowed": True,
                "rewrite_publish_recommended": True,
                "rewrite_readme_recommended": True,
            },
            "findings": {
                "errors": [
                    {
                        "area": "publish",
                        "code": "unsupported_strong_software_claim",
                        "message": "Release-facing copy makes strong software-track claims without complete evidence.",
                    }
                ],
                "warnings": [
                    {
                        "area": "readme",
                        "code": "setting_default_mismatch",
                        "message": "`SoftCap` default is `4000` in README but `5000` in Setting.cs.",
                    },
                    {
                        "area": "checklist",
                        "code": "checklist_field_unresolved",
                        "message": "Release-gate evidence field remains unresolved.",
                    },
                ],
                "info": [
                    {
                        "area": "helper",
                        "code": "missing_local_release_script",
                        "message": "Helper handoff remains local-only.",
                    }
                ],
            },
        }

    def run_builder(self, context: dict, lint: dict, *, result_output: bool = False) -> tuple[int, str, dict[str, dict], dict | None]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_path = tmp / "context.json"
            lint_path = tmp / "lint.json"
            output_dir = tmp / "packets"
            result_path = tmp / "build.json"
            self.write_json(context_path, context)
            self.write_json(lint_path, lint)

            argv = [
                "build_release_copy_packets.py",
                "--context",
                str(context_path),
                "--lint",
                str(lint_path),
                "--output-dir",
                str(output_dir),
            ]
            if result_output:
                argv.extend(["--result-output", str(result_path)])

            stdout = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                argv,
            ), redirect_stdout(stdout):
                exit_code = packets.main()

            payloads = {
                path.name: self.read_json(path)
                for path in output_dir.iterdir()
            }
            result_payload = self.read_json(result_path) if result_output else None
            return exit_code, stdout.getvalue(), payloads, result_payload

    def test_contract_metadata_and_routing_helpers(self) -> None:
        self.assertEqual(contract.WORKFLOW_FAMILY, "release-copy")
        self.assertEqual(contract.ARCHETYPE, "audit-and-apply")
        self.assertEqual(contract.ORCHESTRATOR_PROFILE, "packet-heavy-orchestrator")
        self.assertEqual(contract.SHARED_PACKET, "global_packet.json")
        self.assertEqual(contract.SHARED_LOCAL_PACKET, "synthesis_packet.json")
        self.assertEqual(
            contract.runtime_artifact_names(include_optional=False),
            [
                "orchestrator.json",
                "global_packet.json",
                "publish_packet.json",
                "readme_packet.json",
                "changes_packet.json",
                "checklist_packet.json",
                "synthesis_packet.json",
            ],
        )
        self.assertEqual(contract.runtime_field_roles()["routing_authority"], "packet_worker_map")
        self.assertEqual(
            contract.runtime_field_roles()["preferred_worker_families_role"],
            "registry_metadata_only",
        )
        self.assertEqual(
            contract.runtime_field_roles()["derived_worker_fields"],
            ["recommended_workers", "optional_workers"],
        )
        self.assertEqual(packets.packet_worker_map()["publish_packet"], ["large_diff_auditor"])
        self.assertEqual(packets.packet_worker_map()["checklist_packet"], ["docs_verifier", "repo_mapper"])
        self.assertEqual(packets.baseline_review_mode(5, 2), ("local-only", 0))
        self.assertEqual(packets.baseline_review_mode(9, 2), ("targeted-delegation", 2))
        self.assertEqual(packets.baseline_review_mode(21, 4), ("broad-delegation", 3))
        self.assertEqual(
            packets.apply_override_adjustment(
                "local-only",
                0,
                1,
                [{"reason": "override", "detail": "x"}],
            ),
            ("targeted-delegation", 2, ["override_signal"]),
        )
        self.assertEqual(
            packets.apply_override_adjustment(
                "targeted-delegation",
                2,
                2,
                [{"reason": "override", "detail": "x"}],
            ),
            ("broad-delegation", 3, ["override_signal"]),
        )
        self.assertEqual(
            packets.maybe_apply_delegation_savings_floor(
                "local-only",
                0,
                {"estimated_delegation_savings": 250},
                [],
            ),
            ("targeted-delegation", 2, ["delegation_savings_floor"]),
        )
        self.assertEqual(
            packets.handoff_command(
                {
                    "target_version": "1.2.3",
                    "local_release_helper": {"status": "present", "repo_relative_path": "helpers/run.ps1"},
                },
                {"checks": {"helper_handoff_allowed": True}},
            ),
            r"powershell -File .\helpers\run.ps1 -Version v1.2.3",
        )
        self.assertIsNone(
            packets.handoff_command(
                {
                    "target_version": "1.2.3",
                    "local_release_helper": {"status": "missing", "repo_relative_path": "helpers/run.ps1"},
                },
                {"checks": {"helper_handoff_allowed": True}},
            )
        )

    def test_help_and_result_output_emit_machine_readable_build_summary(self) -> None:
        help_text = packets.build_parser().format_help()
        self.assertIn("--result-output", help_text)

        context = self.build_context()
        lint = self.build_lint()

        exit_code, stdout, payloads, result_payload = self.run_builder(context, lint, result_output=True)

        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(result_payload)

        stdout_payload = json.loads(stdout)
        self.assertEqual(stdout_payload, result_payload)

        orchestrator = payloads["orchestrator.json"]
        packet_metrics = payloads["packet_metrics.json"]
        self.assertEqual(result_payload["review_mode"], orchestrator["review_mode"])
        self.assertEqual(result_payload["recommended_worker_count"], orchestrator["recommended_worker_count"])
        self.assertEqual(result_payload["packet_files"], orchestrator["packet_files"])
        self.assertEqual(result_payload["packet_metrics"], packet_metrics)
        self.assertTrue(result_payload["packet_metrics_file"].endswith("packet_metrics.json"))
        self.assertEqual(result_payload["packet_count"], packet_metrics["packet_count"])
        self.assertEqual(result_payload["largest_packet_bytes"], packet_metrics["largest_packet_bytes"])
        self.assertEqual(result_payload["largest_two_packets_bytes"], packet_metrics["largest_two_packets_bytes"])
        self.assertEqual(result_payload["estimated_local_only_tokens"], packet_metrics["estimated_local_only_tokens"])
        self.assertEqual(result_payload["estimated_packet_tokens"], packet_metrics["estimated_packet_tokens"])
        self.assertEqual(result_payload["estimated_delegation_savings"], packet_metrics["estimated_delegation_savings"])
        self.assertEqual(result_payload["packet_size_bytes"], packet_metrics["packet_size_bytes"])
        self.assertTrue(result_payload["common_path_sufficient"])
        self.assertEqual(
            result_payload["synthesis_packet_sufficient_for_common_path"],
            packet_metrics["synthesis_packet_sufficient_for_common_path"],
        )

    def test_packet_emission_and_common_path_sufficiency(self) -> None:
        context = self.build_context()
        lint = self.build_lint()

        exit_code, stdout, payloads, result_payload = self.run_builder(context, lint)

        self.assertEqual(exit_code, 0)
        self.assertIsNone(result_payload)
        self.assertIn('"review_mode": "targeted-delegation"', stdout)

        expected_files = {
            "global_packet.json",
            "publish_packet.json",
            "readme_packet.json",
            "changes_packet.json",
            "checklist_packet.json",
            "evidence_packet.json",
            "synthesis_packet.json",
            "orchestrator.json",
            "packet_metrics.json",
        }
        emitted_files = set(payloads)
        self.assertEqual(emitted_files, expected_files)

        global_packet = payloads["global_packet.json"]
        publish_packet = payloads["publish_packet.json"]
        readme_packet = payloads["readme_packet.json"]
        changes_packet = payloads["changes_packet.json"]
        checklist_packet = payloads["checklist_packet.json"]
        evidence_packet = payloads["evidence_packet.json"]
        synthesis_packet = payloads["synthesis_packet.json"]
        orchestrator = payloads["orchestrator.json"]
        packet_metrics = payloads["packet_metrics.json"]

        self.assertTrue(packets.synthesis_packet_common_path_ready(synthesis_packet))
        self.assertTrue(packets.SYNTHESIS_REQUIRED_KEYS.issubset(synthesis_packet))
        self.assertTrue(synthesis_packet["common_path_contract"]["sufficient_for_local_final_drafting"])
        self.assertTrue(synthesis_packet["common_path_contract"]["packet_insufficiency_is_failure"])
        self.assertEqual(
            synthesis_packet["common_path_contract"]["raw_reread_allowed_reasons"],
            contract.RAW_REREAD_ALLOWED_REASONS,
        )
        self.assertEqual(
            synthesis_packet["plan_defaults"]["draft_basis"]["raw_reread_count"],
            0,
        )
        self.assertFalse(
            synthesis_packet["plan_defaults"]["draft_basis"]["compensatory_reread_detected"]
        )

        self.assertEqual(global_packet["worker_return_contract"], contract.WORKER_RETURN_CONTRACT)
        self.assertEqual(global_packet["worker_output_shape"], contract.WORKER_OUTPUT_SHAPE)
        self.assertEqual(global_packet["workflow_family"], contract.WORKFLOW_FAMILY)
        self.assertEqual(global_packet["authority_order"], contract.AUTHORITY_ORDER)
        self.assertEqual(global_packet["gate_summary"]["helper_status"], "present")
        self.assertNotIn("packet_worker_map", global_packet)
        self.assertNotIn("changed_files", changes_packet)
        self.assertTrue(changes_packet["topic_signals"])
        self.assertTrue(changes_packet["representative_files"])
        self.assertTrue(changes_packet["condensed_commit_subjects"])
        self.assertTrue(synthesis_packet["shipped_change_summary"]["topic_signals"])
        self.assertNotIn("packet_worker_map", publish_packet)
        self.assertNotIn("packet_worker_map", readme_packet)
        self.assertNotIn("packet_worker_map", changes_packet)
        self.assertNotIn("packet_worker_map", checklist_packet)
        self.assertNotIn("packet_worker_map", evidence_packet)

        self.assertEqual(orchestrator["workflow_family"], contract.WORKFLOW_FAMILY)
        self.assertEqual(orchestrator["archetype"], contract.ARCHETYPE)
        self.assertEqual(orchestrator["orchestrator_profile"], contract.ORCHESTRATOR_PROFILE)
        self.assertEqual(orchestrator["shared_packet"], "global_packet.json")
        self.assertEqual(orchestrator["shared_local_packet"], "synthesis_packet.json")
        self.assertEqual(orchestrator["routing_contract"], contract.runtime_field_roles())
        self.assertEqual(orchestrator["review_mode_baseline"], "targeted-delegation")
        self.assertEqual(orchestrator["review_mode_adjustments"], [])
        self.assertEqual(
            orchestrator["common_path_contract"]["required_packets"],
            ["global_packet.json", "synthesis_packet.json"],
        )
        self.assertEqual(
            orchestrator["common_path_contract"]["max_additional_focused_packets"],
            contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
        )
        self.assertEqual(orchestrator["raw_reread_allowed_reasons"], contract.RAW_REREAD_ALLOWED_REASONS)
        self.assertNotIn("estimated_packet_tokens", orchestrator)
        self.assertNotIn("estimated_delegation_savings", orchestrator)

        self.assertEqual(packet_metrics["packet_count"], len(orchestrator["packet_files"]))
        self.assertEqual(packet_metrics["packet_count"], len(expected_files) - 1)
        packet_sizes = packet_metrics["packet_size_bytes"]
        self.assertEqual(
            packet_sizes["worker_facing_total"],
            sum(
                packet_sizes["by_packet"][name]
                for name in expected_files
                if name not in {"synthesis_packet.json", "orchestrator.json", "packet_metrics.json"}
            ),
        )
        self.assertLessEqual(packet_sizes["worker_facing_total"], TARGET_WORKER_FACING_BYTES)
        self.assertGreater(packet_sizes["raw_local_source_bytes"], 0)
        self.assertGreater(packet_metrics["estimated_delegation_savings"], 0)
        self.assertGreaterEqual(packet_metrics["largest_packet_bytes"], 1)
        self.assertGreaterEqual(packet_metrics["largest_two_packets_bytes"], packet_metrics["largest_packet_bytes"])


if __name__ == "__main__":
    unittest.main()
