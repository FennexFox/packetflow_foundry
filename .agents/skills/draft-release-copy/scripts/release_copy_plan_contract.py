#!/usr/bin/env python3
"""Shared contract helpers for draft-release-copy packet/build/validate/apply flows."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import collect_release_copy_context as collect_tools

WORKFLOW_FAMILY = "release-copy"
ARCHETYPE = "audit-and-apply"
ORCHESTRATOR_PROFILE = "packet-heavy-orchestrator"
WORKER_RETURN_CONTRACT = "generic"
WORKER_OUTPUT_SHAPE = "flat"

SHARED_PACKET = "global_packet.json"
SHARED_LOCAL_PACKET = "synthesis_packet.json"
FOCUSED_PACKETS = [
    "publish_packet.json",
    "readme_packet.json",
    "changes_packet.json",
    "checklist_packet.json",
    "evidence_packet.json",
]
CANONICAL_RUNTIME_ARTIFACTS = [
    "orchestrator.json",
    SHARED_PACKET,
    "publish_packet.json",
    "readme_packet.json",
    "changes_packet.json",
    "checklist_packet.json",
    SHARED_LOCAL_PACKET,
]
CANONICAL_OPTIONAL_RUNTIME_ARTIFACTS = ["evidence_packet.json"]
CANONICAL_EVAL_ARTIFACTS = ["packet_metrics.json", "eval-log.json"]

AUTHORITY_ORDER = [
    "tracked release rules and metadata",
    "tracked runtime defaults",
    "tracked release diff since the base tag",
    "optional evidence input",
    "optional repo-relative local helper",
]

ROUTING_AUTHORITY = "packet_worker_map"
PREFERRED_WORKER_FAMILIES_ROLE = "registry_metadata_only"
DERIVED_WORKER_FIELDS = ["recommended_workers", "optional_workers"]
EXPLANATORY_WORKER_FIELDS = ["worker_selection_guidance"]

SMOKE_OUTPUT_FIELDS = [
    "status",
    "reason",
    "repo_root",
    "next_action",
]


CORE_STOP_CATEGORIES = [
    "stale_context",
    "ambiguous_routing",
    "missing_required_evidence",
    "validator_mismatch",
    "missing_auth",
    "unresolved_stop_reason",
]

LOCAL_STOP_CATEGORIES = [
    "unsupported_layout",
    "stale_issue_snapshot",
    "release_gate_incomplete",
    "rewrite_block_unsupported",
    "project_scope_required",
    "synthesis_packet_insufficient",
]

RAW_REREAD_ALLOWED_REASONS = [
    "unsupported_layout",
    "evidence_dispute",
    "issue_snapshot_conflict",
    "validator_blocker",
]

COMMON_PATH_MAX_FOCUSED_PACKETS = 1

PLAN_PHASE_FIELDS = {
    "top_level": {
        "required": [
            "context_fingerprint",
            "freshness_tuple",
            "overall_confidence",
            "stop_reasons",
            "evidence_status",
            "draft_basis",
            "publish_update",
            "readme_update",
            "issue_action",
        ],
        "allowed": [
            "context_fingerprint",
            "freshness_tuple",
            "overall_confidence",
            "stop_reasons",
            "evidence_status",
            "draft_basis",
            "publish_update",
            "readme_update",
            "issue_action",
        ],
        "ignored": [],
    },
    "draft_basis": {
        "required": [
            "common_path_sufficient",
            "raw_reread_count",
            "reread_reasons",
            "focused_packets_used",
            "compensatory_reread_detected",
        ],
        "allowed": [
            "common_path_sufficient",
            "raw_reread_count",
            "reread_reasons",
            "focused_packets_used",
            "compensatory_reread_detected",
            "synthesis_packet_fingerprint",
        ],
        "ignored": [],
    },
    "publish_update": {
        "required": ["mode"],
        "allowed": ["mode", "short_description", "long_description", "change_log", "mod_version"],
        "ignored": [],
    },
    "readme_update": {
        "required": ["mode"],
        "allowed": ["mode", "intro_text", "sections"],
        "ignored": [],
    },
    "issue_action": {
        "required": ["mode"],
        "allowed": ["mode", "title", "body_markdown", "project_mode", "project_title"],
        "ignored": [],
    },
}

VALIDATION_ERROR_CODES = {
    "missing_field": "E_RELEASE_PLAN_MISSING_FIELD",
    "invalid_mode": "E_RELEASE_PLAN_INVALID_MODE",
    "invalid_reread_reason": "E_RELEASE_PLAN_INVALID_REREAD_REASON",
    "validator_mismatch": "E_RELEASE_PLAN_VALIDATOR_MISMATCH",
    "context_fingerprint": "E_RELEASE_PLAN_CONTEXT_FINGERPRINT",
    "freshness_tuple": "E_RELEASE_PLAN_FRESHNESS_TUPLE",
    "stale_context": "E_RELEASE_PLAN_STALE_CONTEXT",
    "missing_auth": "E_RELEASE_PLAN_MISSING_AUTH",
    "stale_issue_snapshot": "E_RELEASE_PLAN_STALE_ISSUE_SNAPSHOT",
    "release_gate_incomplete": "E_RELEASE_PLAN_RELEASE_GATE_INCOMPLETE",
    "unsupported_layout": "E_RELEASE_PLAN_UNSUPPORTED_LAYOUT",
    "project_scope_required": "E_RELEASE_PLAN_PROJECT_SCOPE_REQUIRED",
    "packet_insufficient": "E_RELEASE_PLAN_PACKET_INSUFFICIENT",
}

VALIDATION_WARNING_CODES = {
    "ignored_field": "W_RELEASE_PLAN_IGNORED_FIELD",
}

SMALL_FILE_LIMIT = 8
MEDIUM_FILE_LIMIT = 20
SMALL_GROUP_LIMIT = 2
LARGE_GROUP_LIMIT = 4
CHURN_OVERRIDE_LIMIT = 400

PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["repo_mapper", "docs_verifier"],
    "candidate_producers": ["evidence_summarizer", "large_diff_auditor", "log_triager"],
    "verifiers": ["docs_verifier"],
}

PACKET_WORKER_MAP = {
    "checklist_packet": ["docs_verifier", "repo_mapper"],
    "publish_packet": ["large_diff_auditor"],
    "readme_packet": ["docs_verifier"],
    "changes_packet": ["large_diff_auditor"],
    "evidence_packet": ["evidence_summarizer"],
}

WORKER_SELECTION_GUIDANCE = {
    "routing_authority": "packet_worker_map",
    "notes": "worker_selection_guidance is explanatory only; packet_worker_map is the concrete routing source.",
    "agent_type_guidance": {
        "repo_mapper": "Use for authority order questions, packet membership, and scope mapping.",
        "docs_verifier": "Use for checklist policy, README wording, and release-policy verification.",
        "evidence_summarizer": "Use for optional evidence or validation input that needs narrow compression.",
        "large_diff_auditor": "Use for release-copy drift, changelog coverage, and broad diff review.",
        "log_triager": "Use for blocker, incident, or validation triage when the release scope touches execution evidence.",
    },
}

LOCAL_ONLY_PACKETS = {SHARED_LOCAL_PACKET, "orchestrator.json"}
SHARED_WORKER_PACKETS = {SHARED_PACKET}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def json_fingerprint(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_release_version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("v") else f"v{text}"


def expected_context_fingerprint(context: dict[str, Any]) -> str:
    payload = {key: value for key, value in context.items() if key != "context_fingerprint"}
    return json_fingerprint(payload)


def expected_freshness_tuple(context: dict[str, Any]) -> dict[str, Any]:
    return collect_tools.freshness_tuple(context)


def packet_size_bytes(payload: dict[str, Any]) -> int:
    return len((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))


def estimate_token_proxy(byte_count: int) -> int:
    if byte_count <= 0:
        return 0
    return int(math.ceil(byte_count / 4.0))


def packet_size_summary(packet_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_packet = {name: packet_size_bytes(payload) for name, payload in packet_payloads.items()}
    total = sum(by_packet.values())
    worker_facing_names = [
        name
        for name in packet_payloads
        if name not in LOCAL_ONLY_PACKETS and name != "orchestrator.json"
    ]
    worker_facing_total = sum(by_packet[name] for name in worker_facing_names)
    local_only_total = sum(by_packet[name] for name in packet_payloads if name in LOCAL_ONLY_PACKETS)
    largest = max(by_packet.values(), default=0)
    largest_two = sum(sorted(by_packet.values(), reverse=True)[:2])
    return {
        "by_packet": by_packet,
        "worker_facing_packets": worker_facing_names,
        "worker_facing_total": worker_facing_total,
        "local_only_total": local_only_total,
        "total": total,
        "largest_packet_bytes": largest,
        "largest_two_packets_bytes": largest_two,
        "packet_count": len(packet_payloads),
        "estimated_packet_tokens": estimate_token_proxy(worker_facing_total),
        "estimated_local_only_tokens": estimate_token_proxy(total),
        "estimated_delegation_savings": max(0, estimate_token_proxy(total) - estimate_token_proxy(worker_facing_total)),
    }


def packet_worker_map() -> dict[str, list[str]]:
    return {packet_name: list(agent_types) for packet_name, agent_types in PACKET_WORKER_MAP.items()}


def runtime_artifact_names(*, include_optional: bool = True) -> list[str]:
    names = list(CANONICAL_RUNTIME_ARTIFACTS)
    if include_optional:
        names.extend(CANONICAL_OPTIONAL_RUNTIME_ARTIFACTS)
    return names


def runtime_field_roles() -> dict[str, Any]:
    return {
        "routing_authority": ROUTING_AUTHORITY,
        "preferred_worker_families_role": PREFERRED_WORKER_FAMILIES_ROLE,
        "derived_worker_fields": list(DERIVED_WORKER_FIELDS),
        "explanatory_worker_fields": list(EXPLANATORY_WORKER_FIELDS),
    }
