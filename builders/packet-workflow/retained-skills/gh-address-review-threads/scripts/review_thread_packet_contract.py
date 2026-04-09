#!/usr/bin/env python3
"""Shared packet/runtime contract for gh-address-review-threads build artifacts."""

from __future__ import annotations

import json
import re
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

DELEGATION_NON_USE_CASES = {
    "runtime_routing_authority": "packet_worker_map",
    "record_only": [
        "review_mode_local_only",
        "code_change_guardrail_blockers",
        "broad_or_cross_cutting_fix_kept_local",
        "validation_path_unclear",
        "optional_qa_not_requested",
    ],
    "fatal": [],
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
    "override_policy": "build-result override_signals may widen the recommended review mode, but they must not upgrade missing evidence or ownership ambiguity into common_path_sufficient=true",
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
REQUEST_ANCHOR_RE = re.compile(r"`([^`]+)`")
IDENTIFIER_BOUNDARY_RE = r"[A-Za-z0-9_]"
REQUEST_ANCHOR_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "by",
        "change",
        "clarify",
        "consider",
        "ensure",
        "fix",
        "for",
        "from",
        "here",
        "in",
        "into",
        "it",
        "keep",
        "less",
        "make",
        "more",
        "of",
        "on",
        "or",
        "please",
        "prefer",
        "remove",
        "rename",
        "switch",
        "that",
        "the",
        "there",
        "this",
        "tighten",
        "to",
        "update",
        "use",
        "with",
    }
)


def clean_headline_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"`{3,}.*", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[*\-+>\s]+", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_~]+", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    if text in {"nit", "nits", "suggestion", "suggestions", "question", "questions", "please address"}:
        return ""
    return text


def normalize_text_for_matching(text: str | None) -> str:
    if not text:
        return ""
    normalized_lines = [clean_headline_line(line) for line in str(text).splitlines()]
    return " ".join(line for line in normalized_lines if line).strip()


def dedupe_preserve(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def canonical_match_term(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text_for_matching(text))


def canonical_match_terms(token: str) -> list[str]:
    terms: list[str] = []
    for part in re.split(r"[./-]+", token):
        candidate = part.strip(".-/")
        if len(candidate) < 3 or candidate in REQUEST_ANCHOR_STOPWORDS:
            continue
        normalized_candidate = canonical_match_term(candidate)
        if normalized_candidate:
            terms.append(normalized_candidate)
    return dedupe_preserve(terms)


def match_terms(text: str | None, *, canonical: bool = False) -> list[str]:
    normalized = normalize_text_for_matching(text)
    terms: list[str] = []
    for raw_token in re.findall(r"[a-z0-9_./-]+", normalized):
        token = raw_token.strip(".-/")
        if canonical:
            terms.extend(canonical_match_terms(token))
            continue
        if len(token) >= 3 and token not in REQUEST_ANCHOR_STOPWORDS:
            terms.append(token)
    return dedupe_preserve(terms)


def extract_exact_anchor_views(reviewer_body: str) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for match in REQUEST_ANCHOR_RE.finditer(reviewer_body):
        raw_anchor = match.group(1)
        normalized_text = normalize_text_for_matching(raw_anchor)
        if not normalized_text:
            continue

        identifier_pairs: list[tuple[str, str]] = []
        if re.search(r"[()_./-]|[A-Z]", raw_anchor):
            seen_canonical: set[str] = set()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw_anchor):
                normalized_token = token.lower()
                if len(normalized_token) < 3 or normalized_token in REQUEST_ANCHOR_STOPWORDS:
                    continue
                canonical_token = canonical_match_term(normalized_token)
                if not canonical_token or canonical_token in seen_canonical:
                    continue
                seen_canonical.add(canonical_token)
                identifier_pairs.append((normalized_token, canonical_token))

        anchors.append(
            {
                "raw": raw_anchor,
                "normalized_text": normalized_text,
                "identifier_pairs": identifier_pairs,
            }
        )
    return anchors


def boundary_aware_anchor_pattern(anchor: str, *, call_form: bool = False) -> re.Pattern[str] | None:
    normalized_anchor = str(anchor).strip()
    if not normalized_anchor:
        return None
    if call_form:
        callee = re.sub(r"\([^)]*\)", "", normalized_anchor).strip()
        if not callee:
            return None
        return re.compile(rf"(?<!{IDENTIFIER_BOUNDARY_RE}){re.escape(callee)}\s*\(")
    return re.compile(rf"(?<!{IDENTIFIER_BOUNDARY_RE}){re.escape(normalized_anchor)}(?!{IDENTIFIER_BOUNDARY_RE})")


def exact_anchor_view_matches(view: dict[str, Any], *, normalized_line_texts: list[str]) -> bool:
    normalized_anchor = str(view.get("normalized_text") or "").strip()
    raw_anchor = str(view.get("raw") or "").strip()
    if not normalized_anchor:
        return False
    if "(" in raw_anchor and ")" in raw_anchor:
        return any(normalized_anchor in line_text for line_text in normalized_line_texts)
    if any(separator in raw_anchor for separator in (".", "/", "::", "->")):
        pattern = boundary_aware_anchor_pattern(normalized_anchor)
        return bool(pattern and any(pattern.search(line_text) for line_text in normalized_line_texts))
    return any(normalized_anchor in line_text for line_text in normalized_line_texts)


def request_anchor_evidence(
    reviewer_body: str,
    *,
    snippet: str | None,
    diff_snippet: str | None,
) -> tuple[bool, list[str], list[str], list[str]]:
    visible_line_texts = _visible_evidence_line_texts(snippet=snippet, diff_snippet=diff_snippet)
    evidence_text = normalize_text_for_matching("\n".join(visible_line_texts))
    if not evidence_text:
        return False, [], [], []

    anchor_views = extract_exact_anchor_views(reviewer_body)
    exact_anchors = [str(view["normalized_text"]) for view in anchor_views]
    matched_exact_anchors = [
        str(view["normalized_text"])
        for view in anchor_views
        if exact_anchor_view_matches(view, normalized_line_texts=visible_line_texts)
    ]
    if exact_anchors:
        return bool(matched_exact_anchors), exact_anchors, matched_exact_anchors, []

    requested_terms = sorted(dict.fromkeys(match_terms(reviewer_body)))
    if len(requested_terms) < 2:
        return False, [], [], requested_terms

    evidence_terms = set(match_terms(evidence_text))
    matched_terms = [term for term in requested_terms if term in evidence_terms]
    return len(matched_terms) >= 2, [], [], matched_terms


def _visible_evidence_line_texts(
    *,
    snippet: str | None,
    diff_snippet: str | None,
) -> list[str]:
    line_texts: list[str] = []
    for raw_line in str(snippet or "").splitlines():
        cleaned_line = re.sub(r"^\s*\d+:\s*", "", raw_line)
        normalized_line = normalize_text_for_matching(cleaned_line)
        if normalized_line:
            line_texts.append(normalized_line)
    for raw_line in str(diff_snippet or "").splitlines():
        if raw_line.startswith(("+++", "---", "@@")):
            continue
        prefix = raw_line[:1]
        if prefix == "-":
            continue
        candidate_line = raw_line[1:] if prefix in {"+", " "} else raw_line
        normalized_line = normalize_text_for_matching(candidate_line)
        if normalized_line:
            line_texts.append(normalized_line)
    return line_texts


def _strong_identifier_match(
    anchor_views: list[dict[str, Any]],
    *,
    normalized_line_texts: list[str],
) -> tuple[bool, list[str], list[str]]:
    evidence_terms = set(match_terms("\n".join(normalized_line_texts), canonical=True))
    identifier_pairs = [
        pair
        for view in anchor_views
        for pair in list(view.get("identifier_pairs") or [])
        if isinstance(pair, tuple) and len(pair) == 2
    ]
    identifier_anchors = dedupe_preserve([str(raw_anchor) for raw_anchor, _ in identifier_pairs])
    matched_identifier_anchors = [
        raw_anchor
        for raw_anchor, canonical_anchor in identifier_pairs
        if canonical_anchor in evidence_terms
    ]
    line_term_sets = [set(match_terms(line_text, canonical=True)) for line_text in normalized_line_texts]
    strong_identifier_match = False
    for view in anchor_views:
        view_identifier_pairs = [
            pair
            for pair in list(view.get("identifier_pairs") or [])
            if isinstance(pair, tuple) and len(pair) == 2
        ]
        if not view_identifier_pairs:
            continue
        normalized_anchor = str(view.get("normalized_text") or "").strip()
        raw_anchor = str(view.get("raw") or "").strip()
        structural_anchor = re.sub(r"\([^)]*\)", "", normalized_anchor).strip()
        if "(" in raw_anchor and ")" in raw_anchor:
            pattern = boundary_aware_anchor_pattern(normalized_anchor, call_form=True)
            if pattern and any(pattern.search(line_text) for line_text in normalized_line_texts):
                strong_identifier_match = True
                break
            continue
        if any(separator in raw_anchor for separator in (".", "/", "::", "->")):
            pattern = boundary_aware_anchor_pattern(structural_anchor)
            if pattern and any(pattern.search(line_text) for line_text in normalized_line_texts):
                strong_identifier_match = True
                break
            continue
        required_identifier_terms = dedupe_preserve([str(canonical_anchor) for _, canonical_anchor in view_identifier_pairs])
        if (
            len(required_identifier_terms) == 1
            and any(all(term in line_terms for term in required_identifier_terms) for line_terms in line_term_sets)
        ):
            strong_identifier_match = True
            break
    return strong_identifier_match, identifier_anchors, dedupe_preserve(matched_identifier_anchors)


def delta_request_anchor_evidence(
    reviewer_body: str,
    *,
    diff_snippet: str | None,
) -> tuple[bool, list[str], list[str], list[str]]:
    added_line_texts = [
        normalize_text_for_matching(raw_line[1:])
        for raw_line in str(diff_snippet).splitlines()
        if raw_line[:1] == "+" and not raw_line.startswith("+++")
    ]
    added_line_texts = [line_text for line_text in added_line_texts if line_text]
    if not added_line_texts:
        return False, [], [], []

    anchor_views = extract_exact_anchor_views(reviewer_body)
    if not anchor_views:
        return False, [], [], []

    exact_anchors = [str(view["normalized_text"]) for view in anchor_views]
    matched_exact_anchors = [
        str(view["normalized_text"])
        for view in anchor_views
        if exact_anchor_view_matches(view, normalized_line_texts=added_line_texts)
    ]
    strong_identifier_match, identifier_anchors, matched_identifier_anchors = _strong_identifier_match(
        anchor_views,
        normalized_line_texts=added_line_texts,
    )
    return (
        bool(matched_exact_anchors or strong_identifier_match),
        matched_exact_anchors,
        identifier_anchors,
        matched_identifier_anchors,
    )


def build_grounding_diagnostics(
    reviewer_body: str,
    *,
    path: str,
    path_exists: bool,
    snippet: str | None,
    diff_snippet: str | None,
) -> dict[str, Any]:
    anchor_views = extract_exact_anchor_views(reviewer_body)
    exact_anchor_visible, exact_anchors, matched_exact_anchors, matched_terms = request_anchor_evidence(
        reviewer_body,
        snippet=snippet,
        diff_snippet=diff_snippet,
    )
    visible_line_texts = _visible_evidence_line_texts(snippet=snippet, diff_snippet=diff_snippet)
    structural_anchor_match, identifier_anchors, matched_identifier_anchors = _strong_identifier_match(
        anchor_views,
        normalized_line_texts=visible_line_texts,
    )
    grounding_mismatch = bool(anchor_views) and not exact_anchor_visible and not structural_anchor_match
    mapped_escape_reason = None
    if grounding_mismatch:
        mapped_escape_reason = "ownership_ambiguity" if (not path.strip() or not path_exists) else "missing_required_evidence"
    return {
        "has_explicit_anchor": bool(anchor_views),
        "exact_request_anchors": exact_anchors,
        "matched_exact_request_anchors": matched_exact_anchors,
        "identifier_request_anchors": identifier_anchors,
        "matched_identifier_request_anchors": matched_identifier_anchors,
        "matched_request_terms": matched_terms,
        "exact_anchor_match": bool(matched_exact_anchors),
        "structural_anchor_match": structural_anchor_match,
        "grounding_mismatch": grounding_mismatch,
        "mapped_escape_reason": mapped_escape_reason,
    }


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
    minimum_count: int = 0,
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

    def build_worker(packet_name: str, agent_type: str, index: int) -> dict[str, Any]:
        return {
            "name": f"thread-analysis-{index}",
            "agent_type": agent_type,
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

    workers: list[dict[str, Any]] = []
    used_assignments: set[tuple[str, str]] = set()
    for packet_name in analysis_packet_names[:worker_budget]:
        agent_type = packet_worker_map.get(packet_name.removesuffix(".json"), ["packet_explorer"])[0]
        workers.append(build_worker(packet_name, agent_type, len(workers) + 1))
        used_assignments.add((packet_name, agent_type))

    if minimum_count > len(workers) and analysis_packet_names:
        packet_cursor = 0
        while len(workers) < minimum_count:
            packet_name = analysis_packet_names[packet_cursor % len(analysis_packet_names)]
            candidate_agent_types = [
                *(packet_worker_map.get(packet_name.removesuffix(".json"), []) or []),
                "repo_mapper",
                "docs_verifier",
            ]
            agent_type = next(
                (
                    candidate
                    for candidate in candidate_agent_types
                    if (packet_name, candidate) not in used_assignments
                ),
                "repo_mapper",
            )
            workers.append(build_worker(packet_name, agent_type, len(workers) + 1))
            used_assignments.add((packet_name, agent_type))
            packet_cursor += 1
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
    review_mode_baseline: str,
    review_mode_adjustments: list[str],
    recommended_workers: list[dict[str, Any]],
    optional_workers: list[dict[str, Any]],
    thread_batch_count: int,
    singleton_thread_packet_count: int,
    active_paths: list[str],
    active_areas: list[str],
    analysis_targets: dict[str, int],
    thread_batches: dict[str, list[str]],
    override_signals: list[dict[str, str]],
    delegation_non_use_cases: dict[str, Any],
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
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "recommended_worker_count": len(recommended_workers),
        "recommended_workers": recommended_workers,
        "optional_worker_count": len(optional_workers),
        "optional_workers": optional_workers,
        "thread_batch_count": thread_batch_count,
        "singleton_thread_packet_count": singleton_thread_packet_count,
        "active_paths": active_paths,
        "active_areas": active_areas,
        "analysis_targets": analysis_targets,
        "thread_batches": thread_batches,
        "override_signals": override_signals,
        "delegation_non_use_cases": delegation_non_use_cases,
        "common_path_sufficient": common_path_sufficient,
        "common_path_failures": common_path_failures,
        "thread_counts": thread_counts,
        "same_run_reconciliation_enabled": same_run_reconciliation_enabled,
        "outdated_transition_candidates": outdated_transition_candidates,
        "outdated_auto_resolve_candidates": outdated_auto_resolve_candidates,
        "outdated_recheck_ambiguous": outdated_recheck_ambiguous,
        "packet_metrics_file": packet_metrics_path,
    }
