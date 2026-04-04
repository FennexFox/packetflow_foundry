from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import lint_pr_writeup as lint_tools
import pr_writeup_contract as contract


SMALL_FILE_LIMIT = contract.SMALL_FILE_LIMIT
MEDIUM_FILE_LIMIT = contract.MEDIUM_FILE_LIMIT
SMALL_GROUP_LIMIT = contract.SMALL_GROUP_LIMIT
LARGE_GROUP_LIMIT = contract.LARGE_GROUP_LIMIT
LARGE_CHURN_LIMIT = 1500
VERY_LARGE_CHURN_LIMIT = 3000
MEANINGFUL_GENERATED_FILE_MIN_COUNT = 3
MEANINGFUL_GENERATED_FILE_MIN_RATIO = 0.2
GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)

STANDARD_RETURN_CONTRACT = contract.STANDARD_RETURN_CONTRACT
QA_REQUIRED_INPUTS = contract.QA_REQUIRED_INPUTS
QA_RETURN_CONTRACT = contract.QA_RETURN_CONTRACT
PREFERRED_WORKER_FAMILIES = contract.PREFERRED_WORKER_FAMILIES
PACKET_WORKER_MAP = contract.PACKET_WORKER_MAP
WORKER_SELECTION_GUIDANCE = contract.WORKER_SELECTION_GUIDANCE
DELEGATION_SAVINGS_FLOOR = 250


def load_json(path: Path) -> dict[str, Any]:
    return contract.load_json(path)


def active_groups(group_summary: dict[str, dict[str, object]]) -> list[str]:
    ordered_names = ("runtime", "automation", "docs", "tests", "config", "other")
    return [name for name in ordered_names if (group_summary.get(name) or {}).get("count", 0) > 0]


def parse_diff_totals(diff_stat: str | None) -> dict[str, int] | None:
    if not diff_stat:
        return None
    last_line = diff_stat.strip().splitlines()[-1]
    files_match = re.search(r"(?P<files>\d+) files? changed", last_line)
    insertions_match = re.search(r"(?P<insertions>\d+) insertions?\(\+\)", last_line)
    deletions_match = re.search(r"(?P<deletions>\d+) deletions?\(-\)", last_line)
    if not files_match and not insertions_match and not deletions_match:
        return None
    files_changed = int(files_match.group("files")) if files_match else 0
    insertions = int(insertions_match.group("insertions")) if insertions_match else 0
    deletions = int(deletions_match.group("deletions")) if deletions_match else 0
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "churn": insertions + deletions,
    }


def is_generated_file(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return any(pattern.search(lowered) for pattern in GENERATED_FILE_PATTERNS)


def core_area_for_path(path: str) -> str | None:
    lowered = path.replace("\\", "/").lower()
    runtime_prefixes = (
        "src/",
        "lib/",
        "app/",
        "server/",
        "client/",
    )
    runtime_files: set[str] = set()
    process_prefixes = (
        ".github/workflows/",
        ".github/scripts/",
        ".github/issue_template/",
        ".github/instructions/",
    )
    process_files = {
        ".github/pull_request_template.md",
        "contributing.md",
        "maintaining.md",
    }
    config_suffixes = (".csproj", ".props", ".targets")
    config_files = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
    }
    if lowered.startswith(runtime_prefixes) or lowered in runtime_files:
        return "runtime"
    if lowered.startswith(process_prefixes) or lowered in process_files:
        return "process"
    if lowered.endswith(config_suffixes) or lowered in config_files:
        return "config"
    return None


def testing_findings(findings: dict[str, Any]) -> list[str]:
    messages = list(findings.get("errors", [])) + list(findings.get("warnings", []))
    return [
        message
        for message in messages
        if any(token in message.lower() for token in ("testing", "tested", "command", "verification"))
    ]


def full_rewrite_likely(body: str, findings: dict[str, Any]) -> bool:
    if not body.strip():
        return True
    rewrite_signals = (
        "missing template sections",
        "template order",
        "placeholder",
        "template guidance text",
        "blank nested bullet",
        "empty bullet",
    )
    for message in findings.get("errors", []):
        lowered = message.lower()
        if any(signal in lowered for signal in rewrite_signals):
            return True
    return False


def determine_baseline_review_mode(
    *,
    file_count: int,
    group_count: int,
    diff_totals: dict[str, int] | None,
    runtime_active: bool,
    process_active: bool,
    testing_relevant: bool,
) -> tuple[str, int]:
    churn = (diff_totals or {}).get("churn", 0)
    if file_count <= SMALL_FILE_LIMIT and group_count <= SMALL_GROUP_LIMIT:
        review_mode = "local-only"
    elif file_count > MEDIUM_FILE_LIMIT or group_count >= LARGE_GROUP_LIMIT:
        review_mode = "broad-delegation"
    else:
        review_mode = "targeted-delegation"

    if review_mode == "local-only":
        return review_mode, 0
    if review_mode == "targeted-delegation":
        return review_mode, 2

    worker_count = 3
    if (
        (runtime_active and process_active and testing_relevant)
        or churn >= VERY_LARGE_CHURN_LIMIT
        or group_count >= 5
    ):
        worker_count = 4
    return review_mode, worker_count


def apply_override_adjustment(
    *,
    review_mode: str,
    worker_count: int,
    group_count: int,
    diff_totals: dict[str, int] | None,
    runtime_active: bool,
    process_active: bool,
    testing_relevant: bool,
    override_signals: list[dict[str, object]],
) -> tuple[str, int, list[str]]:
    adjustments: list[str] = []
    churn = (diff_totals or {}).get("churn", 0)
    if override_signals and review_mode == "local-only":
        review_mode = "targeted-delegation"
        worker_count = 2
        adjustments.append("override_signal")
    elif override_signals and review_mode == "targeted-delegation":
        review_mode = "broad-delegation"
        worker_count = 3
        adjustments.append("override_signal")
    elif override_signals:
        adjustments.append("override_signal")

    if review_mode == "local-only":
        return review_mode, 0, adjustments
    if review_mode == "targeted-delegation":
        return review_mode, 2, adjustments

    if (
        (runtime_active and process_active and testing_relevant)
        or churn >= VERY_LARGE_CHURN_LIMIT
        or group_count >= 5
        or bool(override_signals)
    ):
        worker_count = 4
    return review_mode, worker_count, adjustments


def maybe_apply_delegation_savings_floor(
    review_mode: str,
    worker_count: int,
    packet_metrics: dict[str, Any],
    adjustments: list[str],
) -> tuple[str, int, list[str]]:
    estimated_savings = int(packet_metrics.get("estimated_delegation_savings", 0) or 0)
    if (
        review_mode == "local-only"
        and estimated_savings >= DELEGATION_SAVINGS_FLOOR
        and "delegation_savings_floor" not in adjustments
    ):
        return "targeted-delegation", max(worker_count, 2), [*adjustments, "delegation_savings_floor"]
    return review_mode, worker_count, adjustments


def focus_packet_name(groups: dict[str, dict[str, Any]], findings: dict[str, Any]) -> str | None:
    testing_group = (groups.get("tests") or {}).get("count", 0)
    runtime_group = (groups.get("runtime") or {}).get("count", 0)
    process_group = sum((groups.get(name) or {}).get("count", 0) for name in ("automation", "docs", "config"))
    if testing_group or testing_findings(findings):
        return "testing_packet.json"
    if runtime_group:
        return "runtime_packet.json"
    if process_group:
        return "process_packet.json"
    return None


def default_review_overrides(
    *,
    context: dict[str, Any],
    diff_totals: dict[str, int] | None,
    core_areas_touched: list[str],
    generated_file_count: int,
    generated_file_ratio: float,
) -> list[dict[str, str]]:
    changed_files = list(context.get("changed_files", []))
    overrides: list[dict[str, str]] = []
    if (diff_totals or {}).get("churn", 0) >= LARGE_CHURN_LIMIT:
        overrides.append(
            {
                "reason": "diff_stat_threshold",
                "detail": f"Diff churn reached {(diff_totals or {}).get('churn', 0)} lines (threshold {LARGE_CHURN_LIMIT}).",
            }
        )
    if len(core_areas_touched) >= 2:
        overrides.append(
            {
                "reason": "core_files_across_groups",
                "detail": "Core runtime/config/process files were touched across multiple groups: "
                + ", ".join(core_areas_touched),
            }
        )
    if (
        generated_file_count >= MEANINGFUL_GENERATED_FILE_MIN_COUNT
        and MEANINGFUL_GENERATED_FILE_MIN_RATIO <= generated_file_ratio < 0.5
    ):
        overrides.append(
            {
                "reason": "generated_files_meaningful_minor_slice",
                "detail": "Generated files are a meaningful minority slice "
                f"({generated_file_count}/{len(changed_files)}); increase review depth so hand-authored changes are not crowded out.",
            }
        )
    return overrides


def build_rules_packet(context: dict[str, Any]) -> dict[str, Any]:
    snippets = context.get("instruction_snippets") or {}
    return {
        "purpose": "Authoritative hard-rule source for PR title/body drafting.",
        "authoritative": True,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "title_pattern": "<type>(<scope>): <summary>",
        "required_sections": list(context.get("expected_template_sections") or []),
        "disallowed_claim_categories": [
            "unsupported testing or manual verification claims",
            "unsupported issue references",
            "unsupported defaults or threshold claims",
            "unsupported reload/restart claims",
            "unsupported migration or compatibility claims",
        ],
        "issue_ref_policy": "Only cite linked issues that are present in PR metadata or already verifiable in the repo state.",
        "repo_instruction_excerpts": {
            "pull_request_title_rules_excerpt": snippets.get("pull_request_title_rules_excerpt"),
            "pull_request_template_sections": snippets.get("pull_request_template_sections"),
            "commit_types_excerpt": snippets.get("commit_types_excerpt"),
        },
        "rule_files": context.get("rule_files", {}),
        "local_gate": [
            "Read this packet locally before drafting any replacement title/body.",
            "Treat this packet as the authority source for hard rules; synthesis_packet only carries rule application results for this PR.",
            "Re-check the final draft against this packet before validation.",
        ],
    }


def build_global_packet(
    context: dict[str, Any],
    *,
    review_mode: str,
    override_signals: list[dict[str, str]],
    focused_packet_hint: str | None,
) -> dict[str, Any]:
    pr = context.get("pr") or {}
    return {
        "purpose": "Shared runtime context for local orchestration and narrow delegated packet analysis.",
        "workflow_family": contract.WORKFLOW_FAMILY,
        "archetype": contract.ARCHETYPE,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "repo_profile": context.get("repo_profile"),
        "pr": {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
            "linked_issues": pr.get("closingIssuesReferences") or [],
        },
        "review_mode": review_mode,
        "authority_order": [
            "rules_packet.json",
            "synthesis_packet.json",
            "focused packet evidence",
            "explicit local reread only for allowed reasons",
        ],
        "packet_worker_map": contract.PACKET_WORKER_MAP,
        "preferred_worker_families": contract.PREFERRED_WORKER_FAMILIES,
        "worker_selection_guidance": contract.WORKER_SELECTION_GUIDANCE,
        "raw_reread_policy": {
            "allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
            "packet_insufficiency_is_failure": True,
            "common_path_expected": True,
        },
        "qa_policy": contract.QA_TRIGGER_POLICY,
        "focused_packet_hint": focused_packet_hint,
        "review_overrides": override_signals,
        "local_gate_reminders": [
            "Keep final title/body synthesis local.",
            "Use rules_packet.json as the only authority source for hard constraints.",
            "Use synthesis_packet.json as the run-specific decision packet.",
            "Treat raw reread as exceptional, not compensatory.",
        ],
    }


def build_runtime_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    runtime_group = groups.get("runtime") or {"count": 0, "sample_files": []}
    return {
        "purpose": "Runtime behavior and shipped-impact evidence slice.",
        "ownership_summary": "Use this packet for runtime behavior, settings impact, reload/restart risk, and runtime claim anchoring.",
        "github_evidence_slice": {
            "changed_files": list(runtime_group.get("sample_files", [])),
            "diff_stat": context.get("diff_stat"),
        },
        "claim_basis": {
            "supported_claims": [
                item for item in drafting_basis.get("supported_claims", []) if item.get("cluster") == "runtime"
            ],
            "coverage_gaps": list(drafting_basis.get("coverage_gaps", [])),
        },
    }


def build_process_packet(context: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    selected_files: list[str] = []
    process_groups: dict[str, Any] = {}
    for group_name in ("automation", "docs", "config"):
        packet_group = groups.get(group_name) or {"count": 0, "sample_files": []}
        process_groups[group_name] = packet_group
        selected_files.extend(list(packet_group.get("sample_files", [])))
    return {
        "purpose": "Workflow, configuration, and documentation evidence slice.",
        "ownership_summary": "Use this packet for workflow/config/docs changes that influence PR wording or risk framing.",
        "github_evidence_slice": {
            "changed_files": selected_files,
            "diff_stat": context.get("diff_stat"),
        },
        "claim_basis": {
            "supported_claims": [
                item for item in drafting_basis.get("supported_claims", []) if item.get("cluster") == "process"
            ],
            "coverage_gaps": list(drafting_basis.get("coverage_gaps", [])),
            "process_groups": process_groups,
        },
    }


def build_testing_packet(context: dict[str, Any], lint_report: dict[str, Any], drafting_basis: dict[str, Any]) -> dict[str, Any]:
    groups = context.get("changed_file_groups") or {}
    findings = lint_report.get("findings", {})
    return {
        "purpose": "Testing-claims evidence slice.",
        "ownership_summary": "Use this packet for testing commands, unsupported verification risks, and coverage gaps tied to validation language.",
        "github_evidence_slice": {
            "changed_test_files": list((groups.get("tests") or {}).get("sample_files", [])),
            "diff_stat": context.get("diff_stat"),
        },
        "testing_evidence_status": drafting_basis.get("testing_evidence_status"),
        "lint_testing_findings": testing_findings(findings),
        "unsupported_claim_risks": list(drafting_basis.get("unsupported_claim_risks", [])),
    }


def build_synthesis_packet(
    context: dict[str, Any],
    *,
    review_mode: str,
    drafting_basis: dict[str, Any],
    focused_packet_hint: str | None,
) -> dict[str, Any]:
    rewrite_strategy = str(drafting_basis.get("rewrite_strategy") or "targeted-touch-up")
    qa_required, qa_reason = contract.should_require_qa(
        rewrite_strategy=rewrite_strategy,
        review_mode=review_mode,
    )
    return {
        "purpose": "Run-specific drafting decision packet for local final PR title/body synthesis.",
        "local_only": True,
        "rewrite_strategy": rewrite_strategy,
        "qa_required": qa_required,
        "qa_reason": qa_reason,
        "active_rule_gates": list(drafting_basis.get("active_rule_gates", [])),
        "current_failures": drafting_basis.get("current_failures", {}),
        "title_direction": drafting_basis.get("title_direction"),
        "required_sections_status": drafting_basis.get("required_sections_status"),
        "section_rewrite_requirements": list(drafting_basis.get("section_rewrite_requirements", [])),
        "supported_claims": list(drafting_basis.get("supported_claims", [])),
        "unsupported_claim_risks": list(drafting_basis.get("unsupported_claim_risks", [])),
        "testing_evidence_status": drafting_basis.get("testing_evidence_status"),
        "issue_ref_status": drafting_basis.get("issue_ref_status"),
        "coverage_gaps": list(drafting_basis.get("coverage_gaps", [])),
        "focused_packet_hint": focused_packet_hint,
        "common_path_contract": {
            "required_packets": contract.COMMON_PATH_REQUIRED_PACKETS,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "sufficient_for_local_final_drafting": True,
            "packet_insufficiency_is_failure": True,
            "raw_reread_allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
        },
        "pr_identity": {
            "number": context.get("pr", {}).get("number"),
            "url": context.get("pr", {}).get("url"),
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
                "Summarize shipped runtime behavior and settings impact.",
                "gpt-5.4-mini",
            )
        )
    if process_active:
        delegated_packets.append(
            (
                "process",
                "packet_explorer",
                "process_packet.json",
                "Summarize automation, docs, and config changes worth mentioning.",
                "gpt-5.4-mini",
            )
        )
    if testing_relevant:
        delegated_packets.append(
            (
                "testing",
                "evidence_summarizer",
                "testing_packet.json",
                "Check testing claims and unsupported evidence.",
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
            "responsibility": "Cross-check the local rules gate when the final draft still has template or claim ambiguity.",
            "reasoning_effort": "medium",
            "when": "Only add this pass when direct local inspection of rules_packet.json still leaves ambiguity.",
            "return_contract": contract.STANDARD_RETURN_CONTRACT,
        }
    )
    optional.append(
        {
            "name": "qa",
            "agent_type": "large_diff_auditor",
            "packets": ["global_packet.json", "rules_packet.json"],
            "responsibility": "Compare the drafted replacement title/body against the diff coverage and template requirements.",
            "reasoning_effort": "medium",
            "when": "Only add this pass when qa_required is true or a claim conflict explicitly triggers QA.",
            "required_inputs": contract.QA_REQUIRED_INPUTS,
            "return_contract": contract.QA_RETURN_CONTRACT,
        }
    )
    return recommended, optional


def build_packet_payloads(context: dict[str, Any], lint_report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    findings = lint_report.get("findings", {})
    body = str((context.get("pr") or {}).get("body") or "")
    groups = context.get("changed_file_groups") or {}
    active_group_names = active_groups(groups)
    changed_files = list(context.get("changed_files", []))
    file_count = len(changed_files)
    group_count = len(active_group_names)
    diff_totals = parse_diff_totals(context.get("diff_stat"))
    generated_file_count = sum(1 for path in changed_files if is_generated_file(path))
    generated_file_ratio = (generated_file_count / file_count) if file_count else 0.0
    core_areas_touched = sorted(
        {
            area
            for path in changed_files
            if (area := core_area_for_path(path)) is not None
        }
    )

    runtime_active = (groups.get("runtime") or {}).get("count", 0) > 0
    process_active = any((groups.get(name) or {}).get("count", 0) > 0 for name in ("automation", "docs", "config"))
    testing_relevant = (
        (groups.get("tests") or {}).get("count", 0) > 0
        or bool(testing_findings(findings))
        or bool(lint_tools.section_text(context, "Testing"))
    )

    override_signals = default_review_overrides(
        context=context,
        diff_totals=diff_totals,
        core_areas_touched=core_areas_touched,
        generated_file_count=generated_file_count,
        generated_file_ratio=generated_file_ratio,
    )
    review_mode_baseline, worker_count = determine_baseline_review_mode(
        file_count=file_count,
        group_count=group_count,
        diff_totals=diff_totals,
        runtime_active=runtime_active,
        process_active=process_active,
        testing_relevant=testing_relevant,
    )
    review_mode, worker_count, review_mode_adjustments = apply_override_adjustment(
        review_mode=review_mode_baseline,
        worker_count=worker_count,
        group_count=group_count,
        diff_totals=diff_totals,
        runtime_active=runtime_active,
        process_active=process_active,
        testing_relevant=testing_relevant,
        override_signals=override_signals,
    )

    drafting_basis = lint_report.get("drafting_basis") or lint_tools.build_drafting_basis(
        context,
        findings,
        rewrite_hint=full_rewrite_likely(body, findings),
    )
    focused_packet_hint = focus_packet_name(groups, findings)

    runtime_packet = build_runtime_packet(context, drafting_basis) if runtime_active else None
    process_packet = build_process_packet(context, drafting_basis) if process_active else None
    testing_packet = build_testing_packet(context, lint_report, drafting_basis)
    synthesis_packet = build_synthesis_packet(
        context,
        review_mode=review_mode,
        drafting_basis=drafting_basis,
        focused_packet_hint=focused_packet_hint,
    )
    common_path_packets = ["rules_packet.json", "synthesis_packet.json"]
    if focused_packet_hint:
        common_path_packets.append(focused_packet_hint)

    packet_payloads: dict[str, Any] = {
        "global_packet.json": build_global_packet(
            context,
            review_mode=review_mode,
            override_signals=override_signals,
            focused_packet_hint=focused_packet_hint,
        ),
        "rules_packet.json": build_rules_packet(context),
        "testing_packet.json": testing_packet,
        "synthesis_packet.json": synthesis_packet,
    }
    if runtime_packet is not None:
        packet_payloads["runtime_packet.json"] = runtime_packet
    if process_packet is not None:
        packet_payloads["process_packet.json"] = process_packet

    packet_metrics = contract.compute_packet_metrics(
        packet_payloads,
        common_path_packet_names=common_path_packets,
        raw_local_payload=raw_local_bundle(context, lint_report),
    )
    packet_metrics["raw_reread_allowed_reasons"] = contract.RAW_REREAD_ALLOWED_REASONS
    packet_metrics["common_path_packets"] = common_path_packets
    packet_metrics["common_path_sufficient"] = True
    packet_metrics["raw_reread_count"] = 0
    packet_metrics["packet_insufficiency_is_failure"] = True
    review_mode, worker_count, review_mode_adjustments = maybe_apply_delegation_savings_floor(
        review_mode,
        worker_count,
        packet_metrics,
        review_mode_adjustments,
    )
    if packet_payloads["global_packet.json"]["review_mode"] != review_mode:
        packet_payloads["global_packet.json"] = build_global_packet(
            context,
            review_mode=review_mode,
            override_signals=override_signals,
            focused_packet_hint=focused_packet_hint,
        )
        packet_payloads["synthesis_packet.json"] = build_synthesis_packet(
            context,
            review_mode=review_mode,
            drafting_basis=drafting_basis,
            focused_packet_hint=focused_packet_hint,
        )
        synthesis_packet = packet_payloads["synthesis_packet.json"]
        packet_metrics = contract.compute_packet_metrics(
            packet_payloads,
            common_path_packet_names=common_path_packets,
            raw_local_payload=raw_local_bundle(context, lint_report),
        )
        packet_metrics["raw_reread_allowed_reasons"] = contract.RAW_REREAD_ALLOWED_REASONS
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
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "recommended_worker_count": len(recommended_workers),
        "optional_worker_count": len(optional_workers),
        "packet_files": packet_files,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "shared_local_packet": contract.SHARED_LOCAL_PACKET,
        "common_path_contract": {
            "required_packets": contract.COMMON_PATH_REQUIRED_PACKETS,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "packet_insufficiency_is_failure": True,
        },
        "rewrite_strategy": synthesis_packet["rewrite_strategy"],
        "qa_required": synthesis_packet["qa_required"],
        "qa_reason": synthesis_packet["qa_reason"],
        "raw_reread_count": 0,
        "common_path_sufficient": True,
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
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
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
        "review_overrides": override_signals,
        "raw_reread_allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
        "common_path_contract": {
            "required_packets": contract.COMMON_PATH_REQUIRED_PACKETS,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "packet_insufficiency_is_failure": True,
            "raw_reread_should_be_exceptional": True,
        },
        "qa_policy": contract.QA_TRIGGER_POLICY,
        "local_responsibilities": [
            "Read rules_packet.json locally before drafting any replacement title/body.",
            "Read synthesis_packet.json locally before final drafting and keep common-path drafting on those packets plus at most one focused packet.",
            "Treat packet insufficiency as failure, not as permission to compensate with raw reread.",
            "Draft the final title/body locally.",
            "Run validate_pr_writeup_edit.py before any mutation.",
            "Run apply_pr_writeup.py only from validator output.",
        ],
        "packet_files": packet_files,
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
        "current_writeup": {
            "title_matches_conventional_commit": context.get("checks", {}).get("title_matches_conventional_commit"),
            "body_has_template_sections": context.get("checks", {}).get("body_has_template_sections"),
            "lint_error_count": len(findings.get("errors", [])),
            "lint_warning_count": len(findings.get("warnings", [])),
            "full_rewrite_likely": full_rewrite_likely(body, findings),
            "rewrite_strategy": synthesis_packet["rewrite_strategy"],
            "qa_required": synthesis_packet["qa_required"],
        },
    }
    packet_payloads["orchestrator.json"] = orchestrator
    packet_payloads["packet_metrics.json"] = packet_metrics
    return packet_payloads, build_result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build packet-heavy PR review packets with lean runtime metadata."
    )
    parser.add_argument("--context", required=True, help="Path to JSON from collect_pr_context.py")
    parser.add_argument("--lint", required=True, help="Path to JSON from lint_pr_writeup.py")
    parser.add_argument("--output-dir", required=True, help="Directory for generated packets")
    parser.add_argument("--result-output", help="Optional output path for build result JSON")
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
                "estimated_delegation_savings": build_result["packet_metrics"]["estimated_delegation_savings"],
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
