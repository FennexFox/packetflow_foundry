#!/usr/bin/env python3
"""Shared contracts and helpers for public-docs-sync."""

from __future__ import annotations

import json
from typing import Any

PACKET_NAMES = [
    "claims_packet",
    "reporting_packet",
    "workflow_packet",
    "forms_batch_packet",
]

WORKFLOW_FAMILY = "repo-audit"
ARCHETYPE = "audit-and-apply"
ORCHESTRATOR_PROFILE = "standard"
DECISION_READY_PACKETS = False
WORKER_RETURN_CONTRACT = "generic"
WORKER_OUTPUT_SHAPE = "flat"

PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["repo_mapper", "docs_verifier"],
    "candidate_producers": ["evidence_summarizer", "large_diff_auditor", "log_triager"],
    "verifiers": ["docs_verifier"],
}

PACKET_WORKER_MAP = {
    "claims_packet": ["large_diff_auditor", "repo_mapper"],
    "reporting_packet": ["evidence_summarizer"],
    "workflow_packet": ["docs_verifier"],
    "forms_batch_packet": ["docs_verifier"],
    "batch-packet-01": ["docs_verifier"],
}

WORKER_SELECTION_GUIDANCE = {
    "routing_authority": "packet_worker_map",
    "notes": "worker_selection_guidance is explanatory only; packet_worker_map is the concrete routing source.",
    "agent_type_guidance": {
        "repo_mapper": "Use for baseline reuse questions, packet ownership, and relevant-ref mapping when the selected ref is ambiguous.",
        "docs_verifier": "Use for public docs wording, workflow docs, and issue-template or policy verification.",
        "evidence_summarizer": "Use for GitHub evidence and narrative change digests that need narrow compression.",
        "large_diff_auditor": "Use for claims drift, runtime-default drift, and broad doc/code diffs.",
        "log_triager": "Use for workflow-run failures, issue-form anomalies, or blocker triage.",
    },
}

REVIEW_MODE_OVERRIDES = [
    "diff churn exceeds the public-docs threshold",
    "runtime defaults and public workflow files span multiple packet groups",
    "generated files are present but are not the majority of the change",
]

RAW_REREAD_ALLOWED_REASONS = [
    "explicit_stop",
    "evidence_dispute",
    "edge_case_layout",
    "validator_blocker",
]

XHIGH_REREAD_POLICY = (
    "Focused packets should support common-path local review; raw reread is allowed only for explicit edge cases."
)

VALIDATION_ERROR_CODES = {
    "missing_field": "E_PLAN_MISSING_FIELD",
    "context_id_mismatch": "E_PLAN_CONTEXT_ID_MISMATCH",
    "context_fingerprint_mismatch": "E_PLAN_CONTEXT_FINGERPRINT_MISMATCH",
    "head_changed": "E_PLAN_HEAD_CHANGED",
    "ambiguous_selected_packet": "E_PLAN_AMBIGUOUS_SELECTED_PACKET",
    "missing_required_evidence": "E_PLAN_MISSING_REQUIRED_EVIDENCE",
    "deterministic_scope_exceeded": "E_PLAN_DETERMINISTIC_SCOPE_EXCEEDED",
    "stale_marker_context": "E_PLAN_STALE_MARKER_CONTEXT",
}

VALIDATION_WARNING_CODES = {
    "unknown_top_level_field": "W_PLAN_UNKNOWN_TOP_LEVEL_FIELD",
    "unknown_action_field": "W_PLAN_UNKNOWN_ACTION_FIELD",
    "action_string_normalized": "W_PLAN_ACTION_STRING_NORMALIZED",
}

DETERMINISTIC_ACTION_ALIASES = {
    "settings_default_sync": "settings_table_default_sync",
    "settings_table_row": "settings_table_default_sync",
    "settings_table_default_sync": "settings_table_default_sync",
    "relative_link_fix": "relative_link_fix",
    "public_doc_reference_sync": "public_doc_reference_sync",
    "doc_reference_sync": "public_doc_reference_sync",
    "public_doc_list_sync": "public_doc_reference_sync",
    "issue_template_metadata_sync": "issue_template_metadata_sync",
}

MANUAL_ONLY_ACTION_TYPES = {
    "manual_review",
    "narrative_review",
    "release_status_review",
    "investigation_review",
    "evidence_review",
    "note",
}

MANUAL_ONLY_ACTION_PREFIXES = (
    "manual_",
    "narrative_",
)

STOP_CATEGORY_SCOPES = {
    "narrative_drift_remaining": "marker-update",
    "deterministic_scope_exceeded": "apply-and-marker",
    "marker_update_without_doc_completion": "marker-update",
    "stale_marker_context": "apply-and-marker",
    "missing_required_evidence": "apply-and-marker",
}

PLAN_PHASE_FIELD_TABLES = {
    "draft_plan": {
        "top_level": {
            "required": [
                "context_id",
                "context_fingerprint",
                "overall_confidence",
                "doc_update_status",
                "allow_marker_update",
                "actions",
                "stop_reasons",
            ],
            "allowed": [
                "marker_reason",
                "selected_packets",
                "remaining_manual_reviews",
            ],
            "ignored": [],
        },
        "action": {
            "required": [
                "type",
                "summary",
            ],
            "allowed": [
                "path",
                "details",
            ],
            "ignored": [],
        },
    }
}

APPLY_CONTEXT_SNAPSHOT_FIELDS = [
    "repo_root",
    "state_file",
    "context_id",
    "context_fingerprint",
    "head_commit",
    "repo_hash",
    "repo_slug",
    "branch",
    "baseline_commit",
    "relevant_ref",
    "primary_pr_number",
    "primary_pr_url",
    "github_evidence_digest",
    "ref_selection_source",
    "audited_doc_paths",
]

PACKET_METRIC_FIELDS = [
    "packet_count",
    "packet_size_bytes",
    "largest_packet_bytes",
    "largest_two_packets_bytes",
    "estimated_local_only_tokens",
    "estimated_packet_tokens",
    "estimated_delegation_savings",
]


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
) -> dict[str, int]:
    packet_sizes = {
        name: json_bytes(payload)
        for name, payload in packet_payloads.items()
    }
    total_packet_bytes = sum(packet_sizes.values())
    largest_sizes = sorted(packet_sizes.values(), reverse=True)
    local_only_bytes = sum(json_bytes(payload) for payload in local_only_sources.values())
    estimated_local_only_tokens = estimate_tokens_from_bytes(local_only_bytes)
    estimated_packet_tokens = estimate_tokens_from_bytes(largest_sizes[0] if largest_sizes else 0)
    return {
        "packet_count": len(packet_payloads),
        "packet_size_bytes": total_packet_bytes,
        "largest_packet_bytes": largest_sizes[0] if largest_sizes else 0,
        "largest_two_packets_bytes": sum(largest_sizes[:2]),
        "estimated_local_only_tokens": estimated_local_only_tokens,
        "estimated_packet_tokens": estimated_packet_tokens,
        "estimated_delegation_savings": max(0, estimated_local_only_tokens - estimated_packet_tokens),
    }
