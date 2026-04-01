#!/usr/bin/env python3
"""Shared packet/runtime contract for gh-address-review-threads build artifacts."""

from __future__ import annotations

import json
from typing import Any


WORKFLOW_FAMILY = "github-review"
ARCHETYPE = "audit-and-apply"
ORCHESTRATOR_PROFILE = "standard"
DECISION_READY_PACKETS = False
WORKER_RETURN_CONTRACT = "generic"
WORKER_OUTPUT_SHAPE = "flat"
XHIGH_REREAD_POLICY = "packet-first local adjudication with raw rereads only for explicit exception reasons"

LOCAL_THREAD_LIMIT = 1
TARGETED_THREAD_LIMIT = 4
TARGETED_TARGET_LIMIT = 2
BROAD_TARGET_LIMIT = 3
CHURN_OVERRIDE_LIMIT = 400
MEANINGFUL_GENERATED_FILE_MIN_COUNT = 3
MEANINGFUL_GENERATED_FILE_MIN_RATIO = 0.2

PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["packet_explorer"],
    "candidate_producers": [],
    "verifiers": [],
}

ALLOWED_REREAD_REASONS = [
    "conflicting_signals",
    "missing_required_evidence",
    "insufficient_excerpt_quality",
    "ownership_ambiguity",
    "stale_context",
]

COMMON_PATH_SUFFICIENCY_REQUIREMENTS = [
    "required evidence is present inside the packet set used for the decision",
    "ownership ambiguity stays below the escape threshold",
    "no explicit reread or escape reason is required",
    "validator-ready recommendation path is closed from packet contents alone",
]

COMMON_PATH_CONTRACT = {
    "default_basis": [
        "global_packet.json + one thread-batch packet",
        "global_packet.json + one thread packet",
    ],
    "allowed_reread_reasons": ALLOWED_REREAD_REASONS,
    "sufficiency_requirements": COMMON_PATH_SUFFICIENCY_REQUIREMENTS,
    "quality_escape_hints_policy": "advisory-only",
    "override_policy": "review_mode_overrides may widen worker recommendation but must not upgrade missing evidence or ownership ambiguity into common_path_sufficient=true",
}

PACKET_METRIC_FIELDS = [
    "packet_count",
    "packet_size_bytes",
    "largest_packet_bytes",
    "largest_two_packets_bytes",
    "estimated_local_only_tokens",
    "estimated_packet_tokens",
    "estimated_delegation_savings",
]

SMOKE_OUTPUT_FIELDS = ["status", "reason", "thread_counts", "next_action"]


def canonical_json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"


def packet_size_bytes(payload: Any) -> int:
    return len(canonical_json_text(payload).encode("utf-8"))


def estimate_tokens_from_bytes(size_bytes: int) -> int:
    if size_bytes <= 0:
        return 0
    return max(1, (size_bytes + 3) // 4)


def compute_packet_metrics(
    runtime_payloads: dict[str, Any],
    *,
    common_path_packet_names: list[str],
    local_only_sources: dict[str, Any],
) -> dict[str, int]:
    packet_sizes_by_name = {name: packet_size_bytes(payload) for name, payload in runtime_payloads.items()}
    packet_sizes = list(packet_sizes_by_name.values())
    total_packet_bytes = sum(packet_sizes)
    largest = max(packet_sizes, default=0)
    largest_two = sum(sorted(packet_sizes, reverse=True)[:2])
    common_path_bytes = sum(packet_sizes_by_name.get(name, 0) for name in common_path_packet_names)
    local_only_bytes = sum(packet_size_bytes(payload) for payload in local_only_sources.values())
    estimated_local_only_tokens = estimate_tokens_from_bytes(local_only_bytes)
    estimated_packet_tokens = estimate_tokens_from_bytes(common_path_bytes)
    return {
        "packet_count": len(runtime_payloads),
        "packet_size_bytes": total_packet_bytes,
        "largest_packet_bytes": largest,
        "largest_two_packets_bytes": largest_two,
        "estimated_local_only_tokens": estimated_local_only_tokens,
        "estimated_packet_tokens": estimated_packet_tokens,
        "estimated_delegation_savings": max(estimated_local_only_tokens - estimated_packet_tokens, 0),
    }


def derive_packet_worker_map(packet_names: list[str]) -> dict[str, list[str]]:
    return {
        packet_name.removesuffix(".json"): ["packet_explorer"]
        for packet_name in packet_names
    }


def derive_recommended_workers(
    *,
    review_mode: str,
    global_packet_name: str,
    analysis_packet_names: list[str],
    packet_worker_map: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if review_mode == "local-only":
        return []

    worker_budget = (
        TARGETED_TARGET_LIMIT
        if review_mode == "targeted-delegation"
        else min(max(len(analysis_packet_names), 1), 4)
    )
    if review_mode == "broad-delegation" and worker_budget < 3 and len(analysis_packet_names) >= 3:
        worker_budget = 3

    workers: list[dict[str, Any]] = []
    for index, packet_name in enumerate(analysis_packet_names[:worker_budget], start=1):
        workers.append(
            {
                "name": f"thread-analysis-{index}",
                "agent_type": packet_worker_map.get(packet_name.removesuffix(".json"), ["packet_explorer"])[0],
                "packets": [global_packet_name, packet_name],
                "responsibility": "Summarize the threaded issue, fix direction, risk, and concrete file/test scope for this packet.",
                "reasoning_effort": "medium",
                "model": "gpt-5.4-mini",
                "return_contract": [
                    "thread ids",
                    "problem summary",
                    "fix direction",
                    "risk",
                    "files to edit",
                    "tests to run",
                ],
            }
        )
    return workers


def derive_optional_workers(
    *,
    review_mode: str,
    global_packet_name: str,
    optional_qa_packets: list[str],
) -> list[dict[str, Any]]:
    if review_mode == "local-only":
        return []
    return [
        {
            "name": "qa",
            "agent_type": "large_diff_auditor",
            "packets": [global_packet_name, *optional_qa_packets],
            "responsibility": "Compare the proposed completion reply and changed files against the thread requirements before resolution.",
            "reasoning_effort": "medium",
            "when": "Only add this worker when broad fixes are in play, worker findings conflict, or resolution confidence is low.",
            "return_contract": [
                "thread ids",
                "resolution verdict",
                "coverage gaps",
                "unsupported claims",
                "remaining risk",
            ],
        }
    ]


def build_result_payload(
    *,
    review_mode: str,
    recommended_workers: list[dict[str, Any]],
    optional_workers: list[dict[str, Any]],
    thread_batch_count: int,
    singleton_thread_packet_count: int,
    active_paths: list[str],
    override_signals: list[dict[str, str]],
    common_path_sufficient: bool,
    common_path_failures: list[dict[str, Any]],
    thread_counts: dict[str, Any],
    same_run_reconciliation_enabled: bool,
    outdated_transition_candidates: int,
    outdated_auto_resolve_candidates: int,
    outdated_recheck_ambiguous: int,
    packet_metrics_path: str,
) -> dict[str, Any]:
    return {
        "review_mode": review_mode,
        "recommended_worker_count": len(recommended_workers),
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
        "thread_batch_count": thread_batch_count,
        "singleton_thread_packet_count": singleton_thread_packet_count,
        "active_paths": active_paths,
        "override_signals": override_signals,
        "common_path_sufficient": common_path_sufficient,
        "common_path_failures": common_path_failures,
        "thread_counts": thread_counts,
        "same_run_reconciliation_enabled": same_run_reconciliation_enabled,
        "outdated_transition_candidates": outdated_transition_candidates,
        "outdated_auto_resolve_candidates": outdated_auto_resolve_candidates,
        "outdated_recheck_ambiguous": outdated_recheck_ambiguous,
        "packet_metrics_file": packet_metrics_path,
    }
