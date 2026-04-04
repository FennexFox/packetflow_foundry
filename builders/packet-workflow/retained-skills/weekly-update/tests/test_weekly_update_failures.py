from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import weekly_update_lib as wl
from test_weekly_update_contract import build_fixture_context, load_json


def valid_plan(context: dict[str, object]) -> dict[str, object]:
    return {
        "context_id": context.get("context_id"),
        "context_fingerprint": context.get("context_fingerprint"),
        "reporting_window": context.get("reporting_window"),
        "selected_packets": ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"],
        "overall_confidence": "medium",
        "stop_reasons": [],
        "allow_marker_update": False,
        "sections": wl.empty_plan_sections(),
    }


class WeeklyUpdateFailurePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = load_json("weekly_update_sample.json")
        self.context = build_fixture_context(self.sample)

    def test_collect_context_stops_immediately_when_gh_auth_is_invalid(self) -> None:
        repo_path = Path("C:/repo")
        with (
            patch.object(wl, "resolve_repo_root", return_value=repo_path),
            patch.object(wl, "verify_gh_auth", side_effect=SystemExit("[ERROR] GitHub evidence is required but gh auth is invalid: auth failed")),
            patch.object(wl, "get_repo_metadata") as mocked_repo_metadata,
        ):
            with self.assertRaises(SystemExit):
                wl.collect_context(repo_root=str(repo_path), now_utc="2026-03-27T12:00:00Z")
        mocked_repo_metadata.assert_not_called()

    def test_verify_gh_auth_stops_cleanly_when_gh_is_missing(self) -> None:
        with patch.object(wl.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(SystemExit) as exc_info:
                wl.verify_gh_auth(Path("C:/repo"))
        self.assertIn("gh auth is invalid", str(exc_info.exception))

    def test_quiet_window_uses_local_only_review_mode(self) -> None:
        quiet_context = dict(self.context)
        quiet_context["releases"] = []
        quiet_context["top_level_prs"] = []
        quiet_context["nested_prs"] = []
        quiet_context["pr_lineage"] = {}
        quiet_context["classified_issues"] = []
        quiet_context["review_findings"] = []
        quiet_context["workflow_failures"] = []
        quiet_context["candidate_inventory"] = []
        quiet_context["counts"] = {
            "releases": 0,
            "top_level_prs": 0,
            "nested_prs": 0,
            "selected_issues": 0,
            "review_findings": 0,
            "workflow_failures": 0,
            "actual_incident_items": 0,
            "changed_files": 0,
            "task_packet_count": len(wl.PACKET_NAMES),
            "batch_count": 0,
        }
        quiet_context["override_signals"] = {
            "high_churn": False,
            "multi_surface_active": False,
            "nested_lineage_complexity": False,
        }
        lint = wl.lint_context(quiet_context)
        packets = wl.build_packets(quiet_context, lint)
        self.assertTrue(lint["can_proceed"])
        self.assertEqual(packets["orchestrator.json"]["review_mode"], "local-only")
        self.assertEqual(packets["orchestrator.json"]["recommended_workers"], [])
        self.assertEqual(packets["changes_packet.json"]["candidate_ids"], [])
        self.assertEqual(packets["incidents_packet.json"]["candidate_ids"], [])
        self.assertEqual(packets["risks_packet.json"]["candidate_ids"], [])

    def test_override_signal_promotes_local_only_to_targeted_delegation(self) -> None:
        quiet_context = dict(self.context)
        quiet_context["releases"] = []
        quiet_context["top_level_prs"] = []
        quiet_context["nested_prs"] = []
        quiet_context["pr_lineage"] = {}
        quiet_context["classified_issues"] = []
        quiet_context["review_findings"] = []
        quiet_context["workflow_failures"] = []
        quiet_context["candidate_inventory"] = []
        quiet_context["counts"] = {
            "releases": 0,
            "top_level_prs": 0,
            "nested_prs": 0,
            "selected_issues": 0,
            "review_findings": 0,
            "workflow_failures": 0,
            "actual_incident_items": 0,
            "changed_files": 0,
            "task_packet_count": len(wl.PACKET_NAMES),
            "batch_count": 0,
        }
        quiet_context["override_signals"] = {
            "high_churn": True,
            "multi_surface_active": False,
            "nested_lineage_complexity": False,
        }
        lint = wl.lint_context(quiet_context)
        packets = wl.build_packets(quiet_context, lint)
        self.assertTrue(lint["can_proceed"])
        self.assertEqual(packets["orchestrator.json"]["review_mode_baseline"], "local-only")
        self.assertEqual(packets["orchestrator.json"]["review_mode"], "targeted-delegation")
        self.assertEqual(packets["orchestrator.json"]["review_mode_adjustments"], ["override_signal"])
        self.assertGreater(len(packets["orchestrator.json"]["recommended_workers"]), 0)

    def test_non_mapping_analysis_ref_is_ignored_during_packet_builds(self) -> None:
        legacy_context = dict(self.context)
        legacy_context["analysis_ref"] = "main"
        normalized_context = dict(self.context)
        normalized_context["analysis_ref"] = {}

        self.assertEqual(
            wl.build_context_fingerprint(legacy_context),
            wl.build_context_fingerprint(normalized_context),
        )

        lint = wl.lint_context(legacy_context)
        artifacts = wl.build_packet_artifacts(legacy_context, lint)

        self.assertIsNone(artifacts["packets"]["global_packet.json"]["analysis_ref"]["policy"])
        self.assertIsNone(artifacts["build_result"]["analysis_ref_policy"])
        self.assertIsNone(artifacts["build_result"]["analysis_ref_selected_branch"])
        self.assertIsNone(artifacts["build_result"]["analysis_ref_selected_sha"])

    def test_collect_context_surfaces_truncation_warnings_in_source_gaps(self) -> None:
        repo_path = Path("C:/repo")
        with (
            patch.object(wl, "resolve_repo_root", return_value=repo_path),
            patch.object(wl, "verify_gh_auth", return_value=None),
            patch.object(wl, "get_repo_metadata", return_value={"repo_slug": "example/repo", "default_branch": "master", "repo_url": "https://example.invalid/repo"}),
            patch.object(wl, "get_branch_state", return_value={"current_branch": "master", "head_sha": "deadbeef"}),
            patch.object(
                wl,
                "resolve_analysis_ref",
                return_value={
                    "policy": wl.DEFAULT_ANALYSIS_REF_POLICY,
                    "preferred_branch_order": [],
                    "resolved_via": wl.DEFAULT_ANALYSIS_REF_POLICY,
                    "selected_ref": "refs/heads/master",
                    "selected_branch": "master",
                    "selected_branch_label": "master",
                    "selected_sha": "deadbeef",
                    "selected_commit_timestamp": "2026-03-27T12:00:00Z",
                    "workspace_branch": "master",
                    "workspace_branch_label": "master",
                    "workspace_head_sha": "deadbeef",
                    "workspace_commit_timestamp": "2026-03-27T12:00:00Z",
                    "workspace_detached": False,
                    "selection_matches_workspace_head": True,
                    "local_branch_count": 1,
                    "read_mode": wl.ANALYSIS_REF_READ_MODE,
                    "treeish": "deadbeef",
                    "git_common_dir": "C:/repo/.git",
                    "fallback_reason": None,
                },
            ),
            patch.object(wl, "compute_repo_hash", return_value="fixturehash"),
            patch.object(wl, "load_state_marker", return_value=(None, [])),
            patch.object(wl, "list_releases", return_value=([], [])),
            patch.object(wl, "list_issues", return_value=([], ["issues may be truncated after 20 pages."])),
            patch.object(wl, "list_merged_pr_summaries", return_value=([], [])),
            patch.object(wl, "list_workflow_runs", return_value=([], [])),
        ):
            context = wl.collect_context(repo_root=str(repo_path), state_file="C:/state.json", now_utc="2026-03-27T12:00:00Z")
        self.assertIn("issues may be truncated after 20 pages.", context["source_gaps"])
        self.assertEqual(context["counts"]["top_level_prs"], 0)

    def test_validator_blocks_marker_updates_when_conflicting_reread_candidates_remain(self) -> None:
        context = dict(self.context)
        context["candidate_inventory"] = [dict(candidate) for candidate in self.context["candidate_inventory"]]
        issue_110 = next(candidate for candidate in context["candidate_inventory"] if candidate["candidate_id"] == "issue-110")
        issue_110["raw_reread_reason"] = "conflicting_signals"
        issue_110["confidence"] = "low"
        plan = valid_plan(context)
        plan["allow_marker_update"] = True
        result = wl.validate_weekly_update_plan(context, plan)
        self.assertFalse(result["valid"])
        self.assertIn("allow_marker_update=true but unresolved raw reread candidates remain.", result["errors"])

    def test_validator_rejects_artifact_only_candidates_as_direct_section_items(self) -> None:
        plan = valid_plan(self.context)
        plan["sections"]["Blockers / Risks"] = [{"candidate_id": "issue-103", "text": "Artifact should not surface as a blocker."}]
        result = wl.validate_weekly_update_plan(self.context, plan)
        self.assertFalse(result["valid"])
        self.assertIn("issue-103", "".join(result["errors"]))

    def test_validator_rejects_low_confidence_marker_updates(self) -> None:
        plan = valid_plan(self.context)
        plan["overall_confidence"] = "low"
        plan["allow_marker_update"] = True
        result = wl.validate_weekly_update_plan(self.context, plan)
        self.assertFalse(result["valid"])
        self.assertIn("allow_marker_update=true is not permitted when overall_confidence=low.", result["errors"])


if __name__ == "__main__":
    unittest.main()
