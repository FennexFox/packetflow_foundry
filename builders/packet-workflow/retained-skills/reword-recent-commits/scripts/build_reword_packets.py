#!/usr/bin/env python3
"""Build compact packet artifacts for token-efficient commit-message rewording."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from reword_plan_contract import (
    COMMON_PATH_CONTRACT,
    DECISION_READY_PACKETS,
    PACKET_METRIC_FIELDS,
    RAW_REREAD_ALLOWED_REASONS,
    WORKER_OUTPUT_SHAPE,
    WORKER_RETURN_CONTRACT,
    XHIGH_REREAD_POLICY,
    branch_state,
    build_packet_worker_map,
    build_task_packet_ids,
    build_task_packet_names,
    build_context_fingerprint,
    compute_packet_metrics,
    dedupe_preserve,
    detect_operation,
    load_json,
    parse_subject_line,
    packet_id,
    rules_reliability,
)


LOCAL_COMMIT_LIMIT = 2
LOCAL_FILE_LIMIT = 8
LOCAL_AREA_LIMIT = 2
BROAD_COMMIT_LIMIT = 5
BROAD_AREA_LIMIT = 4
CHURN_OVERRIDE_LIMIT = 200
MEANINGFUL_GENERATED_FILE_MIN_COUNT = 3
MEANINGFUL_GENERATED_FILE_MIN_RATIO = 0.2
GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)
def parse_shortstat(shortstat: str) -> dict[str, int]:
    files = re.search(r"(\d+)\s+files?\s+changed", shortstat)
    insertions = re.search(r"(\d+)\s+insertions?\(\+\)", shortstat)
    deletions = re.search(r"(\d+)\s+deletions?\(-\)", shortstat)
    return {
        "files_changed": int(files.group(1)) if files else 0,
        "insertions": int(insertions.group(1)) if insertions else 0,
        "deletions": int(deletions.group(1)) if deletions else 0,
        "churn": (int(insertions.group(1)) if insertions else 0)
        + (int(deletions.group(1)) if deletions else 0),
    }


def classify_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    lower = normalized.lower()
    if (
        "/tests/" in lower
        or lower.endswith("_test.py")
        or lower.endswith(".tests.cs")
        or lower.endswith(".spec.ts")
        or lower.startswith(".github/scripts/tests/")
    ):
        return "tests"
    if (
        lower.startswith(".github/workflows/")
        or lower.startswith(".github/scripts/")
        or lower.startswith(".github/issue_template/")
    ):
        return "automation"
    if lower.endswith(".md") or lower.startswith("docs/"):
        return "docs"
    if lower.endswith((".yml", ".yaml", ".toml", ".json", ".csproj", ".props", ".targets")):
        return "config"
    if lower.endswith((".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
        return "runtime"
    return "other"


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
    config_files = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "cargo.lock",
    }

    if lowered.startswith(runtime_prefixes) or lowered in runtime_files:
        return "runtime"
    if lowered.startswith(process_prefixes) or lowered in process_files:
        return "process"
    if lowered.endswith((".csproj", ".props", ".targets")) or lowered in config_files:
        return "config"
    return None


def candidate_scopes(files: list[str], rules: dict, current_subject: str) -> list[str]:
    candidates: list[str] = []
    known_scopes = list(rules.get("recent_scope_vocabulary", [])) + list(
        rules.get("rules", {}).get("scope_suggestions", [])
    )
    seen = set()

    parsed_subject = parse_subject_line(current_subject)
    if parsed_subject and parsed_subject.get("scope"):
        scope = str(parsed_subject["scope"])
        candidates.append(scope)
        seen.add(scope)

    for path in files:
        lower = path.replace("\\", "/").lower()
        derived = None
        if "/systems/" in lower:
            derived = "systems"
        elif "/patches/" in lower:
            derived = "patches"
        elif lower.startswith(".github/") or lower.endswith((".yml", ".yaml")):
            derived = "infra"
        elif lower.endswith(".md") or lower.startswith("docs/"):
            derived = "docs"
        elif lower.endswith((".csproj", ".props", ".targets", ".toml", ".json")):
            derived = "config"
        elif "/tests/" in lower or lower.endswith("_test.py"):
            derived = "test"
        elif lower.endswith(".lock"):
            derived = "deps"
        if derived and derived not in seen:
            candidates.append(derived)
            seen.add(derived)

    for scope in known_scopes:
        if scope in seen:
            continue
        if any(scope.lower() in path.replace("\\", "/").lower() for path in files):
            candidates.append(scope)
            seen.add(scope)

    return candidates[:6]


def body_needed_reason(commit: dict) -> tuple[bool, str]:
    files = commit.get("files", []) or []
    if len(files) > 1:
        return True, "More than one file changed."
    if str(commit.get("body", "")).strip():
        return True, "The current commit already carries a body."
    return False, "Single-file change with no existing body."


def current_message_checks(commit: dict, rules: dict, body_recommended: bool) -> dict[str, object]:
    subject = str(commit.get("subject", "")).strip()
    body = str(commit.get("body", "")).rstrip("\n")
    allowed_types = rules.get("rules", {}).get("allowed_types", [])
    scope_is_required = rules.get("rules", {}).get("scope_required")
    subject_limit = rules.get("rules", {}).get("subject_length_limit")
    expected_format = str(rules.get("rules", {}).get("format") or "<type>(<scope>): <subject>")
    errors: list[str] = []
    warnings: list[str] = []

    parsed_subject = parse_subject_line(subject)
    if not parsed_subject:
        errors.append(f"Subject does not match the repo format anchor `{expected_format}`.")
    else:
        message_type = str(parsed_subject["type"])
        scope = str(parsed_subject.get("scope", ""))
        if allowed_types and message_type not in allowed_types:
            errors.append(f"Type `{message_type}` is not in the allowed type list.")
        if scope_is_required and not scope:
            errors.append("Scope is required by repo rules.")

    if subject_limit and len(subject) > int(subject_limit):
        warnings.append(f"Subject exceeds the repo limit of {subject_limit} characters.")
    if body_recommended and not body.strip():
        warnings.append("Body is recommended by repo rules or commit shape but is empty.")

    return {
        "errors": errors,
        "warnings": warnings,
    }


def commit_quality_escape_hints(commit: dict[str, Any]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    commit_index = int(commit.get("index") or 0)
    subject = str(commit.get("subject") or "").strip()
    files = [str(path).strip() for path in commit.get("files", []) or [] if str(path).strip()]
    if not subject:
        hints.append(
            {
                "reason": "missing_required_evidence",
                "detail": "Commit subject is missing, so packet evidence is not sufficient for common-path drafting.",
                "commit_index": commit_index,
                "common_path_blocking": True,
            }
        )
    if not files:
        hints.append(
            {
                "reason": "missing_required_evidence",
                "detail": "Commit file coverage is missing, so packet evidence is not sufficient for common-path drafting.",
                "commit_index": commit_index,
                "common_path_blocking": True,
            }
        )
    return hints


def determine_baseline_review_mode(
    commit_count: int,
    unique_file_count: int,
    active_area_count: int,
) -> tuple[str, int]:
    if commit_count <= LOCAL_COMMIT_LIMIT and unique_file_count <= LOCAL_FILE_LIMIT and active_area_count <= LOCAL_AREA_LIMIT:
        review_mode = "local-only"
    elif commit_count > BROAD_COMMIT_LIMIT or active_area_count >= BROAD_AREA_LIMIT:
        review_mode = "broad-delegation"
    else:
        review_mode = "targeted-delegation"
    if review_mode == "local-only":
        return review_mode, 0
    if review_mode == "targeted-delegation":
        return review_mode, 2
    return review_mode, 3 if commit_count <= 6 else 4


def apply_override_adjustment(
    review_mode: str,
    worker_count: int,
    commit_count: int,
    override_signals: list[dict[str, str]],
) -> tuple[str, int, list[str]]:
    adjustments: list[str] = []
    if override_signals and review_mode == "local-only":
        review_mode = "targeted-delegation"
        worker_count = 2
        adjustments.append("override_signal")
    elif override_signals and review_mode == "targeted-delegation":
        review_mode = "broad-delegation"
        worker_count = 3 if commit_count <= 6 else 4
        adjustments.append("override_signal")
    return review_mode, worker_count, adjustments


def chunk_commit_indexes(commit_indexes: list[int], chunks: int) -> list[list[int]]:
    if chunks <= 0:
        return []
    result: list[list[int]] = [[] for _ in range(chunks)]
    for index, commit_index in enumerate(commit_indexes):
        result[index % chunks].append(commit_index)
    return [chunk for chunk in result if chunk]


def packet_name_for_commit(commit_index: int) -> str:
    return f"commit-{commit_index:02d}.json"


def build_result_payload(
    *,
    review_mode: str,
    review_mode_baseline: str,
    review_mode_adjustments: list[str],
    recommended_workers: list[dict[str, Any]],
    packet_files: list[str],
    active_packets: list[str],
    applied_override_signals: list[str],
    commit_packet_count: int,
    packet_metrics: dict[str, int],
    common_path_sufficient: bool,
    raw_reread_reasons: list[str],
) -> dict[str, Any]:
    return {
        "review_mode": review_mode,
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "recommended_worker_count": len(recommended_workers),
        "recommended_workers": recommended_workers,
        "packet_files": packet_files,
        "active_packets": active_packets,
        "active_packet_count": len(active_packets),
        "commit_packet_count": commit_packet_count,
        "applied_override_signals": applied_override_signals,
        "common_path_sufficient": common_path_sufficient,
        "raw_reread_count": len(raw_reread_reasons),
        "raw_reread_reasons": raw_reread_reasons,
        "packet_metrics": packet_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build packet artifacts for token-efficient commit-message rewording."
    )
    parser.add_argument("--rules", type=Path, required=True, help="Path to rules JSON from collect_commit_rules.py")
    parser.add_argument("--plan", type=Path, required=True, help="Path to plan JSON from collect_recent_commits.py")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated packets")
    parser.add_argument("--result-output", type=Path, help="Optional path to write build result JSON.")
    args = parser.parse_args()

    rules = load_json(args.rules)
    plan = load_json(args.plan)
    repo_root = Path(str(plan.get("repo_root", "")))
    commits = plan.get("commits", [])
    if not isinstance(commits, list) or not commits:
        print("build_reword_packets.py: plan does not contain commits", file=sys.stderr)
        return 1

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    branch_info = branch_state(repo_root)
    active_operation = detect_operation(repo_root)
    context_fingerprint_value = build_context_fingerprint(plan, rules)
    rules_reliability_value = rules_reliability(rules)
    unique_files = sorted({path for commit in commits for path in commit.get("files", [])})
    unique_file_count = len(unique_files)
    generated_file_count = sum(1 for path in unique_files if is_generated_file(path))
    generated_file_ratio = (generated_file_count / unique_file_count) if unique_file_count else 0.0
    area_names = sorted({classify_path(path) for path in unique_files if classify_path(path) != "other"})
    core_areas_touched = sorted(
        {
            area
            for path in unique_files
            if (area := core_area_for_path(path)) is not None
        }
    )

    total_insertions = 0
    total_deletions = 0
    total_churn = 0
    merge_commit_indexes: list[int] = []
    commit_packet_names: list[str] = []
    commit_payloads: dict[str, dict[str, Any]] = {}
    commit_quality_hints: list[dict[str, Any]] = []

    global_packet = {
        "purpose": "Shared context every worker should keep in view before reading its packet.",
        "task_intent": "Rewrite recent commit messages to repo rules without losing each commit's real behavior or workflow intent.",
        "repo_profile_name": plan.get("repo_profile_name"),
        "repo_profile_path": plan.get("repo_profile_path"),
        "repo_profile_summary": plan.get("repo_profile_summary"),
        "repo_profile": plan.get("repo_profile"),
        "rewrite_scope": {
            "count": plan.get("count"),
            "branch": plan.get("branch"),
            "head_commit": plan.get("head_commit"),
            "base_commit": plan.get("base_commit"),
        },
        "context_fingerprint": context_fingerprint_value,
        "rewrite_safety": {
            "detached_head": plan.get("detached_head"),
            "active_operation": active_operation or plan.get("active_operation"),
            "working_tree_dirty": branch_info["working_tree_dirty"],
            "upstream_branch": branch_info["upstream_branch"],
            "ahead_count": branch_info["ahead_count"],
            "behind_count": branch_info["behind_count"],
            "force_push_likely": branch_info["force_push_likely"],
        },
        "rules_reliability": rules_reliability_value,
        "required_message_rules": {
            "format": rules.get("rules", {}).get("format"),
            "allowed_types": rules.get("rules", {}).get("allowed_types", []),
            "scope_required": rules.get("rules", {}).get("scope_required"),
            "subject_length_limit": rules.get("rules", {}).get("subject_length_limit"),
            "body_rules": rules.get("rules", {}).get("body_rules", []),
            "references_rules": rules.get("rules", {}).get("references_rules", []),
        },
        "disallowed_rewrite_actions": [
            "Do not change refs or run apply_reword_plan.py without explicit user confirmation.",
            "Do not hand-drive interactive rebase when the plan/apply scripts are sufficient.",
            "Do not rewrite merge commits with this workflow.",
            "Do not proceed while another git operation is already in progress.",
            "Do not invent issue references or body bullets that are not supported by the commit content or repo context.",
        ],
        "recent_scope_vocabulary": rules.get("recent_scope_vocabulary", []),
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
    }
    (output_dir / "global_packet.json").write_text(
        json.dumps(global_packet, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    rules_packet = {
        "purpose": "Extract hard commit-message rules and preferred scope vocabulary.",
        "local_gate": "Read this packet locally before drafting replacement messages, and re-check the final draft set against it before applying the rewrite.",
        "context_fingerprint": context_fingerprint_value,
        "rules_reliability": rules_reliability_value,
        "rule_files": rules.get("rule_files", {}),
        "rules": rules.get("rules", {}),
        "rule_derivation": rules.get("rule_derivation", {}),
        "recent_scope_vocabulary": rules.get("recent_scope_vocabulary", []),
        "recent_subject_samples": rules.get("recent_subject_samples", []),
        "instruction_snippets": rules.get("instruction_snippets", {}),
        "doc_mentions": rules.get("doc_mentions", {}),
    }
    (output_dir / "rules_packet.json").write_text(
        json.dumps(rules_packet, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    for commit in commits:
        commit_index = int(commit["index"])
        shortstat = parse_shortstat(str(commit.get("shortstat", "")))
        total_insertions += shortstat["insertions"]
        total_deletions += shortstat["deletions"]
        total_churn += shortstat["churn"]
        if len(commit.get("parent_hashes", [])) > 1:
            merge_commit_indexes.append(commit_index)

        files = commit.get("files", []) or []
        areas = sorted({classify_path(path) for path in files if classify_path(path) != "other"})
        body_needed, reason = body_needed_reason(commit)
        quality_escape_hints = commit_quality_escape_hints(commit)
        commit_quality_hints.extend(quality_escape_hints)
        packet = {
            "purpose": "Summarize one commit's real intent before drafting a replacement message.",
            "commit": {
                "index": commit_index,
                "hash": commit.get("hash"),
                "short_hash": commit.get("short_hash"),
                "subject": commit.get("subject"),
                "body": commit.get("body"),
                "full_message": commit.get("full_message"),
                "parent_hashes": commit.get("parent_hashes"),
                "new_message": commit.get("new_message", ""),
            },
            "files": files,
            "shortstat": shortstat,
            "inferred_areas": areas,
            "scope_candidates": candidate_scopes(files, rules, str(commit.get("subject", ""))),
            "body_guidance": {
                "body_recommended": body_needed,
                "reason": reason,
            },
            "current_message_checks": current_message_checks(commit, rules, body_needed),
            "quality_escape_hints": quality_escape_hints,
            "rules_reliability": rules_reliability_value,
        }
        packet_name = packet_name_for_commit(commit_index)
        (output_dir / packet_name).write_text(
            json.dumps(packet, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        commit_packet_names.append(packet_name)
        commit_payloads[packet_name] = packet

    override_signals: list[dict[str, str]] = []
    if total_churn >= CHURN_OVERRIDE_LIMIT:
        override_signals.append(
            {
                "reason": "aggregate_churn_threshold",
                "detail": f"Aggregate shortstat churn reached {total_churn} lines (threshold {CHURN_OVERRIDE_LIMIT}).",
            }
        )
    if len(core_areas_touched) >= 2:
        override_signals.append(
            {
                "reason": "core_files_across_groups",
                "detail": "Core runtime/config/process files were touched across multiple areas: "
                + ", ".join(core_areas_touched),
            }
        )
    if (
        generated_file_count >= MEANINGFUL_GENERATED_FILE_MIN_COUNT
        and MEANINGFUL_GENERATED_FILE_MIN_RATIO <= generated_file_ratio < 0.5
    ):
        override_signals.append(
            {
                "reason": "generated_files_meaningful_minor_slice",
                "detail": "Generated files are a meaningful minority slice "
                f"({generated_file_count}/{unique_file_count}) of the touched files.",
            }
        )

    review_mode_baseline, worker_count = determine_baseline_review_mode(
        commit_count=len(commits),
        unique_file_count=unique_file_count,
        active_area_count=len(area_names),
    )
    review_mode, worker_count, review_mode_adjustments = apply_override_adjustment(
        review_mode_baseline,
        worker_count,
        len(commits),
        override_signals=override_signals,
    )

    raw_reread_reasons = dedupe_preserve(
        [
            str(item.get("reason"))
            for item in commit_quality_hints
            if item.get("common_path_blocking")
        ]
    )
    unexpected_reread_reasons = [
        reason
        for reason in raw_reread_reasons
        if reason not in RAW_REREAD_ALLOWED_REASONS
    ]
    if unexpected_reread_reasons:
        print(
            "build_reword_packets.py: unsupported reread reasons generated: "
            + ", ".join(unexpected_reread_reasons),
            file=sys.stderr,
        )
        return 1
    common_path_sufficient = not raw_reread_reasons

    task_packet_names = build_task_packet_names(commit_packet_names)
    task_packet_ids = build_task_packet_ids(commit_packet_names)
    packet_worker_map = build_packet_worker_map(commit_packet_names)
    preferred_worker_families = {
        "context_findings": ["repo_mapper", "docs_verifier", "evidence_summarizer"],
        "verifiers": ["docs_verifier"],
    }
    worker_selection_guidance = [
        "docs_verifier: use for rules_packet and hard commit-message constraints.",
        "evidence_summarizer: use for commit packets that summarize one commit's intent and rewrite constraints.",
        "large_diff_auditor: use for QA when the rewrite spans many commits or the evidence disagrees.",
        "repo_mapper: keep local for rewrite-scope and blocker inspection before final synthesis.",
    ]
    worker_output_fields = [
        "commit_indexes",
        "primary_intent",
        "suggested_type_scope",
        "body_needed",
        "evidence_files",
        "ambiguity",
        "confidence",
        "reread_control",
    ]
    global_packet.update(
        {
            "decision_ready_packets": DECISION_READY_PACKETS,
            "worker_return_contract": WORKER_RETURN_CONTRACT,
            "worker_output_shape": WORKER_OUTPUT_SHAPE,
            "common_path_contract": COMMON_PATH_CONTRACT,
            "task_packet_names": task_packet_names,
            "task_packet_ids": task_packet_ids,
            "worker_selection_guidance": worker_selection_guidance,
            "preferred_worker_families": preferred_worker_families,
            "packet_worker_map": packet_worker_map,
            "worker_output_fields": worker_output_fields,
            "reread_reason_values": RAW_REREAD_ALLOWED_REASONS,
            "packet_metric_fields": PACKET_METRIC_FIELDS,
            "xhigh_reread_policy": XHIGH_REREAD_POLICY,
            "common_path_sufficient": common_path_sufficient,
            "raw_reread_reasons": raw_reread_reasons,
        }
    )
    (output_dir / "global_packet.json").write_text(
        json.dumps(global_packet, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    recommended_workers: list[dict[str, object]] = []
    optional_workers: list[dict[str, object]] = []
    commit_indexes = [int(commit["index"]) for commit in commits]

    if review_mode == "targeted-delegation":
        recommended_workers.append(
            {
                "name": "rules",
                "agent_type": "docs_verifier",
                "packets": ["global_packet.json", "rules_packet.json"],
                "responsibility": "Extract hard commit-message rules and preferred scope vocabulary.",
                "reasoning_effort": "medium",
            }
        )
        recommended_workers.append(
            {
                "name": "commit-intent",
                "agent_type": "evidence_summarizer",
                "packets": ["global_packet.json", *commit_packet_names],
                "responsibility": "Summarize each targeted commit's primary intent and rewrite constraints.",
                "reasoning_effort": "medium",
                "model": "gpt-5.4-mini",
            }
        )
    elif review_mode == "broad-delegation":
        recommended_workers.append(
            {
                "name": "rules",
                "agent_type": "docs_verifier",
                "packets": ["global_packet.json", "rules_packet.json"],
                "responsibility": "Extract hard commit-message rules and preferred scope vocabulary.",
                "reasoning_effort": "medium",
            }
        )
        commit_worker_count = max(1, worker_count - 1)
        for batch_index, batch in enumerate(chunk_commit_indexes(commit_indexes, commit_worker_count), start=1):
            packets = ["global_packet.json"] + [packet_name_for_commit(index) for index in batch]
            recommended_workers.append(
                {
                    "name": f"commit-batch-{batch_index}",
                    "agent_type": "evidence_summarizer",
                    "packets": packets,
                    "responsibility": "Summarize commit intent and rewrite constraints for this commit batch.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                }
            )
        optional_workers.append(
            {
                "name": "qa",
                "agent_type": "large_diff_auditor",
                "packets": ["global_packet.json", "rules_packet.json", *commit_packet_names],
                    "responsibility": "Compare the drafted replacement messages against the rules and per-commit evidence.",
                    "reasoning_effort": "medium",
                    "when": "Only add this pass when the rewrite covers many areas or worker findings conflict.",
                }
        )

    orchestrator = {
        "rewrite_scope": {
            "count": len(commits),
            "branch": plan.get("branch"),
            "head_commit": plan.get("head_commit"),
        },
        "repo_profile_name": plan.get("repo_profile_name"),
        "repo_profile_path": plan.get("repo_profile_path"),
        "repo_profile_summary": plan.get("repo_profile_summary"),
        "review_mode": review_mode,
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "worker_budget": len(recommended_workers),
        "recommended_worker_count": len(recommended_workers),
        "optional_worker_count": len(optional_workers),
        "shared_packet": "global_packet.json",
        "shared_packet_name": "global_packet.json",
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "common_path_contract": COMMON_PATH_CONTRACT,
        "task_packet_names": task_packet_names,
        "task_packet_ids": task_packet_ids,
        "commit_packet_count": len(commit_packet_names),
        "worker_selection_guidance": worker_selection_guidance,
        "preferred_worker_families": preferred_worker_families,
        "packet_worker_map": packet_worker_map,
        "worker_output_fields": worker_output_fields,
        "reread_reason_values": RAW_REREAD_ALLOWED_REASONS,
        "packet_metric_fields": PACKET_METRIC_FIELDS,
        "xhigh_reread_policy": XHIGH_REREAD_POLICY,
        "active_areas": area_names,
        "context_fingerprint": context_fingerprint_value,
        "rules_reliability": rules_reliability_value,
        "common_path_sufficient": common_path_sufficient,
        "raw_reread_reasons": raw_reread_reasons,
        "rewrite_blockers": {
            "active_operation": active_operation or plan.get("active_operation"),
            "detached_head": bool(plan.get("detached_head")),
            "merge_commit_indexes": merge_commit_indexes,
            "root_rewrite_unsupported": not bool(plan.get("base_commit")),
        },
        "diff_summary": {
            "commit_count": len(commits),
            "unique_file_count": unique_file_count,
            "aggregate_shortstat": {
                "insertions": total_insertions,
                "deletions": total_deletions,
                "churn": total_churn,
            },
            "generated_file_count": generated_file_count,
            "generated_file_ratio": round(generated_file_ratio, 3),
            "core_areas_touched": core_areas_touched,
        },
        "review_overrides": override_signals,
        "local_responsibilities": [
            "Read rules_packet.json locally before drafting replacement messages.",
            "Draft the final replacement commit messages locally.",
            "Keep commits in oldest-to-newest order.",
            "Re-check the final message set against rules_packet.json locally before asking for confirmation.",
            "Ask for confirmation immediately before rewriting history.",
            "Run apply_reword_plan.py only after confirmation.",
        ],
        "packet_files": ["global_packet.json", "rules_packet.json", *commit_packet_names, "orchestrator.json"],
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
    }
    (output_dir / "orchestrator.json").write_text(
        json.dumps(orchestrator, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    packet_payloads: dict[str, dict[str, Any]] = {
        "global_packet.json": global_packet,
        "rules_packet.json": rules_packet,
        **commit_payloads,
    }
    packet_metrics = compute_packet_metrics(
        packet_payloads,
        local_only_sources={"rules": rules, "plan": plan},
        shared_packets=COMMON_PATH_CONTRACT["shared_packets"],
    )
    if orchestrator["review_mode"] != review_mode:
        recommended_workers = []
        optional_workers = []
        if review_mode == "targeted-delegation":
            recommended_workers.append(
                {
                    "name": "rules",
                    "agent_type": "docs_verifier",
                    "packets": ["global_packet.json", "rules_packet.json"],
                    "responsibility": "Extract hard commit-message rules and preferred scope vocabulary.",
                    "reasoning_effort": "medium",
                }
            )
            recommended_workers.append(
                {
                    "name": "commit-intent",
                    "agent_type": "evidence_summarizer",
                    "packets": ["global_packet.json", *commit_packet_names],
                    "responsibility": "Summarize each targeted commit's primary intent and rewrite constraints.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                }
            )
        elif review_mode == "broad-delegation":
            recommended_workers.append(
                {
                    "name": "rules",
                    "agent_type": "docs_verifier",
                    "packets": ["global_packet.json", "rules_packet.json"],
                    "responsibility": "Extract hard commit-message rules and preferred scope vocabulary.",
                    "reasoning_effort": "medium",
                }
            )
            commit_worker_count = max(1, worker_count - 1)
            for batch_index, batch in enumerate(chunk_commit_indexes(commit_indexes, commit_worker_count), start=1):
                packets = ["global_packet.json"] + [packet_name_for_commit(index) for index in batch]
                recommended_workers.append(
                    {
                        "name": f"commit-batch-{batch_index}",
                        "agent_type": "evidence_summarizer",
                        "packets": packets,
                        "responsibility": "Summarize commit intent and rewrite constraints for this commit batch.",
                        "reasoning_effort": "medium",
                        "model": "gpt-5.4-mini",
                    }
                )
            optional_workers.append(
                {
                    "name": "qa",
                    "agent_type": "large_diff_auditor",
                    "packets": ["global_packet.json", "rules_packet.json", *commit_packet_names],
                    "responsibility": "Compare the drafted replacement messages against the rules and per-commit evidence.",
                    "reasoning_effort": "medium",
                    "when": "Only add this pass when the rewrite covers many areas or worker findings conflict.",
                }
            )
        orchestrator["review_mode"] = review_mode
        orchestrator["review_mode_baseline"] = review_mode_baseline
        orchestrator["review_mode_adjustments"] = review_mode_adjustments
        orchestrator["worker_budget"] = len(recommended_workers)
        orchestrator["recommended_worker_count"] = len(recommended_workers)
        orchestrator["optional_worker_count"] = len(optional_workers)
        orchestrator["recommended_workers"] = recommended_workers
        orchestrator["optional_workers"] = optional_workers
        (output_dir / "orchestrator.json").write_text(
            json.dumps(orchestrator, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    final_packet_payloads = {
        **packet_payloads,
        "orchestrator.json": orchestrator,
    }
    packet_metrics = compute_packet_metrics(
        final_packet_payloads,
        local_only_sources={"rules": rules, "plan": plan},
        shared_packets=COMMON_PATH_CONTRACT["shared_packets"],
    )
    (output_dir / "packet_metrics.json").write_text(
        json.dumps(packet_metrics, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    active_packets = ["rules_packet.json", *commit_packet_names]
    build_result = build_result_payload(
        review_mode=review_mode,
        review_mode_baseline=review_mode_baseline,
        review_mode_adjustments=review_mode_adjustments,
        recommended_workers=recommended_workers,
        packet_files=orchestrator["packet_files"],
        active_packets=active_packets,
        applied_override_signals=[str(item.get("reason")) for item in override_signals if str(item.get("reason") or "").strip()],
        commit_packet_count=len(commit_packet_names),
        packet_metrics=packet_metrics,
        common_path_sufficient=common_path_sufficient,
        raw_reread_reasons=raw_reread_reasons,
    )
    if args.result_output:
        args.result_output.parent.mkdir(parents=True, exist_ok=True)
        args.result_output.write_text(
            json.dumps(build_result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "review_mode": review_mode,
                "packet_files": orchestrator["packet_files"],
                "recommended_worker_count": len(recommended_workers),
                "common_path_sufficient": common_path_sufficient,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
