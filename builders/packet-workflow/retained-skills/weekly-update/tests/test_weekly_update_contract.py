from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import weekly_update_lib as wl
import build_weekly_update_packets as build_packets_script
import smoke_weekly_update as smoke


def load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8-sig"))


def pr_body(pr: dict[str, Any]) -> str:
    sections = [
        "## What changed",
        *[f"- {bullet}" for bullet in pr.get("shipped_change_bullets", [])],
        "",
        "## Risk / Rollback",
        *[f"- {bullet}" for bullet in pr.get("review_followups", [])],
        "",
        "## Validation",
        "- Weekly fixture check.",
    ]
    return "\n".join(sections)


def to_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"],
        "labels": issue.get("labels", []),
        "state": issue.get("state", "OPEN"),
        "createdAt": issue.get("created_at"),
        "updatedAt": issue.get("updated_at"),
        "url": f"https://example.invalid/issues/{issue['number']}",
    }


def to_pr(pr: dict[str, Any]) -> dict[str, Any]:
    head_ref_name = pr.get("head_ref_name")
    if not head_ref_name:
        head_ref_name = "develop" if pr["number"] == 97 else f"branch/{pr['number']}"
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": f"https://example.invalid/pull/{pr['number']}",
        "body": pr_body(pr),
        "base_ref_name": pr["base_ref_name"],
        "head_ref_name": head_ref_name,
        "merged_at": pr["merged_at"],
        "merge_commit_sha": f"deadbeef{pr['number']}",
        "linked_issue_numbers": pr.get("linked_issue_numbers", []),
        "files": [{"path": f"src/file_{pr['number']}.cs"}],
        "changed_file_groups": {"runtime": [f"src/file_{pr['number']}.cs"], "automation": [], "docs": [], "tests": [], "config": [], "other": []},
        "shipped_change_bullets": list(pr.get("shipped_change_bullets", [])),
        "risk_bullets": list(pr.get("review_followups", [])),
        "validation_bullets": ["Weekly fixture check."],
    }


def review_comments_by_pr(sample: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for thread in sample["review_threads"]:
        bucket = grouped.setdefault(int(thread["pr_number"]), [])
        for comment in thread["comments"]:
            bucket.append(
                {
                    "id": comment["id"],
                    "body": comment["body"],
                    "created_at": comment["created_at"],
                    "updated_at": comment["created_at"],
                    "in_reply_to_id": comment.get("in_reply_to_id"),
                    "path": comment.get("path"),
                    "html_url": f"https://example.invalid/review/{comment['id']}",
                    "user": {"login": comment.get("author", "")},
                }
            )
    return grouped


def build_fixture_context(sample: dict[str, Any]) -> dict[str, Any]:
    profile_path = wl.default_repo_profile_path()
    repo_profile = wl.load_repo_profile(profile_path)
    runtime_settings = wl.weekly_update_runtime_settings(repo_profile)
    now_utc = wl.parse_iso8601(sample["now_utc"])
    reporting_window = wl.select_reporting_window(now_utc=now_utc, window_days=int(sample["window_days"]), state_marker=sample["state_marker"])
    start = wl.parse_iso8601(reporting_window["start_utc"])
    end = wl.parse_iso8601(reporting_window["end_utc"])
    assert start is not None and end is not None

    releases = [
        {
            "tag_name": release["tag_name"],
            "name": release["tag_name"],
            "url": f"https://example.invalid/releases/{release['tag_name']}",
            "published_at": release["published_at"],
            "body": "",
        }
        for release in sample["releases"]
        if wl.window_contains(release.get("published_at"), start, end)
    ]
    prs = [to_pr(pr) for pr in sample["prs"] if wl.window_contains(pr.get("merged_at"), start, end)]
    top_level_prs, nested_prs, pr_lineage = wl.build_pr_lineage(prs, sample["default_branch"])
    issues = [to_issue(issue) for issue in sample["issues"]]
    release_issue_linkage = wl.link_releases_to_issues(
        releases,
        issues,
        release_title_re=runtime_settings["release_title_re"],
    )
    linked_issue_numbers = wl.build_issue_linkage_set(top_level_prs)
    active_release_tags = {release["tag_name"] for release in releases}
    classified_issues = [
        classified
        for classified in (
            wl.classify_issue(
                issue,
                window_start=start,
                window_end=end,
                linked_issue_numbers=linked_issue_numbers,
                active_release_tags=active_release_tags,
                release_title_re=runtime_settings["release_title_re"],
            )
            for issue in issues
        )
        if classified["classification"] != wl.IGNORE
    ]
    review_findings: list[dict[str, Any]] = []
    for pr_number, comments in review_comments_by_pr(sample).items():
        review_findings.extend(
            wl.extract_review_findings(
                pr_number,
                f"https://example.invalid/pull/{pr_number}",
                comments,
                window_start=start,
                window_end=end,
                review_ack_patterns=runtime_settings["review_ack_patterns"],
                review_complete_patterns=runtime_settings["review_complete_patterns"],
                priority_marker_re=runtime_settings["priority_marker_re"],
            )
        )
    workflow_failures = [
        candidate
        for candidate in (
            wl.classify_workflow_run(run, window_start=start, window_end=end)
            for run in sample["workflow_runs"]
        )
        if candidate is not None
    ]
    context = {
        "skill_name": wl.SKILL_NAME,
        "skill_version": wl.SKILL_VERSION,
        "workflow_family": wl.WORKFLOW_FAMILY,
        "archetype": wl.ARCHETYPE,
        "repo_root": str(wl.skill_root().parents[3]),
        "repo_hash": "fixturehash",
        "repo_slug": "example/repo",
        "repo_url": "https://example.invalid/repo",
        "current_branch": sample["default_branch"],
        "head_sha": "abcdef123456",
        "branch_state": {
            "branch": sample["default_branch"],
            "head_sha": "abcdef123456",
        },
        "analysis_ref": {
            "policy": runtime_settings["analysis_ref"]["policy"],
            "preferred_branch_order": list(
                runtime_settings["analysis_ref"]["preferred_branch_order"]
            ),
            "resolved_via": runtime_settings["analysis_ref"]["policy"],
            "selected_ref": f"refs/heads/{sample['default_branch']}",
            "selected_branch": sample["default_branch"],
            "selected_branch_label": sample["default_branch"],
            "selected_sha": "abcdef123456",
            "selected_commit_timestamp": sample["now_utc"],
            "workspace_branch": sample["default_branch"],
            "workspace_branch_label": sample["default_branch"],
            "workspace_head_sha": "abcdef123456",
            "workspace_commit_timestamp": sample["now_utc"],
            "workspace_detached": False,
            "selection_matches_workspace_head": True,
            "local_branch_count": 1,
            "read_mode": wl.ANALYSIS_REF_READ_MODE,
            "treeish": "abcdef123456",
            "git_common_dir": str((wl.skill_root().parents[3] / ".git").resolve()),
            "fallback_reason": None,
        },
        "workspace_branch_state": {
            "current_branch": sample["default_branch"],
            "head_sha": "abcdef123456",
            "detached": False,
        },
        "repo_profile_name": str(repo_profile.get("name") or ""),
        "repo_profile_path": str(profile_path),
        "repo_profile_summary": str(repo_profile.get("summary") or ""),
        "repo_profile": repo_profile,
        "state_namespace": runtime_settings["state_namespace"],
        "default_branch": sample["default_branch"],
        "reporting_window": reporting_window,
        "releases": releases,
        "release_issue_linkage": release_issue_linkage,
        "top_level_prs": top_level_prs,
        "nested_prs": nested_prs,
        "pr_lineage": pr_lineage,
        "classified_issues": classified_issues,
        "review_findings": review_findings,
        "workflow_failures": workflow_failures,
        "source_gaps": [],
        "override_signals": {},
        "context_id": "weekly-update:20260327T120000Z:fixturehash",
        "notes": [f"Loaded repo profile from {profile_path}."],
    }
    context["candidate_inventory"] = wl.build_candidate_inventory(context, releases, top_level_prs, issues, classified_issues, review_findings, workflow_failures, release_issue_linkage)
    context["counts"] = {
        "releases": len(releases),
        "top_level_prs": len(top_level_prs),
        "nested_prs": len(nested_prs),
        "selected_issues": len(classified_issues),
        "review_findings": len(review_findings),
        "workflow_failures": len(workflow_failures),
        "actual_incident_items": sum(1 for candidate in context["candidate_inventory"] if candidate["proposed_classification"] == wl.ACTUAL_INCIDENT),
        "changed_files": sum(len(pr.get("files") or []) for pr in prs),
        "task_packet_count": len(wl.PACKET_NAMES),
        "batch_count": 0,
    }
    context["override_signals"] = {
        "high_churn": False,
        "multi_surface_active": True,
        "nested_lineage_complexity": False,
    }
    context["context_fingerprint"] = wl.build_context_fingerprint(context)
    return context


class WeeklyUpdateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = load_json("weekly_update_sample.json")
        self.context = build_fixture_context(self.sample)
        self.lint = wl.lint_context(self.context)
        self.artifacts = wl.build_packet_artifacts(self.context, self.lint)
        self.packets = wl.build_packets(self.context, self.lint)
        self.packet_metrics = self.artifacts["packet_metrics"]
        self.build_result = self.artifacts["build_result"]
        self.ready_plan = load_json("weekly_update_plan_ready.json")
        self.low_plan = load_json("weekly_update_plan_low.json")
        self.reread_plan = load_json("weekly_update_plan_reread.json")

    def test_reporting_window_reuses_last_success_marker(self) -> None:
        window = self.context["reporting_window"]
        self.assertEqual(window["source"], "state_marker")
        self.assertEqual(window["start_utc"], "2026-03-20T23:59:59Z")
        self.assertEqual(window["end_utc"], "2026-03-27T12:00:00Z")

    def test_nested_pr_lineage_dedups_into_top_level_pr(self) -> None:
        self.assertEqual([pr["number"] for pr in self.context["top_level_prs"]], [97, 101])
        self.assertEqual([pr["number"] for pr in self.context["nested_prs"]], [90, 93])
        self.assertEqual(self.context["pr_lineage"]["90"]["root_top_level_pr"], 97)
        self.assertEqual(self.context["pr_lineage"]["93"]["root_top_level_pr"], 97)
        self.assertEqual(self.context["top_level_prs"][0]["absorbed_nested_pr_numbers"], [90, 93])

    def test_releases_are_window_bounded(self) -> None:
        self.assertEqual([release["tag_name"] for release in self.context["releases"]], ["v0.2.2", "v0.2.3"])

    def test_issue_classification_matches_contract_examples(self) -> None:
        candidates = {candidate["candidate_id"]: candidate for candidate in self.context["candidate_inventory"] if candidate["source_type"] == "issue"}
        self.assertEqual(candidates["issue-110"]["proposed_classification"], wl.ACTUAL_INCIDENT)
        self.assertEqual(candidates["issue-111"]["proposed_classification"], wl.BLOCKER_OR_RISK)
        self.assertEqual(candidates["issue-103"]["proposed_classification"], wl.ARTIFACT_ONLY)

    def test_review_noise_is_filtered_and_real_findings_survive(self) -> None:
        review_candidates = [candidate for candidate in self.context["candidate_inventory"] if candidate["source_type"] == "review_finding"]
        self.assertEqual([candidate["candidate_id"] for candidate in review_candidates], ["review-pr107-comment2992368622", "review-pr107-comment2992369000"])
        self.assertEqual(review_candidates[0]["proposed_classification"], wl.IGNORE)
        self.assertEqual(review_candidates[1]["proposed_classification"], wl.BLOCKER_OR_RISK)

    def test_schema_uses_source_refs_and_forbidden_field_is_absent(self) -> None:
        self.assertIn("overall_confidence", self.packets["global_packet.json"]["worker_output_contract"]["worker_footer_fields"])
        self.assertEqual(self.packets["global_packet.json"]["worker_output_contract"]["worker_output_shape"], "hierarchical")
        self.assertEqual(self.packets["global_packet.json"]["worker_output_contract"]["footer_container"], "footer")
        for candidate in self.context["candidate_inventory"]:
            self.assertIn("source_refs", candidate)
            self.assertNotIn("evidence_files_or_links", candidate)
            self.assertTrue(candidate["packet_membership"])
            for ref in candidate["source_refs"]:
                self.assertIn("kind", ref)
                self.assertIn("ref", ref)

    def test_active_profile_metadata_is_propagated_to_context_packets_and_build_result(self) -> None:
        global_packet = self.packets["global_packet.json"]
        orchestrator = self.packets["orchestrator.json"]
        self.assertEqual(self.context["repo_profile_name"], "default")
        self.assertEqual(self.context["state_namespace"], "weekly-update")
        self.assertEqual(
            self.context["repo_profile"]["extra"]["weekly_update"]["review_markers"]["acknowledged"],
            ["phase=ack"],
        )
        self.assertEqual(global_packet["repo_profile_name"], "default")
        self.assertEqual(orchestrator["repo_profile_name"], "default")
        self.assertEqual(self.build_result["repo_profile_name"], "default")
        self.assertEqual(Path(self.context["repo_profile_path"]).parts[-3:], ("profiles", "default", "profile.json"))
        self.assertEqual(Path(global_packet["repo_profile_path"]).parts[-3:], ("profiles", "default", "profile.json"))
        self.assertEqual(Path(orchestrator["repo_profile_path"]).parts[-3:], ("profiles", "default", "profile.json"))
        self.assertEqual(Path(self.build_result["repo_profile_path"]).parts[-3:], ("profiles", "default", "profile.json"))

    def test_analysis_ref_metadata_is_propagated_to_context_packets_and_build_result(self) -> None:
        analysis_ref = self.context["analysis_ref"]
        self.assertEqual(analysis_ref["policy"], wl.DEFAULT_ANALYSIS_REF_POLICY)
        self.assertEqual(analysis_ref["selected_branch"], "master")
        self.assertEqual(analysis_ref["selected_sha"], "abcdef123456")
        self.assertEqual(
            self.packets["global_packet.json"]["analysis_ref"]["selected_sha"],
            "abcdef123456",
        )
        self.assertEqual(
            self.packets["mapping_packet.json"]["analysis_ref"]["selected_branch"],
            "master",
        )
        self.assertEqual(
            self.packets["orchestrator.json"]["analysis_ref"]["policy"],
            wl.DEFAULT_ANALYSIS_REF_POLICY,
        )
        self.assertEqual(
            self.build_result["analysis_ref_selected_sha"],
            "abcdef123456",
        )

    def test_domain_overlay_uses_normalized_builder_keys(self) -> None:
        overlay = self.packets["global_packet.json"]["domain_overlay"]
        self.assertEqual(
            overlay["output_inclusion_rules"],
            {
                "standalone": [wl.ACTUAL_INCIDENT, wl.BLOCKER_OR_RISK],
                "reference_only": [wl.ARTIFACT_ONLY],
                "excluded": [wl.IGNORE],
            },
        )

    def test_changes_packet_separates_shipped_changes_from_review_followups(self) -> None:
        changes_packet = self.packets["changes_packet.json"]
        self.assertEqual([candidate["source_id"] for candidate in changes_packet["candidates"]], ["#97", "#101"])
        self.assertEqual(changes_packet["footer"]["candidate_ids"], changes_packet["candidate_ids"])
        self.assertEqual(changes_packet["candidate_template"]["field_bundles"], wl.CANDIDATE_FIELD_BUNDLES)
        for candidate in changes_packet["candidates"]:
            self.assertIn("shipped_change_bullets", candidate)
            self.assertIn("review_followups", candidate)
            self.assertIsInstance(candidate["shipped_change_bullets"], list)
            self.assertIsInstance(candidate["review_followups"], list)

    def test_orchestrator_exposes_packet_worker_map_and_optional_workers(self) -> None:
        orchestrator = self.packets["orchestrator.json"]
        self.assertEqual(orchestrator["orchestrator_profile"], "standard")
        self.assertTrue(orchestrator["decision_ready_packets"])
        self.assertEqual(orchestrator["worker_return_contract"], "classification-oriented")
        self.assertEqual(orchestrator["worker_output_shape"], "hierarchical")
        self.assertEqual(orchestrator["packet_worker_map"], wl.PACKET_WORKER_MAP)
        self.assertIn("common_path_contract", orchestrator)
        self.assertNotIn("estimated_packet_tokens", orchestrator)
        self.assertNotIn("packet_size_bytes", orchestrator)
        self.assertEqual(
            [worker["agent_type"] for worker in orchestrator["recommended_workers"]],
            ["repo_mapper", "large_diff_auditor", "log_triager", "evidence_summarizer"],
        )
        self.assertEqual(orchestrator["optional_workers"], ["docs_verifier"])
        self.assertEqual(orchestrator["worker_selection_guidance"]["routing_authority"], "packet_worker_map")

    def test_build_artifacts_emit_eval_side_packet_metrics_and_result(self) -> None:
        self.assertEqual(self.packet_metrics["packet_count"], len(smoke.EXPECTED_PACKET_FILES))
        self.assertGreater(self.packet_metrics["estimated_delegation_savings"], 0)
        self.assertLess(self.packet_metrics["estimated_packet_tokens"], self.packet_metrics["estimated_local_only_tokens"])
        self.assertEqual(self.build_result["repo_profile_name"], "default")
        self.assertEqual(self.build_result["packet_metrics"]["packet_count"], self.packet_metrics["packet_count"])
        self.assertEqual(self.build_result["selected_packets"], ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"])
        self.assertIn("candidate_counts_by_proposed_classification", self.build_result)
        self.assertIn("raw_reread_reason_counts", self.build_result)

    def test_build_wrapper_writes_packet_metrics_and_build_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            context_path = temp_path / "context.json"
            lint_path = temp_path / "lint.json"
            output_dir = temp_path / "packets"
            result_path = temp_path / "build-result.json"
            context_path.write_text(json.dumps(self.context, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            lint_path.write_text(json.dumps(self.lint, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

            with mock.patch.object(
                sys,
                "argv",
                [
                    "build_weekly_update_packets.py",
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
                exit_code = build_packets_script.main()

            self.assertEqual(exit_code, 0)
            packet_metrics = json.loads((output_dir / "packet_metrics.json").read_text(encoding="utf-8"))
            build_result = json.loads(result_path.read_text(encoding="utf-8"))
            orchestrator = json.loads((output_dir / "orchestrator.json").read_text(encoding="utf-8"))
            self.assertEqual(packet_metrics["packet_count"], len(smoke.EXPECTED_PACKET_FILES))
            self.assertEqual(build_result["packet_metrics"]["estimated_packet_tokens"], packet_metrics["estimated_packet_tokens"])
            self.assertEqual(orchestrator["orchestrator_profile"], "standard")
            self.assertEqual(orchestrator["repo_profile_name"], "default")
            self.assertEqual(build_result["repo_profile_name"], "default")
            self.assertNotIn("estimated_packet_tokens", orchestrator)

    def test_packet_membership_is_consistent_across_packets(self) -> None:
        mapping_index = {item["candidate_id"]: item for item in self.packets["mapping_packet.json"]["candidate_inventory_index"]}
        for candidate in self.packets["incidents_packet.json"]["candidates"]:
            self.assertIn("incidents_packet", mapping_index[candidate["candidate_id"]]["packet_membership"])
        for candidate in self.packets["risks_packet.json"]["candidates"]:
            self.assertIn("risks_packet", mapping_index[candidate["candidate_id"]]["packet_membership"])

    def test_artifact_only_candidates_do_not_surface_as_blockers(self) -> None:
        risk_candidates = {candidate["candidate_id"]: candidate for candidate in self.packets["risks_packet.json"]["candidates"]}
        self.assertIn("issue-103", risk_candidates)
        blocker_ids = [candidate_id for candidate_id, candidate in risk_candidates.items() if candidate["proposed_classification"] != wl.ARTIFACT_ONLY]
        self.assertNotIn("issue-103", blocker_ids)

    def test_apply_gating_blocks_low_confidence_and_raw_reread_exceptions(self) -> None:
        ready = dict(self.ready_plan)
        ready["context_id"] = self.context["context_id"]
        ready["context_fingerprint"] = self.context["context_fingerprint"]
        reread = dict(self.reread_plan)
        reread["context_id"] = self.context["context_id"]
        reread["context_fingerprint"] = self.context["context_fingerprint"]
        reread["unresolved_raw_reread_candidate_ids"] = ["issue-111"]
        low = dict(self.low_plan)
        low["context_id"] = self.context["context_id"]
        low["context_fingerprint"] = self.context["context_fingerprint"]
        with tempfile.TemporaryDirectory() as temp_dir:
            ready_result = wl.apply_plan(context=self.context, plan=ready, state_file=str(Path(temp_dir) / "ready.json"), dry_run=False)
            low_result = wl.apply_plan(context=self.context, plan=low, state_file=str(Path(temp_dir) / "low.json"), dry_run=False)
            reread_result = wl.apply_plan(context=self.context, plan=reread, state_file=str(Path(temp_dir) / "reread.json"), dry_run=False)
        self.assertTrue(ready_result["marker_update_written"])
        self.assertFalse(low_result["marker_update_written"])
        self.assertFalse(reread_result["marker_update_written"])

    def test_final_output_sections_follow_the_locked_order(self) -> None:
        self.assertEqual(wl.OUTPUT_SECTIONS, ["PRs", "Rollouts", "Incidents", "Reviews", "Blockers / Risks", "Evidence reviewed"])

    def test_agent_interface_describes_top_level_orchestrator(self) -> None:
        agent_yaml = (Path(__file__).resolve().parents[1] / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('short_description: "Top-level packet-driven weekly update orchestrator with profile-aware repo conventions"', agent_yaml)
        self.assertIn("Use $weekly-update to collect context, build packets, optionally delegate", agent_yaml)
        self.assertNotIn("ExampleProduct", agent_yaml)
        self.assertNotIn("worker-only packet analyst", agent_yaml)

    def test_retained_builder_assets_exist(self) -> None:
        skill_dir = Path(__file__).resolve().parents[1]
        self.assertTrue((skill_dir / "builder-spec.json").is_file())
        self.assertTrue((skill_dir / "migration-worksheet.md").is_file())
        self.assertTrue((skill_dir / "references" / "core-contract.md").is_file())
        self.assertTrue((skill_dir / "profiles" / "default" / "profile.json").is_file())

    def test_smoke_script_targets_all_expected_packets(self) -> None:
        self.assertEqual(
            smoke.EXPECTED_PACKET_FILES,
            (
                "orchestrator.json",
                "global_packet.json",
                "mapping_packet.json",
                "changes_packet.json",
                "incidents_packet.json",
                "risks_packet.json",
            ),
        )
        self.assertEqual(len(smoke.EXPECTED_PACKET_FILES), 6)
        self.assertEqual(smoke.EXPECTED_EVAL_FILES, ("packet_metrics.json",))

    def test_smoke_plan_disables_marker_updates(self) -> None:
        plan = smoke.build_minimal_plan({"context_id": "ctx-1", "context_fingerprint": "fp-1"})
        self.assertEqual(plan["context_id"], "ctx-1")
        self.assertEqual(plan["context_fingerprint"], "fp-1")
        self.assertEqual(plan["overall_confidence"], "high")
        self.assertEqual(plan["stop_reasons"], [])
        self.assertFalse(plan["allow_marker_update"])
        self.assertEqual(plan["selected_packets"], ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"])
        self.assertEqual(list(plan["sections"].keys()), wl.OUTPUT_SECTIONS)


if __name__ == "__main__":
    unittest.main()
