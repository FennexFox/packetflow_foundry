#!/usr/bin/env python3
"""Shared packet contracts and helpers for git-split-and-commit."""

from __future__ import annotations

import json
from typing import Any

ORCHESTRATOR_PROFILE = "standard"
DECISION_READY_PACKETS = True
WORKER_RETURN_CONTRACT = "classification-oriented"
WORKER_OUTPUT_SHAPE = "hierarchical"

PACKET_NAMES = {
    "global": "global_packet.json",
    "rules": "rules_packet.json",
    "worktree": "worktree_packet.json",
}

PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["repo_mapper", "docs_verifier"],
    "candidate_producers": ["evidence_summarizer", "large_diff_auditor", "log_triager"],
    "verifiers": ["docs_verifier"],
}

WORKER_SELECTION_GUIDANCE = {
    "routing_authority": "packet_worker_map",
    "notes": "packet_worker_map is the concrete routing source; preferred_worker_families is explanatory metadata.",
    "agent_type_guidance": {
        "docs_verifier": "Use for hard commit-message constraints, scope rules, and repo defaults.",
        "repo_mapper": "Use for worktree surface mapping, touched-area summary, and validation-candidate coverage.",
        "evidence_summarizer": "Use for logical commit-bucket summaries and proposal-grade scope/type recommendations.",
        "large_diff_auditor": "Use for split-file adjudication and QA on risky commit boundaries.",
        "log_triager": "Use only when targeted validation or automation blockers need narrow triage.",
    },
}

RAW_REREAD_ALLOWED_REASONS = [
    "conflicting_signals",
    "missing_required_evidence",
    "schema_mismatch",
    "insufficient_excerpt_quality",
    "stale_worktree_fingerprint",
    "ambiguous_hunk_match",
]

XHIGH_REREAD_POLICY = (
    "Packet-first local adjudication is required on the common path; raw diff rereads are only allowed for explicit exception reasons."
)

COMMON_PATH_CONTRACT = {
    "shared_packets": ["rules_packet.json", "worktree_packet.json"],
    "focused_packet_mode": "read one candidate-batch or split-file packet at a time while keeping the shared packets in view",
    "goal": "Draft commit-plan.json without raw diff rereads on the common path.",
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


def packet_basename(name: str) -> str:
    return name.removesuffix(".json")


def packet_basenames(names: list[str]) -> list[str]:
    return [packet_basename(name) for name in names]


def build_task_packet_names(candidate_batch_names: list[str], split_packet_names: list[str]) -> list[str]:
    return [
        packet_basename(PACKET_NAMES["rules"]),
        packet_basename(PACKET_NAMES["worktree"]),
        *packet_basenames(candidate_batch_names),
        *packet_basenames(split_packet_names),
    ]


def build_packet_worker_map(candidate_batch_names: list[str], split_packet_names: list[str]) -> dict[str, list[str]]:
    return {
        packet_basename(PACKET_NAMES["rules"]): ["docs_verifier"],
        packet_basename(PACKET_NAMES["worktree"]): ["repo_mapper"],
        **{name: ["evidence_summarizer"] for name in packet_basenames(candidate_batch_names)},
        **{name: ["large_diff_auditor"] for name in packet_basenames(split_packet_names)},
    }


def dedupe_preserve(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8"))


def estimate_tokens_from_bytes(byte_count: int) -> int:
    if byte_count <= 0:
        return 0
    return max(1, int(round(byte_count / 4.0)))


def compute_packet_metrics(
    packet_payloads: dict[str, Any],
    *,
    local_only_sources: dict[str, Any],
    shared_packets: list[str] | None = None,
) -> dict[str, int]:
    shared_packet_names = shared_packets or [PACKET_NAMES["rules"], PACKET_NAMES["worktree"]]
    packet_sizes = {
        name: json_bytes(payload)
        for name, payload in packet_payloads.items()
    }
    total_packet_bytes = sum(packet_sizes.values())
    largest_sizes = sorted(packet_sizes.values(), reverse=True)
    focused_sizes = [
        size
        for name, size in packet_sizes.items()
        if name.startswith("candidate-batch-") or name.startswith("split-file-")
    ]
    common_path_packet_bytes = sum(packet_sizes.get(name, 0) for name in shared_packet_names)
    if focused_sizes:
        common_path_packet_bytes += max(focused_sizes)
    local_only_bytes = sum(json_bytes(payload) for payload in local_only_sources.values())
    estimated_local_only_tokens = estimate_tokens_from_bytes(local_only_bytes)
    estimated_packet_tokens = estimate_tokens_from_bytes(common_path_packet_bytes)
    return {
        "packet_count": len(packet_payloads),
        "packet_size_bytes": total_packet_bytes,
        "largest_packet_bytes": largest_sizes[0] if largest_sizes else 0,
        "largest_two_packets_bytes": sum(largest_sizes[:2]),
        "estimated_local_only_tokens": estimated_local_only_tokens,
        "estimated_packet_tokens": estimated_packet_tokens,
        "estimated_delegation_savings": max(0, estimated_local_only_tokens - estimated_packet_tokens),
    }
