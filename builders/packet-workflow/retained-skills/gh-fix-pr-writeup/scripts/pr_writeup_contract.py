#!/usr/bin/env python3
"""Shared contracts and helpers for gh-fix-pr-writeup."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


WORKFLOW_FAMILY = "github-review"
ARCHETYPE = "audit-and-apply"
ORCHESTRATOR_PROFILE = "packet-heavy-orchestrator"
DECISION_READY_PACKETS = False
WORKER_RETURN_CONTRACT = "generic"
WORKER_OUTPUT_SHAPE = "flat"

COMMON_PATH_REQUIRED_PACKETS = ["rules_packet.json", "synthesis_packet.json"]
COMMON_PATH_MAX_FOCUSED_PACKETS = 1
SHARED_LOCAL_PACKET = "synthesis_packet.json"

PACKET_NAMES = [
    "global_packet.json",
    "rules_packet.json",
    "runtime_packet.json",
    "process_packet.json",
    "testing_packet.json",
    "synthesis_packet.json",
]

SMALL_FILE_LIMIT = 8
MEDIUM_FILE_LIMIT = 20
SMALL_GROUP_LIMIT = 2
LARGE_GROUP_LIMIT = 4

PACKET_WORKER_MAP = {
    "runtime_packet.json": ["packet_explorer"],
    "process_packet.json": ["packet_explorer"],
    "testing_packet.json": ["evidence_summarizer"],
}

PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["packet_explorer", "docs_verifier"],
    "candidate_producers": ["evidence_summarizer", "large_diff_auditor"],
    "verifiers": ["docs_verifier"],
}

WORKER_SELECTION_GUIDANCE = {
    "routing_authority": "packet_worker_map",
    "notes": [
        "Treat packet_worker_map as the concrete routing source for delegated runtime, process, and testing packets.",
        "Keep rules_packet.json as a local-only authority source for rule text and hard constraints.",
        "Use the optional QA pass only when qa_required is true or a local conflict explicitly triggers it.",
    ],
    "agent_type_guidance": {
        "packet_explorer": "Use for one focused runtime or process packet plus only the explicitly referenced file slices needed to ground a narrow summary.",
        "docs_verifier": "Use only as a narrow rules cross-check when the local gate still leaves ambiguity.",
        "evidence_summarizer": "Use for testing claims, commands, and unsupported evidence.",
        "large_diff_auditor": "Use only for the optional QA pass after a local draft exists.",
    },
}

STANDARD_RETURN_CONTRACT = [
    "primary outcome",
    "evidence files",
    "unsupported claims",
    "suggested PR bullets",
]

QA_REQUIRED_INPUTS = [
    "global_packet.json",
    "rules_packet.json",
    "draft title",
    "draft body",
    "conflicting worker findings or specific changed files being re-checked",
]

QA_RETURN_CONTRACT = [
    "keep_or_revise",
    "rule violations",
    "coverage gaps",
    "unsupported claims",
]

RAW_REREAD_ALLOWED_REASONS = [
    "sample_omission",
    "worker_conflict",
    "claim_dispute",
    "validator_blocker",
]

QA_TRIGGER_POLICY = {
    "rare_exception_expected": True,
    "required_when": [
        "rewrite_strategy == full-rewrite and review_mode == broad-delegation",
        "worker/local findings conflict on the same claim cluster",
        "raw reread reason is worker_conflict or claim_dispute",
    ],
    "not_required_when": [
        "full_rewrite_likely alone",
        "small PR rewrite without conflicting claim evidence",
    ],
}

VALIDATION_ERROR_CODES = {
    "missing_context_field": "E_EDIT_CONTEXT_MISSING_FIELD",
    "missing_candidate_field": "E_EDIT_CANDIDATE_MISSING_FIELD",
    "candidate_lint_failed": "E_EDIT_CANDIDATE_LINT_FAILED",
    "unsupported_claims": "E_EDIT_UNSUPPORTED_CLAIMS",
    "missing_auth": "E_EDIT_MISSING_AUTH",
    "live_snapshot_unavailable": "E_EDIT_LIVE_SNAPSHOT_UNAVAILABLE",
    "stale_context": "E_EDIT_STALE_CONTEXT",
    "qa_clear_required": "E_EDIT_QA_CLEAR_REQUIRED",
    "qa_rejected": "E_EDIT_QA_REJECTED",
}

VALIDATION_WARNING_CODES = {
    "candidate_warning": "W_EDIT_CANDIDATE_WARNING",
}

CORE_STOP_CATEGORIES = [
    "stale_context",
    "ambiguous_routing",
    "missing_required_evidence",
    "validator_mismatch",
    "missing_auth",
    "unresolved_stop_reason",
]

APPLICABLE_STOP_CATEGORIES = [
    "stale_context",
    "validator_mismatch",
    "missing_auth",
    "unresolved_stop_reason",
]

LOCAL_STOP_CATEGORIES = [
    "invalid_candidate",
    "live_snapshot_unavailable",
    "unsupported_claims_detected",
    "qa_required",
]

VALIDATED_SNAPSHOT_FIELDS = [
    "title",
    "body",
    "url",
    "headRefName",
    "headRefOid",
    "baseRefName",
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

LOCAL_ONLY_PACKETS = {"synthesis_packet.json", "orchestrator.json"}
RUNTIME_PACKET_EXCLUSIONS = {"packet_metrics.json"}


def load_json(path: Any) -> dict[str, Any]:
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Any, payload: dict[str, Any]) -> None:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def json_fingerprint(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def json_bytes(payload: Any) -> int:
    return len((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))


def estimate_tokens_from_bytes(byte_count: int) -> int:
    if byte_count <= 0:
        return 0
    return int(math.ceil(byte_count / 4.0))


def compute_packet_metrics(
    packet_payloads: dict[str, Any],
    *,
    common_path_packet_names: list[str],
    raw_local_payload: Any,
) -> dict[str, Any]:
    packet_sizes = {name: json_bytes(payload) for name, payload in packet_payloads.items()}
    total_packet_bytes = sum(packet_sizes.values())
    sorted_sizes = sorted(packet_sizes.values(), reverse=True)
    common_path_bytes = sum(packet_sizes.get(name, 0) for name in common_path_packet_names)
    raw_local_bytes = json_bytes(raw_local_payload)
    return {
        "packet_count": len(packet_payloads),
        "packet_size_bytes": total_packet_bytes,
        "packet_size_by_file": packet_sizes,
        "largest_packet_bytes": sorted_sizes[0] if sorted_sizes else 0,
        "largest_two_packets_bytes": sum(sorted_sizes[:2]),
        "common_path_packet_bytes": common_path_bytes,
        "raw_local_source_bytes": raw_local_bytes,
        "estimated_local_only_tokens": estimate_tokens_from_bytes(raw_local_bytes),
        "estimated_packet_tokens": estimate_tokens_from_bytes(common_path_bytes),
        "estimated_delegation_savings": max(
            0,
            estimate_tokens_from_bytes(raw_local_bytes) - estimate_tokens_from_bytes(common_path_bytes),
        ),
    }


def stop_status() -> dict[str, Any]:
    return {
        "status": "pass",
        "applicable_stop_categories": APPLICABLE_STOP_CATEGORIES.copy(),
        "covered_stop_categories": APPLICABLE_STOP_CATEGORIES.copy(),
        "uncovered_stop_categories": [],
        "not_applicable_stop_categories": ["ambiguous_routing", "missing_required_evidence"],
        "local_stop_categories": LOCAL_STOP_CATEGORIES.copy(),
    }


def should_require_qa(
    *,
    rewrite_strategy: str,
    review_mode: str,
    worker_conflict: bool = False,
    raw_reread_reasons: list[str] | None = None,
) -> tuple[bool, str | None]:
    reasons = list(raw_reread_reasons or [])
    if worker_conflict:
        return True, "worker-local claim conflict"
    if any(reason in {"worker_conflict", "claim_dispute"} for reason in reasons):
        return True, "claim conflict requires QA cross-check"
    if rewrite_strategy == "full-rewrite" and review_mode == "broad-delegation":
        return True, "broad-delegation full rewrite requires QA cross-check"
    return False, None


def minimal_validated_snapshot(pr_payload: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
    snapshot = {field: str(pr_payload.get(field) or "").strip() for field in VALIDATED_SNAPSHOT_FIELDS}
    snapshot["changed_files"] = [str(path).replace("\\", "/") for path in changed_files]
    return snapshot
