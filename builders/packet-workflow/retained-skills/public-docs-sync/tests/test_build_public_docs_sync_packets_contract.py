import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_public_docs_sync_packets as packets
import public_docs_sync_contract as contract


class BuildPublicDocsSyncPacketsContractTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_routing_metadata_and_review_mode_helpers(self) -> None:
        self.assertEqual(packets.PACKET_WORKER_MAP["claims_packet"], ["large_diff_auditor", "repo_mapper"])
        self.assertEqual(packets.PACKET_WORKER_MAP["batch-packet-01"], ["docs_verifier"])
        self.assertEqual(
            packets.compute_baseline_review_mode(
                {"counts": {"active_packet_count": 1, "changed_files": 3, "doc_changes": 1, "code_changes": 0}}
            ),
            "local-only",
        )
        self.assertEqual(
            packets.compute_baseline_review_mode(
                {"counts": {"active_packet_count": 2, "changed_files": 3, "doc_changes": 1, "code_changes": 0}}
            ),
            "targeted-delegation",
        )
        self.assertEqual(
            packets.compute_baseline_review_mode(
                {"counts": {"active_packet_count": 4, "changed_files": 3, "doc_changes": 1, "code_changes": 0}}
            ),
            "broad-delegation",
        )
        self.assertEqual(
            packets.apply_override_adjustment(
                "local-only",
                {
                    "override_signals": {"high_churn": True},
                },
                {"override_signals": {}},
            ),
            ("targeted-delegation", True, ["high_churn"], ["override_signal"]),
        )
        self.assertEqual(
            packets.maybe_apply_delegation_savings_floor(
                "local-only",
                {"estimated_delegation_savings": 249},
                [],
            ),
            ("local-only", []),
        )
        self.assertEqual(
            packets.maybe_apply_delegation_savings_floor(
                "local-only",
                {"estimated_delegation_savings": 250},
                [],
            ),
            ("targeted-delegation", ["delegation_savings_floor"]),
        )
        recommended = packets.recommended_workers(
            ["claims_packet", "reporting_packet", "workflow_packet"],
            "targeted-delegation",
        )
        self.assertEqual(recommended[0]["agent_type"], "large_diff_auditor")
        self.assertEqual(recommended[1]["agent_type"], "evidence_summarizer")
        optional = packets.optional_workers(
            "broad-delegation",
            packets.recommended_workers(
                ["claims_packet", "reporting_packet", "workflow_packet", "batch-packet-01"],
                "broad-delegation",
            ),
        )
        self.assertEqual([item["agent_type"] for item in optional], ["repo_mapper", "log_triager"])
        promoted = packets.recommended_workers(
            ["claims_packet"],
            "targeted-delegation",
            ["delegation_savings_floor"],
        )
        self.assertEqual(len(promoted), 2)
        self.assertEqual(promoted[1]["agent_type"], "repo_mapper")

    def test_packet_emission_result_output_and_metrics_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_path = tmp / "context.json"
            lint_path = tmp / "lint.json"
            output_dir = tmp / "packets"
            result_path = tmp / "build-result.json"

            context = {
                "skill_name": "public-docs-sync",
                "context_id": "ctx-1",
                "context_fingerprint": "fp-1",
                "repo_root": str(tmp / "repo"),
                "relevant_ref": {"kind": "merge-base", "base_commit": "abc123"},
                "authority_order": ["runtime", "docs", "workflow"],
                "stop_conditions": ["stale"],
                "github_evidence_required": True,
                "evidence_summary": {
                    "urls": ["https://example.test/pr/1"],
                    "packet_signals": {"claims_packet": ["comment"]},
                },
                "github_evidence": {
                    "auth_policy": "fail-closed",
                    "artifacts": [
                        {
                            "packet_hints": ["claims_packet", "forms_batch_packet"],
                            "url": "https://example.test/artifact",
                        }
                    ],
                },
                "counts": {"active_packet_count": 4, "changed_files": 7, "doc_changes": 2, "code_changes": 1},
                "override_signals": {},
                "deterministic_apply_boundaries": {"mode": "narrow"},
                "notes": ["note"],
                "public_doc_inventory": {
                    "README.md": {
                        "exists": True,
                        "kind": "markdown",
                        "sha256": "aaa",
                        "headings": ["One"],
                        "preview_lines": ["# One"],
                        "issue_form": None,
                        "publish_configuration": None,
                        "settings_table": None,
                    },
                    "docs/issue-form.md": {
                        "exists": True,
                        "kind": "markdown",
                        "sha256": "bbb",
                        "headings": ["Issue"],
                        "preview_lines": ["# Issue"],
                        "issue_form": None,
                        "publish_configuration": None,
                        "settings_table": None,
                    },
                },
                "changed_path_summaries": {
                    "README.md": {
                        "kind": "markdown",
                        "exists": True,
                        "preview_lines": ["# One"],
                        "headings": ["One"],
                    }
                },
                "packet_candidates": {
                    "claims_packet": {
                        "active": True,
                        "packet_kind": "focused",
                        "review_docs": ["README.md"],
                        "changed_paths": ["README.md"],
                        "direct_doc_changes": ["README.md"],
                        "direct_source_changes": [],
                        "activation_reasons": ["claims drift"],
                    },
                    "reporting_packet": {
                        "active": True,
                        "packet_kind": "focused",
                        "review_docs": ["README.md"],
                        "changed_paths": [],
                        "direct_doc_changes": [],
                        "direct_source_changes": [],
                        "activation_reasons": ["evidence"],
                    },
                    "workflow_packet": {
                        "active": True,
                        "packet_kind": "focused",
                        "review_docs": ["README.md"],
                        "changed_paths": [],
                        "direct_doc_changes": [],
                        "direct_source_changes": [],
                        "activation_reasons": ["workflow"],
                    },
                    "forms_batch_packet": {
                        "active": True,
                        "packet_kind": "batch",
                        "review_docs": ["README.md", "docs/issue-form.md"],
                        "changed_paths": ["README.md"],
                        "direct_doc_changes": ["README.md"],
                        "direct_source_changes": [],
                        "activation_reasons": ["forms"],
                    },
                },
            }
            lint = {
                "issues": [
                    {"packet": "claims_packet", "message": "claims drift"},
                    {"packet": "forms_batch_packet", "message": "forms drift"},
                ],
                "packet_basis": {
                    "claims_packet": {
                        "deterministic_action_candidates": [
                            {
                                "packet": "claims_packet",
                                "kind": "settings_default_sync",
                                "canonical_type": "settings_table_default_sync",
                                "path": "README.md",
                                "message": "Sync a README setting row.",
                                "details": {"setting": "EnableThing"},
                                "evidence_anchor": "runtime default",
                                "expected_edit_scope": "single README settings-table cell update",
                            }
                        ],
                        "manual_review_residuals": [],
                        "marker_gate_signals": {
                            "marker_blocked_by_packet": False,
                            "blocking_reasons": [],
                            "manual_review_residual_count": 0,
                            "deterministic_candidate_count": 1,
                        },
                    },
                    "forms_batch_packet": {
                        "deterministic_action_candidates": [
                            {
                                "packet": "forms_batch_packet",
                                "kind": "issue_template_metadata_sync",
                                "canonical_type": "issue_template_metadata_sync",
                                "path": "docs/issue-form.md",
                                "message": "Sync issue-form metadata.",
                                "details": {"field": "labels"},
                                "evidence_anchor": "form metadata",
                                "expected_edit_scope": "single issue-template metadata update",
                            }
                        ],
                        "manual_review_residuals": [
                            {
                                "classification": "review_required",
                                "path": "README.md",
                                "message": "Narrative review still needed.",
                                "severity": "warning",
                                "blocking_scope": "marker-update",
                                "related_paths": ["README.md"],
                                "evidence_anchor": "review signal",
                            }
                        ],
                        "marker_gate_signals": {
                            "marker_blocked_by_packet": True,
                            "blocking_reasons": ["Narrative review still needed."],
                            "manual_review_residual_count": 1,
                            "deterministic_candidate_count": 1,
                        },
                    },
                },
                "auto_apply_candidates": [
                    {"packet": "claims_packet", "path": "README.md", "kind": "settings_default_sync"},
                    {"packet": "forms_batch_packet", "path": "docs/issue-form.md", "kind": "issue_template_metadata_sync"},
                ],
                "override_signals": {"lint": True},
            }

            self.write_json(context_path, context)
            self.write_json(lint_path, lint)

            with mock.patch.object(
                sys,
                "argv",
                [
                    "build_public_docs_sync_packets.py",
                    "--context",
                    str(context_path),
                    "--lint",
                    str(lint_path),
                    "--output-dir",
                    str(output_dir),
                    "--result-output",
                    str(result_path),
                ],
            ):
                exit_code = packets.main()

            self.assertEqual(exit_code, 0)

            orchestrator = self.read_json(output_dir / "orchestrator.json")
            global_packet = self.read_json(output_dir / "global_packet.json")
            claims_packet = self.read_json(output_dir / "claims_packet.json")
            forms_packet = self.read_json(output_dir / "forms_batch_packet.json")
            batch_packet = self.read_json(output_dir / "batch-packet-01.json")
            packet_metrics = self.read_json(output_dir / "packet_metrics.json")
            build_result = self.read_json(result_path)

            self.assertEqual(orchestrator["orchestrator_profile"], "standard")
            self.assertEqual(orchestrator["review_mode"], "broad-delegation")
            self.assertFalse(orchestrator["decision_ready_packets"])
            self.assertEqual(orchestrator["worker_return_contract"], contract.WORKER_RETURN_CONTRACT)
            self.assertEqual(orchestrator["worker_output_shape"], contract.WORKER_OUTPUT_SHAPE)
            self.assertEqual(orchestrator["applied_override_signals"], ["lint"])
            self.assertEqual(orchestrator["packet_worker_map"], contract.PACKET_WORKER_MAP)
            self.assertEqual(orchestrator["raw_reread_allowed_reasons"], contract.RAW_REREAD_ALLOWED_REASONS)
            self.assertNotIn("packet_size_bytes", orchestrator)
            self.assertEqual(
                [worker["agent_type"] for worker in orchestrator["recommended_workers"]],
                ["large_diff_auditor", "evidence_summarizer", "docs_verifier", "docs_verifier"],
            )
            self.assertEqual(orchestrator["recommended_workers"][-1]["packet"], "batch-packet-01.json")
            self.assertEqual([worker["agent_type"] for worker in orchestrator["optional_workers"]], ["repo_mapper", "log_triager"])
            self.assertEqual(global_packet["orchestrator_profile"], "standard")
            self.assertEqual(global_packet["review_mode_overrides"], contract.REVIEW_MODE_OVERRIDES)
            self.assertEqual(global_packet["packet_worker_map"]["batch-packet-01"], ["docs_verifier"])
            self.assertEqual(global_packet["raw_reread_allowed_reasons"], contract.RAW_REREAD_ALLOWED_REASONS)
            self.assertEqual(global_packet["github_evidence_urls"], ["https://example.test/pr/1"])
            self.assertEqual(claims_packet["ownership_summary"]["packet"], "claims_packet")
            self.assertEqual(claims_packet["deterministic_action_candidates"][0]["canonical_type"], "settings_table_default_sync")
            self.assertEqual(claims_packet["manual_review_residuals"], [])
            self.assertFalse(claims_packet["marker_gate_signals"]["marker_blocked_by_packet"])
            self.assertEqual(forms_packet["marker_gate_signals"]["manual_review_residual_count"], 1)
            self.assertEqual(batch_packet["deterministic_action_candidates"][0]["canonical_type"], "issue_template_metadata_sync")
            self.assertEqual(
                packet_metrics,
                contract.compute_packet_metrics(
                    {
                        "orchestrator.json": orchestrator,
                        "global_packet.json": global_packet,
                        "claims_packet.json": claims_packet,
                        "reporting_packet.json": self.read_json(output_dir / "reporting_packet.json"),
                        "workflow_packet.json": self.read_json(output_dir / "workflow_packet.json"),
                        "forms_batch_packet.json": forms_packet,
                        "batch-packet-01.json": batch_packet,
                    },
                    local_only_sources={
                        "context.json": context,
                        "lint.json": lint,
                    },
                ),
            )
            self.assertEqual(packet_metrics["packet_count"], 7)
            self.assertEqual(build_result["auto_apply_candidate_count"], 2)
            self.assertEqual(build_result["packet_metrics"]["largest_packet_bytes"], packet_metrics["largest_packet_bytes"])

    def test_common_path_focused_packets_are_decision_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            context_path = tmp / "context.json"
            lint_path = tmp / "lint.json"
            output_dir = tmp / "packets"

            context = {
                "skill_name": "public-docs-sync",
                "context_id": "ctx-1",
                "context_fingerprint": "fp-1",
                "repo_root": str(tmp / "repo"),
                "relevant_ref": {"kind": "merge-base", "base_commit": "abc123"},
                "authority_order": ["runtime", "docs"],
                "stop_conditions": ["stale"],
                "github_evidence_required": False,
                "evidence_summary": {"urls": [], "packet_signals": {}},
                "github_evidence": {"auth_policy": "fail-closed", "artifacts": []},
                "counts": {"active_packet_count": 1, "changed_files": 1, "doc_changes": 1, "code_changes": 0},
                "override_signals": {},
                "deterministic_apply_boundaries": {"mode": "narrow"},
                "notes": [],
                "public_doc_inventory": {
                    "README.md": {"exists": True, "kind": "markdown", "sha256": "aaa", "headings": ["One"], "preview_lines": ["# One"]},
                },
                "changed_path_summaries": {
                    "README.md": {"kind": "markdown", "exists": True, "preview_lines": ["# One"], "headings": ["One"]},
                },
                "packet_candidates": {
                    "claims_packet": {
                        "active": True,
                        "packet_kind": "focused",
                        "review_docs": ["README.md"],
                        "changed_paths": ["README.md"],
                        "direct_doc_changes": ["README.md"],
                        "direct_source_changes": [],
                        "activation_reasons": ["claims drift"],
                    },
                    "reporting_packet": {"active": False, "packet_kind": "focused", "review_docs": [], "changed_paths": [], "direct_doc_changes": [], "direct_source_changes": [], "activation_reasons": []},
                    "workflow_packet": {"active": False, "packet_kind": "focused", "review_docs": [], "changed_paths": [], "direct_doc_changes": [], "direct_source_changes": [], "activation_reasons": []},
                    "forms_batch_packet": {"active": False, "packet_kind": "batch", "review_docs": [], "changed_paths": [], "direct_doc_changes": [], "direct_source_changes": [], "activation_reasons": []},
                },
            }
            lint = {
                "issues": [],
                "packet_basis": {
                    "claims_packet": {
                        "deterministic_action_candidates": [
                            {
                                "packet": "claims_packet",
                                "kind": "public_doc_reference_sync",
                                "canonical_type": "public_doc_reference_sync",
                                "path": "README.md",
                                "message": "Sync a single line.",
                                "details": {"match_text": "old", "replacement_text": "new"},
                                "evidence_anchor": "changed source summary",
                                "expected_edit_scope": "single-line replacement",
                            }
                        ],
                        "manual_review_residuals": [],
                        "marker_gate_signals": {
                            "marker_blocked_by_packet": False,
                            "blocking_reasons": [],
                            "manual_review_residual_count": 0,
                            "deterministic_candidate_count": 1,
                        },
                    }
                },
                "auto_apply_candidates": [{"packet": "claims_packet", "path": "README.md", "kind": "public_doc_reference_sync"}],
                "override_signals": {},
            }

            self.write_json(context_path, context)
            self.write_json(lint_path, lint)

            with mock.patch.object(
                sys,
                "argv",
                [
                    "build_public_docs_sync_packets.py",
                    "--context",
                    str(context_path),
                    "--lint",
                    str(lint_path),
                    "--output-dir",
                    str(output_dir),
                ],
            ):
                exit_code = packets.main()

            self.assertEqual(exit_code, 0)
            global_packet = self.read_json(output_dir / "global_packet.json")
            claims_packet = self.read_json(output_dir / "claims_packet.json")
            self.assertEqual(global_packet["selected_packets"], ["claims_packet.json"])
            self.assertIn("xhigh_reread_policy", global_packet)
            self.assertEqual(claims_packet["ownership_summary"]["review_docs"], ["README.md"])
            self.assertEqual(claims_packet["deterministic_action_candidates"][0]["expected_edit_scope"], "single-line replacement")
            self.assertEqual(claims_packet["manual_review_residuals"], [])
            self.assertFalse(claims_packet["marker_gate_signals"]["marker_blocked_by_packet"])


if __name__ == "__main__":
    unittest.main()
