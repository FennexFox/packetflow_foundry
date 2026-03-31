#!/usr/bin/env python3
"""Build focused packets for gh-create-pr from collected context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import lint_pr_create as lint_tools
import pr_create_contract as contract


def load_json(path: Path) -> dict[str, Any]:
    return contract.load_json(path)


def parse_diff_totals(diff_stat: str | None) -> dict[str, int]:
    return lint_tools.parse_diff_totals(diff_stat)


def active_groups(group_summary: dict[str, dict[str, object]]) -> list[str]:
    ordered_names = ("runtime", "automation", "docs", "tests", "config", "other")
    return [name for name in ordered_names if (group_summary.get(name) or {}).get("count", 0) > 0]


def determine_review_mode(context: dict[str, Any], lint_report: dict[str, Any]) -> tuple[str, int]:
    groups = context.get("changed_file_groups") or {}
    file_count = len(list(context.get("changed_files") or []))
    group_count = len(active_groups(groups))
    diff_totals = parse_diff_totals(context.get("diff_stat"))
    override_signals = lint_report.get("findings", {}).get("override_signals", {})

    if file_count <= contract.SMALL_FILE_LIMIT and group_count <= contract.SMALL_GROUP_LIMIT:
        review_mode = "local-only"
        worker_count = 0
    elif file_count > contract.MEDIUM_FILE_LIMIT or group_count >= contract.LARGE_GROUP_LIMIT:
        review_mode = "broad-delegation"
        worker_count = 3
    else:
        review_mode = "targeted-delegation"
        worker_count = 2

    if any(bool(value) for value in override_signals.values()):
        if review_mode == "local-only":
            review_mode = "targeted-delegation"
            worker_count = 2
        elif review_mode == "targeted-delegation":
            review_mode = "broad-delegation"
            worker_count = 4

    if review_mode == "broad-delegation" and diff_totals.get("churn", 0) >= 3000:
        worker_count = 4
    return review_mode, worker_count


def build_rules_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    snippets = context.get("instruction_snippets") or {}
    template_selection = context.get("template_selection") or {}
    return {
        "purpose": "Authoritative hard-rule source for PR title/body drafting.",
        "authoritative": True,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "title_pattern": "<type>(<scope>): <summary>",
        "template_status": template_selection.get("status"),
        "template_path": template_selection.get("selected_path"),
        "template_fingerprint": template_selection.get("fingerprint"),
        "required_sections": list(context.get("expected_template_sections") or []),
        "strict_claim_gates": [
            "issue references must match process-packet issue hints",
            "positive testing claims require exact commands from testing packet evidence",
            "`no behavior change` is only supportable when runtime packet is empty",
            "restart/reload, migration, rollout, and compatibility claims are blocked by default",
        ],
        "repo_instruction_excerpts": {
            "pull_request_title_rules_excerpt": snippets.get("pull_request_title_rules_excerpt"),
            "pull_request_template_sections": snippets.get("pull_request_template_sections"),
            "commit_types_excerpt": snippets.get("commit_types_excerpt"),
        },
        "rule_files": context.get("rule_files", {}),
        "drafting_basis": drafting_basis,
    }


def build_global_packet(
    context: dict[str, Any],
    *,
    review_mode: str,
    focused_packet_hint: str | None,
    lint_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "purpose": "Shared runtime context for local orchestration and narrow delegated packet analysis.",
        "workflow_family": contract.WORKFLOW_FAMILY,
        "archetype": contract.ARCHETYPE,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "repo_profile": context.get("repo_profile"),
        "repo_slug": context.get("repo_slug"),
        "head_ref": context.get("resolved_head"),
        "base_ref": context.get("resolved_base"),
        "review_mode": review_mode,
        "authority_order": [
            "rules_packet.json",
            "synthesis_packet.json",
            "focused packet evidence",
            "explicit local reread only for stale or disputed signals",
        ],
        "packet_worker_map": contract.PACKET_WORKER_MAP,
        "preferred_worker_families": contract.PREFERRED_WORKER_FAMILIES,
        "worker_selection_guidance": contract.WORKER_SELECTION_GUIDANCE,
        "focused_packet_hint": focused_packet_hint,
        "review_overrides": lint_report.get("findings", {}).get("override_signals", {}),
        "duplicate_hint": context.get("duplicate_check_hint"),
        "local_gate_reminders": [
            "Keep final title/body synthesis local.",
            "Treat rules_packet.json as the only authority source for template, title, and claim gates.",
            "Do not rely on collector duplicate hints for mutation safety; validator and apply re-check GitHub state.",
            "Treat raw reread as exceptional, not compensatory.",
        ],
    }


def build_runtime_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    runtime_group = groups.get("runtime") or {"count": 0, "sample_files": []}
    return {
        "purpose": "Runtime behavior and shipped-impact evidence slice.",
        "changed_files": list(runtime_group.get("sample_files", [])),
        "changed_file_count": runtime_group.get("count", 0),
        "diff_stat": context.get("diff_stat"),
        "supported_claims": [
            item for item in drafting_basis.get("supported_claims", []) if item.get("cluster") == "runtime"
        ],
        "runtime_packet_empty": int(runtime_group.get("count", 0)) == 0,
        "no_behavior_change_supportable": int(runtime_group.get("count", 0)) == 0,
    }


def build_process_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    process_files: list[str] = []
    for group_name in ("automation", "docs", "config"):
        process_files.extend(list((groups.get(group_name) or {}).get("sample_files", [])))
    return {
        "purpose": "Workflow, template, branch, and duplicate-check evidence slice.",
        "repo_slug": context.get("repo_slug"),
        "current_branch": context.get("current_branch"),
        "head_ref": context.get("resolved_head"),
        "base_ref": context.get("resolved_base"),
        "local_head_oid": context.get("local_head_oid"),
        "remote_head_oid": context.get("remote_head_oid"),
        "changed_files": process_files,
        "recent_commit_subjects": list(context.get("recent_commit_subjects") or []),
        "issue_reference_hints": context.get("issue_reference_hints"),
        "duplicate_check_hint": context.get("duplicate_check_hint"),
        "create_options": context.get("create_options"),
        "supported_claims": [
            item for item in drafting_basis.get("supported_claims", []) if item.get("cluster") == "process"
        ],
    }


def build_testing_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    testing_group = groups.get("tests") or {"count": 0, "sample_files": []}
    return {
        "purpose": "Testing evidence and claim-limit slice.",
        "changed_test_files": list(testing_group.get("sample_files", [])),
        "changed_test_file_count": testing_group.get("count", 0),
        "testing_signal_candidates": context.get("testing_signal_candidates"),
        "positive_testing_claims_supported": False,
        "supported_claims": [
            item for item in drafting_basis.get("supported_claims", []) if item.get("cluster") == "testing"
        ],
    }


def build_synthesis_packet(
    context: dict[str, Any],
    *,
    review_mode: str,
    lint_report: dict[str, Any],
    drafting_basis: dict[str, Any],
) -> dict[str, Any]:
    return {
        "purpose": "Run-specific drafting decision packet for local final PR title/body synthesis.",
        "local_only": True,
        "review_mode": review_mode,
        "template_status": context.get("template_selection", {}).get("status"),
        "duplicate_hint_status": context.get("duplicate_check_hint", {}).get("status"),
        "active_rule_gates": list(drafting_basis.get("active_rule_gates", [])),
        "required_sections_status": drafting_basis.get("required_sections_status"),
        "issue_reference_hints": drafting_basis.get("issue_reference_hints"),
        "testing_evidence_status": drafting_basis.get("testing_evidence_status"),
        "coverage_gaps": list(drafting_basis.get("coverage_gaps", [])),
        "focused_packet_hint": drafting_basis.get("focused_packet_hint"),
        "lint_errors": list(lint_report.get("findings", {}).get("errors", [])),
        "lint_warnings": list(lint_report.get("findings", {}).get("warnings", [])),
        "common_path_contract": {
            "required_packets": contract.COMMON_PATH_REQUIRED_PACKETS,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "sufficient_for_local_final_drafting": True,
            "packet_insufficiency_is_failure": True,
        },
    }


def raw_local_bundle(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "context": context,
        "lint_findings": lint_report.get("findings"),
        "drafting_basis": lint_report.get("drafting_basis"),
    }


def build_worker_specs(
    *,
    review_mode: str,
    worker_count: int,
    runtime_active: bool,
    process_active: bool,
    testing_relevant: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recommended: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []

    delegated_packets: list[tuple[str, str, str, str, str | None]] = []
    if runtime_active:
        delegated_packets.append(
            (
                "runtime",
                "packet_explorer",
                "runtime_packet.json",
                "Summarize shipped runtime behavior and whether `no behavior change` is supportable.",
                "gpt-5.4-mini",
            )
        )
    if process_active:
        delegated_packets.append(
            (
                "process",
                "packet_explorer",
                "process_packet.json",
                "Summarize branch/base/template and issue-hint evidence worth mentioning.",
                "gpt-5.4-mini",
            )
        )
    if testing_relevant:
        delegated_packets.append(
            (
                "testing",
                "evidence_summarizer",
                "testing_packet.json",
                "Summarize which testing claims remain blocked or supportable.",
                None,
            )
        )

    for name, agent_type, packet_name, responsibility, model in delegated_packets[:worker_count]:
        worker: dict[str, Any] = {
            "name": name,
            "agent_type": agent_type,
            "packets": ["global_packet.json", packet_name],
            "responsibility": responsibility,
            "reasoning_effort": "medium" if agent_type != "evidence_summarizer" else "low",
            "return_contract": contract.STANDARD_RETURN_CONTRACT,
        }
        if model:
            worker["model"] = model
        recommended.append(worker)

    optional.append(
        {
            "name": "rules-cross-check",
            "agent_type": "docs_verifier",
            "packets": ["global_packet.json", "rules_packet.json"],
            "responsibility": "Cross-check title, template, or claim gates when local inspection still leaves ambiguity.",
            "reasoning_effort": "medium",
            "return_contract": contract.STANDARD_RETURN_CONTRACT,
        }
    )
    optional.append(
        {
            "name": "risk-cross-check",
            "agent_type": "large_diff_auditor",
            "packets": ["global_packet.json", "runtime_packet.json"],
            "responsibility": "Use only for broad delegation or unusually risky diffs before mutation.",
            "reasoning_effort": "medium",
            "return_contract": contract.STANDARD_RETURN_CONTRACT,
        }
    )
    return recommended, optional


def build_packet_payloads(context: dict[str, Any], lint_report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    groups = context.get("changed_file_groups") or {}
    review_mode, worker_count = determine_review_mode(context, lint_report)
    drafting_basis = lint_report.get("drafting_basis") or {}
    runtime_active = int((groups.get("runtime") or {}).get("count", 0)) > 0
    process_active = any(int((groups.get(name) or {}).get("count", 0)) > 0 for name in ("automation", "docs", "config"))
    testing_relevant = int((groups.get("tests") or {}).get("count", 0)) > 0
    focused_hint = drafting_basis.get("focused_packet_hint")

    packet_payloads: dict[str, Any] = {
        "global_packet.json": build_global_packet(
            context,
            review_mode=review_mode,
            focused_packet_hint=focused_hint,
            lint_report=lint_report,
        ),
        "rules_packet.json": build_rules_packet(context, drafting_basis),
        "testing_packet.json": build_testing_packet(context, drafting_basis),
        "synthesis_packet.json": build_synthesis_packet(
            context,
            review_mode=review_mode,
            lint_report=lint_report,
            drafting_basis=drafting_basis,
        ),
    }
    if runtime_active:
        packet_payloads["runtime_packet.json"] = build_runtime_packet(context, drafting_basis)
    if process_active:
        packet_payloads["process_packet.json"] = build_process_packet(context, drafting_basis)

    common_path_packets = ["rules_packet.json", "synthesis_packet.json"]
    if focused_hint:
        common_path_packets.append(focused_hint)
    packet_metrics = contract.compute_packet_metrics(
        packet_payloads,
        common_path_packet_names=common_path_packets,
        raw_local_payload=raw_local_bundle(context, lint_report),
    )
    packet_metrics["common_path_packets"] = common_path_packets
    packet_metrics["common_path_sufficient"] = True
    packet_metrics["raw_reread_count"] = 0
    packet_metrics["packet_insufficiency_is_failure"] = True

    recommended_workers, optional_workers = build_worker_specs(
        review_mode=review_mode,
        worker_count=worker_count,
        runtime_active=runtime_active,
        process_active=process_active,
        testing_relevant=testing_relevant,
    )
    packet_files = list(packet_payloads.keys()) + ["orchestrator.json"]
    build_result = {
        "review_mode": review_mode,
        "recommended_worker_count": len(recommended_workers),
        "optional_worker_count": len(optional_workers),
        "packet_files": packet_files,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "shared_local_packet": contract.SHARED_LOCAL_PACKET,
        "template_status": context.get("template_selection", {}).get("status"),
        "duplicate_hint_status": context.get("duplicate_check_hint", {}).get("status"),
        "packet_metrics": packet_metrics,
    }
    orchestrator = {
        "workflow_family": contract.WORKFLOW_FAMILY,
        "archetype": contract.ARCHETYPE,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "review_mode": review_mode,
        "recommended_worker_count": len(recommended_workers),
        "optional_worker_count": len(optional_workers),
        "shared_packet": "global_packet.json",
        "shared_local_packet": contract.SHARED_LOCAL_PACKET,
        "decision_ready_packets": contract.DECISION_READY_PACKETS,
        "worker_return_contract": contract.WORKER_RETURN_CONTRACT,
        "worker_output_shape": contract.WORKER_OUTPUT_SHAPE,
        "preferred_worker_families": contract.PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": contract.PACKET_WORKER_MAP,
        "worker_selection_guidance": contract.WORKER_SELECTION_GUIDANCE,
        "common_path_contract": {
            "required_packets": contract.COMMON_PATH_REQUIRED_PACKETS,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "packet_insufficiency_is_failure": True,
        },
        "local_responsibilities": [
            "Read rules_packet.json locally before drafting title/body.",
            "Keep final PR draft synthesis local.",
            "Validate against live head/template/duplicate state before any mutation.",
            "Run apply_pr_create.py only from validator-normalized output.",
        ],
        "packet_files": packet_files,
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
    }
    packet_payloads["orchestrator.json"] = orchestrator
    packet_payloads["packet_metrics.json"] = packet_metrics
    return packet_payloads, build_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Path to JSON from collect_pr_create_context.py.")
    parser.add_argument("--lint", required=True, help="Path to JSON from lint_pr_create.py.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated packets.")
    parser.add_argument("--result-output", help="Optional output path for build result JSON.")
    args = parser.parse_args()

    context = load_json(Path(args.context))
    lint_report = load_json(Path(args.lint))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    packets, build_result = build_packet_payloads(context, lint_report)
    for file_name, payload in packets.items():
        contract.write_json(output_dir / file_name, payload)
    if args.result_output:
        contract.write_json(Path(args.result_output), build_result)

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "review_mode": build_result["review_mode"],
                "packet_files": build_result["packet_files"],
                "recommended_worker_count": build_result["recommended_worker_count"],
                "packet_metrics_file": str(output_dir / "packet_metrics.json"),
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
