#!/usr/bin/env python3
"""Shared contracts and helpers for gh-create-pr."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


WORKFLOW_FAMILY = "github-review"
ARCHETYPE = "plan-validate-apply"
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
        "Keep rules_packet.json as the local-only authority source for template, title, and claim gates.",
        "Keep final draft synthesis local and validator/apply mutation gates local.",
    ],
    "agent_type_guidance": {
        "packet_explorer": "Use for one focused runtime or process packet plus only the explicitly referenced file slices needed to ground a narrow summary.",
        "docs_verifier": "Use only as a narrow rules cross-check when the local gate still leaves ambiguity.",
        "evidence_summarizer": "Use for testing claims, exact-command evidence, and unsupported-claim screening.",
        "large_diff_auditor": "Reserve for rare QA or broad-risk cross-checks after a local draft exists.",
    },
}

STANDARD_RETURN_CONTRACT = [
    "primary outcome",
    "evidence files",
    "unsupported claims",
    "suggested PR bullets",
]

VALIDATION_ERROR_CODES = {
    "missing_context_field": "E_CREATE_CONTEXT_MISSING_FIELD",
    "missing_candidate_field": "E_CREATE_CANDIDATE_MISSING_FIELD",
    "invalid_title": "E_CREATE_INVALID_TITLE",
    "invalid_body": "E_CREATE_INVALID_BODY",
    "unsupported_claim": "E_CREATE_UNSUPPORTED_CLAIM",
    "missing_auth": "E_CREATE_MISSING_AUTH",
    "repo_inference_failed": "E_CREATE_REPO_INFERENCE_FAILED",
    "base_resolution_failed": "E_CREATE_BASE_RESOLUTION_FAILED",
    "template_not_found": "E_CREATE_TEMPLATE_NOT_FOUND",
    "template_ambiguous": "E_CREATE_TEMPLATE_AMBIGUOUS",
    "remote_head_missing": "E_CREATE_REMOTE_HEAD_MISSING",
    "head_oid_mismatch": "E_CREATE_HEAD_OID_MISMATCH",
    "existing_open_pr": "E_CREATE_EXISTING_OPEN_PR",
    "live_snapshot_unavailable": "E_CREATE_LIVE_SNAPSHOT_UNAVAILABLE",
    "stale_snapshot": "E_CREATE_STALE_SNAPSHOT",
    "fingerprint_mismatch": "E_CREATE_FINGERPRINT_MISMATCH",
    "apply_verification_failed": "E_CREATE_APPLY_VERIFICATION_FAILED",
}

VALIDATION_WARNING_CODES = {
    "candidate_warning": "W_CREATE_CANDIDATE_WARNING",
}

CORE_STOP_CATEGORIES = [
    "missing_auth",
    "repo_inference_failed",
    "base_resolution_failed",
    "template_not_found",
    "template_ambiguous",
    "remote_head_missing",
    "head_oid_mismatch",
    "existing_open_pr",
    "invalid_title",
    "invalid_body",
    "unsupported_claim",
    "stale_snapshot",
    "fingerprint_mismatch",
    "apply_verification_failed",
    "validator_mismatch",
    "live_snapshot_unavailable",
    "unresolved_stop_reason",
]

APPLICABLE_STOP_CATEGORIES = [
    "missing_auth",
    "repo_inference_failed",
    "base_resolution_failed",
    "template_not_found",
    "template_ambiguous",
    "remote_head_missing",
    "head_oid_mismatch",
    "existing_open_pr",
    "stale_snapshot",
    "fingerprint_mismatch",
    "apply_verification_failed",
    "validator_mismatch",
    "unresolved_stop_reason",
]

LOCAL_STOP_CATEGORIES = [
    "invalid_title",
    "invalid_body",
    "unsupported_claim",
    "live_snapshot_unavailable",
]

VALIDATED_SNAPSHOT_FIELDS = [
    "local_head_oid",
    "remote_head_oid",
    "repo_slug",
    "base_ref",
    "head_ref",
    "changed_files_fingerprint",
    "template_path",
    "template_fingerprint",
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


def normalize_scalar(value: Any) -> str:
    return str(value or "").strip()


def normalize_path(value: Any) -> str:
    return normalize_scalar(value).replace("\\", "/")


def normalize_string_list(values: Any, *, casefold: bool = False, sort_values: bool = True) -> list[str]:
    items: list[str] = []
    if isinstance(values, list):
        raw_items = values
    elif values is None:
        raw_items = []
    else:
        raw_items = [values]
    for item in raw_items:
        text = normalize_scalar(item)
        if not text:
            continue
        if casefold:
            text = text.lower()
        items.append(text)
    deduped = list(dict.fromkeys(items))
    return sorted(deduped) if sort_values else deduped


def normalize_duplicate_summary(summary: Any) -> dict[str, Any]:
    payload = summary if isinstance(summary, dict) else {}
    number = payload.get("existing_pr_number")
    count = payload.get("existing_pr_count")
    return {
        "status": normalize_scalar(payload.get("status")) or "unknown",
        "matched_repo_slug": normalize_scalar(payload.get("matched_repo_slug")),
        "matched_head": normalize_scalar(payload.get("matched_head")),
        "existing_pr_number": int(number) if isinstance(number, int) or str(number).isdigit() else None,
        "existing_pr_url": normalize_scalar(payload.get("existing_pr_url")) or None,
        "existing_pr_count": int(count) if isinstance(count, int) or str(count).isdigit() else 0,
    }


def duplicate_summary_is_clear(summary: Any) -> bool:
    return normalize_duplicate_summary(summary).get("status") == "clear"


def build_validated_snapshot(context: dict[str, Any], duplicate_summary: dict[str, Any]) -> dict[str, Any]:
    template_selection = context.get("template_selection") or {}
    return {
        "local_head_oid": normalize_scalar(context.get("local_head_oid")),
        "remote_head_oid": normalize_scalar(context.get("remote_head_oid")),
        "repo_slug": normalize_scalar(context.get("repo_slug")),
        "base_ref": normalize_scalar(context.get("resolved_base")),
        "head_ref": normalize_scalar(context.get("resolved_head")),
        "changed_files_fingerprint": normalize_scalar(context.get("changed_files_fingerprint")),
        "template_path": normalize_path(template_selection.get("selected_path")),
        "template_fingerprint": normalize_scalar(template_selection.get("fingerprint")),
        "duplicate_check_summary": normalize_duplicate_summary(duplicate_summary),
    }


def snapshot_mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for field in VALIDATED_SNAPSHOT_FIELDS:
        expected_value = normalize_scalar(expected.get(field)) if field != "template_path" else normalize_path(expected.get(field))
        actual_value = normalize_scalar(actual.get(field)) if field != "template_path" else normalize_path(actual.get(field))
        if expected_value != actual_value:
            mismatches.append({"field": field, "expected": expected_value, "actual": actual_value})

    expected_duplicate = normalize_duplicate_summary(expected.get("duplicate_check_summary"))
    actual_duplicate = normalize_duplicate_summary(actual.get("duplicate_check_summary"))
    if json_fingerprint(expected_duplicate) != json_fingerprint(actual_duplicate):
        mismatches.append(
            {
                "field": "duplicate_check_summary",
                "expected": expected_duplicate,
                "actual": actual_duplicate,
            }
        )
    return mismatches


def stop_status() -> dict[str, Any]:
    return {
        "status": "pass",
        "applicable_stop_categories": APPLICABLE_STOP_CATEGORIES.copy(),
        "covered_stop_categories": APPLICABLE_STOP_CATEGORIES.copy(),
        "uncovered_stop_categories": [],
        "not_applicable_stop_categories": [],
        "local_stop_categories": LOCAL_STOP_CATEGORIES.copy(),
    }
