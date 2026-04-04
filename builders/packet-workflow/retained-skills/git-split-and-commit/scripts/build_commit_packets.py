#!/usr/bin/env python3
"""Build compact packet artifacts for token-efficient commit planning."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from commit_packet_contract import (
    COMMON_PATH_CONTRACT,
    DECISION_READY_PACKETS,
    ORCHESTRATOR_PROFILE,
    PACKET_NAMES,
    PREFERRED_WORKER_FAMILIES,
    RAW_REREAD_ALLOWED_REASONS,
    WORKER_OUTPUT_SHAPE,
    WORKER_RETURN_CONTRACT,
    WORKER_SELECTION_GUIDANCE,
    XHIGH_REREAD_POLICY,
    build_packet_worker_map,
    build_task_packet_names,
    compute_packet_metrics,
    dedupe_preserve,
    packet_basename,
)


LOCAL_FILE_LIMIT = 8
LOCAL_BATCH_LIMIT = 2
TARGETED_BATCH_LIMIT = 4
BROAD_FILE_LIMIT = 20
CHURN_OVERRIDE_LIMIT = 300
GENERATED_FILE_OVERRIDE_RATIO = 0.5
DELEGATION_SAVINGS_FLOOR = 250


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_shortstat(shortstat: str | None) -> dict[str, int]:
    if not shortstat:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "churn": 0}
    files = re.search(r"(\d+)\s+files?\s+changed", shortstat)
    insertions = re.search(r"(\d+)\s+insertions?\(\+\)", shortstat)
    deletions = re.search(r"(\d+)\s+deletions?\(-\)", shortstat)
    file_count = int(files.group(1)) if files else 0
    added = int(insertions.group(1)) if insertions else 0
    removed = int(deletions.group(1)) if deletions else 0
    return {
        "files_changed": file_count,
        "insertions": added,
        "deletions": removed,
        "churn": added + removed,
    }


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def candidate_scopes(files: list[dict[str, Any]], rules: dict[str, Any]) -> list[str]:
    known_scopes = list(rules.get("recent_scope_vocabulary", [])) + list(
        rules.get("rules", {}).get("scope_suggestions", [])
    )
    candidates: list[str] = []
    seen: set[str] = set()
    for entry in files:
        path = normalize_path(str(entry["path"])).lower()
        derived = None
        if "/systems/" in path:
            derived = "systems"
        elif "/patches/" in path:
            derived = "patches"
        elif path.startswith(".github/"):
            derived = "infra"
        elif path.endswith(".md") or path.startswith("docs/"):
            derived = "docs"
        elif path.endswith((".yml", ".yaml", ".json", ".toml", ".xml")):
            derived = "config"
        elif "/tests/" in path or path.endswith("_test.py"):
            derived = "test"
        if derived and derived not in seen:
            candidates.append(derived)
            seen.add(derived)
    for scope in known_scopes:
        if scope in seen:
            continue
        if any(scope.lower() in normalize_path(str(entry["path"])).lower() for entry in files):
            candidates.append(scope)
            seen.add(scope)
    return candidates[:6]


def feature_tokens(entry: dict[str, Any]) -> list[str]:
    tokens = list(entry.get("path_tokens", []))
    for hunk in entry.get("hunks", []):
        for token in hunk.get("tokens", []):
            if token not in tokens:
                tokens.append(token)
    return tokens[:20]


def source_test_partner(path: str) -> str | None:
    normalized = normalize_path(path)
    if normalized.startswith(".github/scripts/tests/test_") and normalized.endswith(".py"):
        stem = Path(normalized).stem.removeprefix("test_")
        return f".github/scripts/{stem}.py"
    if normalized.startswith(".github/scripts/") and normalized.endswith(".py") and not normalized.startswith(".github/scripts/tests/"):
        return f".github/scripts/tests/test_{Path(normalized).stem}.py"
    return None


def token_overlap(entry_a: dict[str, Any], entry_b: dict[str, Any]) -> int:
    return len(set(feature_tokens(entry_a)) & set(feature_tokens(entry_b)))


def adjacency_score(entry_a: dict[str, Any], entry_b: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    path_a = normalize_path(str(entry_a["path"]))
    path_b = normalize_path(str(entry_b["path"]))
    if source_test_partner(path_a) == path_b or source_test_partner(path_b) == path_a:
        score += 5
        reasons.append("source_test_adjacency")

    overlap = token_overlap(entry_a, entry_b)
    if overlap >= 2:
        score += 3
        reasons.append("feature_token_overlap")
    elif overlap == 1 and (
        str(entry_a.get("area")) in {"docs", "config", "other"}
        or str(entry_b.get("area")) in {"docs", "config", "other"}
    ):
        score += 2
        reasons.append("supporting_token_overlap")

    parent_a = path_a.rsplit("/", 1)[0] if "/" in path_a else "."
    parent_b = path_b.rsplit("/", 1)[0] if "/" in path_b else "."
    if parent_a == parent_b and parent_a != ".":
        score += 1
        reasons.append("same_directory")

    return score, reasons


def connected_components(files: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not files:
        return []
    index_to_neighbors: dict[int, set[int]] = {index: set() for index in range(len(files))}
    for left in range(len(files)):
        for right in range(left + 1, len(files)):
            score, _ = adjacency_score(files[left], files[right])
            if score >= 3:
                index_to_neighbors[left].add(right)
                index_to_neighbors[right].add(left)

    visited: set[int] = set()
    components: list[list[dict[str, Any]]] = []
    for index in range(len(files)):
        if index in visited:
            continue
        queue = [index]
        visited.add(index)
        members: list[int] = []
        while queue:
            current = queue.pop()
            members.append(current)
            for neighbor in index_to_neighbors[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        component = [files[item] for item in sorted(members, key=lambda value: str(files[value]["path"]))]
        components.append(component)
    components.sort(key=lambda batch: str(batch[0]["path"]))
    return components


def dominant_type(batch: list[dict[str, Any]]) -> str:
    areas = {str(entry.get("area")) for entry in batch}
    if areas <= {"docs", "config", "other"} and "docs" in areas:
        return "docs"
    if areas == {"tests"}:
        return "test"
    if "runtime" in areas or "automation" in areas:
        return "fix"
    if "config" in areas:
        return "chore"
    return "fix"


def body_needed(batch: list[dict[str, Any]]) -> bool:
    return len(batch) > 1 or any(entry.get("split_eligible") for entry in batch)


def hunk_overlap_ratio(hunks: list[dict[str, Any]]) -> float:
    if len(hunks) < 2:
        return 1.0
    scores: list[float] = []
    for left in range(len(hunks)):
        left_tokens = set(hunks[left].get("tokens", []))
        for right in range(left + 1, len(hunks)):
            right_tokens = set(hunks[right].get("tokens", []))
            union = left_tokens | right_tokens
            scores.append((len(left_tokens & right_tokens) / len(union)) if union else 1.0)
    return sum(scores) / len(scores) if scores else 1.0


def split_candidate_packet(entry: dict[str, Any], batch_size: int) -> dict[str, Any] | None:
    hunks = list(entry.get("hunks", []))
    if not entry.get("split_eligible") or len(hunks) < 2:
        return None
    area = str(entry.get("area"))
    path = normalize_path(str(entry.get("path")))
    if area not in {"runtime", "automation", "tests"}:
        return None
    if path.startswith(".github/ISSUE_TEMPLATE/") or path.endswith(".md"):
        return None
    sorted_hunks = sorted(hunks, key=lambda item: (int(item["old_start"]), int(item["new_start"])))
    line_span = max(int(hunk["new_start"]) for hunk in sorted_hunks) - min(int(hunk["new_start"]) for hunk in sorted_hunks)
    average_overlap = hunk_overlap_ratio(sorted_hunks)
    digest_pairs = [(str(hunk["removed_digest"]), str(hunk["added_digest"])) for hunk in sorted_hunks]
    duplicate_digest_pairs = len(digest_pairs) != len(set(digest_pairs))
    should_inspect = duplicate_digest_pairs or (
        batch_size == 1
        and len(hunks) >= 4
        and line_span >= 250
        and average_overlap < 0.15
        and area in {"runtime", "automation"}
    )
    if not should_inspect:
        return None

    return {
        "path": entry["path"],
        "reason": {
            "line_span": line_span,
            "average_hunk_token_overlap": round(average_overlap, 3),
            "duplicate_digest_pairs": duplicate_digest_pairs,
        },
        "hunks": [
            {
                "hunk_id": hunk["hunk_id"],
                "header": hunk["header"],
                "tokens": hunk.get("tokens", []),
                "removed_digest": hunk["removed_digest"],
                "added_digest": hunk["added_digest"],
            }
            for hunk in sorted_hunks
        ],
    }


def override_signals(files: list[dict[str, Any]], diff_totals: dict[str, int]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    if diff_totals.get("churn", 0) >= CHURN_OVERRIDE_LIMIT:
        signals.append(
            {
                "reason": "diff_stat_threshold",
                "detail": f"Tracked diff churn reached {diff_totals['churn']} lines (threshold {CHURN_OVERRIDE_LIMIT}).",
            }
        )

    batch_areas = sorted({str(entry.get("area")) for entry in files if str(entry.get("area")) in {"runtime", "automation", "config"}})
    if len(batch_areas) >= 2:
        signals.append(
            {
                "reason": "core_files_across_groups",
                "detail": "Core runtime/config/process files span multiple groups: " + ", ".join(batch_areas),
            }
        )

    generated_count = sum(1 for entry in files if entry.get("generated"))
    if files and generated_count and (generated_count / len(files)) < GENERATED_FILE_OVERRIDE_RATIO:
        signals.append(
            {
                "reason": "generated_files_not_majority",
                "detail": f"Generated files are present but not the majority ({generated_count}/{len(files)}).",
            }
        )
    return signals


def determine_baseline_review_mode(
    file_count: int,
    batch_count: int,
    split_count: int,
) -> tuple[str, int]:
    if file_count <= LOCAL_FILE_LIMIT and batch_count <= LOCAL_BATCH_LIMIT and split_count == 0:
        review_mode = "local-only"
    elif batch_count >= 5 or file_count > BROAD_FILE_LIMIT:
        review_mode = "broad-delegation"
    elif batch_count >= 3 or split_count > 0:
        review_mode = "targeted-delegation"
    else:
        review_mode = "local-only"
    if review_mode == "local-only":
        return review_mode, 0
    if review_mode == "targeted-delegation":
        return review_mode, 2
    return review_mode, 4 if batch_count > TARGETED_BATCH_LIMIT else 3


def apply_override_adjustment(
    review_mode: str,
    worker_count: int,
    batch_count: int,
    split_count: int,
    overrides: list[dict[str, str]],
) -> tuple[str, int, list[str]]:
    override_reasons = {str(item.get("reason", "")) for item in overrides}
    adjustments: list[str] = []
    if overrides and review_mode == "local-only":
        if batch_count > 1 or split_count > 0 or "diff_stat_threshold" in override_reasons:
            review_mode = "targeted-delegation"
            worker_count = 2
            adjustments.append("override_signal")
    elif overrides and review_mode == "targeted-delegation":
        if batch_count > TARGETED_BATCH_LIMIT or split_count > 1 or "diff_stat_threshold" in override_reasons:
            review_mode = "broad-delegation"
            worker_count = 4 if batch_count > TARGETED_BATCH_LIMIT else 3
            adjustments.append("override_signal")
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


def packet_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index:02d}.json"


def summarize_changed_lines(lines: list[str], *, limit: int = 4) -> list[str]:
    preview: list[str] = []
    for line in lines:
        if not line.startswith(("+", "-")):
            continue
        payload = line[1:].strip()
        if not payload:
            continue
        candidate = f"{line[0]} {payload[:140]}"
        if candidate not in preview:
            preview.append(candidate)
        if len(preview) >= limit:
            break
    return preview


def representative_hunk_headers(entry: dict[str, Any], *, limit: int = 3) -> list[str]:
    return [str(hunk.get("header", "")) for hunk in entry.get("hunks", [])[:limit] if str(hunk.get("header", "")).strip()]


def file_change_synopsis(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "insertions": entry.get("insertions"),
        "deletions": entry.get("deletions"),
        "diff_header_text": entry.get("diff_header_text", ""),
        "hunk_headers": representative_hunk_headers(entry),
        "representative_tokens": feature_tokens(entry)[:8],
        "changed_line_preview": summarize_changed_lines(
            [line for hunk in entry.get("hunks", []) for line in hunk.get("raw_body_lines", [])]
        ),
    }


def validation_candidate_map(validation_candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    for item in validation_candidates:
        command = str(item.get("command") or "").strip()
        if not command:
            continue
        payload = {
            "command": command,
            "reason": item.get("reason"),
            "confidence": item.get("confidence"),
        }
        for path in item.get("paths", []):
            mapping.setdefault(str(path), []).append(payload)
    return mapping


def single_file_basis(entry: dict[str, Any]) -> list[dict[str, Any]]:
    basis = [
        {
            "kind": "single_file_scope",
            "paths": [str(entry["path"])],
            "detail": "The batch contains one changed file, so commit cohesion is file-bounded.",
        }
    ]
    partner = source_test_partner(str(entry["path"]))
    if partner:
        basis.append(
            {
                "kind": "source_test_pair",
                "paths": [str(entry["path"]), partner],
                "detail": "The file has a conventional source/test partner and should stay grouped with that companion change when both appear.",
            }
        )
    return basis


def batch_cohesion_basis(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not batch:
        return []
    if len(batch) == 1:
        return single_file_basis(batch[0])

    basis: list[dict[str, Any]] = []
    for left in range(len(batch)):
        for right in range(left + 1, len(batch)):
            score, reasons = adjacency_score(batch[left], batch[right])
            if score < 3:
                continue
            detail_parts = []
            if "source_test_adjacency" in reasons:
                detail_parts.append("source/test adjacency")
            if "feature_token_overlap" in reasons:
                detail_parts.append("shared feature tokens")
            if "supporting_token_overlap" in reasons:
                detail_parts.append("supporting token overlap")
            if "same_directory" in reasons:
                detail_parts.append("same directory")
            basis.append(
                {
                    "kind": "adjacency_signal",
                    "paths": [str(batch[left]["path"]), str(batch[right]["path"])],
                    "score": score,
                    "reasons": reasons,
                    "detail": ", ".join(detail_parts) if detail_parts else "grouping signal detected",
                }
            )
    return basis


def batch_boundary_risks(
    batch: list[dict[str, Any]],
    split_paths: list[str],
    relevant_commands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    areas = sorted({str(entry.get("area")) for entry in batch})
    if len(areas) > 1:
        risks.append(
            {
                "risk": "mixed_areas",
                "detail": "The batch spans multiple areas: " + ", ".join(areas),
            }
        )
    if split_paths:
        risks.append(
            {
                "risk": "split_candidate_present",
                "detail": "One or more files may need split adjudication before the batch is safe to apply.",
                "paths": split_paths,
            }
        )
    if not relevant_commands:
        risks.append(
            {
                "risk": "no_targeted_validation",
                "detail": "No targeted validation command was matched to this batch.",
            }
        )
    generated = [str(entry["path"]) for entry in batch if entry.get("generated")]
    if generated and len(generated) != len(batch):
        risks.append(
            {
                "risk": "generated_and_handwritten_mix",
                "detail": "Generated files are mixed with handwritten files in the same batch.",
                "paths": generated,
            }
        )
    return risks


def batch_coverage_gaps(
    batch: list[dict[str, Any]],
    split_paths: list[str],
    relevant_commands: list[dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    if split_paths:
        gaps.append("Resolve split-file packets before treating the batch as whole-file safe.")
    if not relevant_commands:
        gaps.append("No targeted validation command was matched to this batch.")
    if any(entry.get("binary") for entry in batch):
        gaps.append("Binary files limit patch-level evidence; rely on whole-file handling only.")
    return gaps


def batch_quality_escape_hints(batch: list[dict[str, Any]], split_paths: list[str]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    if len(batch) <= 1:
        return hints
    cohesion = batch_cohesion_basis(batch)
    strong_reasons = {
        reason
        for item in cohesion
        for reason in item.get("reasons", [])
        if reason != "same_directory"
    }
    if not strong_reasons and split_paths:
        hints.append(
            {
                "reason": "conflicting_signals",
                "detail": "The batch groups multiple files without strong cross-file evidence beyond directory locality, and a split candidate is present.",
                "paths": split_paths,
                "common_path_blocking": False,
            }
        )
    return hints


def batch_whole_file_recommendation(split_paths: list[str]) -> dict[str, Any]:
    if split_paths:
        return {
            "mode": "defer-to-split-packet",
            "detail": "Keep the batch whole-file by default unless the matching split-file packet gives clear multi-intent support.",
            "paths": split_paths,
        }
    return {
        "mode": "whole-file",
        "detail": "No split candidates were identified in this batch.",
        "paths": [],
    }


def hunk_preview_quality(hunk: dict[str, Any]) -> dict[str, Any]:
    preview = summarize_changed_lines(list(hunk.get("raw_body_lines", [])))
    tokens = [str(token) for token in hunk.get("tokens", []) if str(token).strip()]
    return {
        "preview_lines": preview,
        "preview_count": len(preview),
        "token_count": len(tokens),
        "tokens": tokens[:8],
    }


def split_decision_basis(packet: dict[str, Any]) -> dict[str, Any]:
    hunks = list(packet.get("hunks", []))
    hunk_summaries: list[dict[str, Any]] = []
    adjacent_hunks = False
    last_new_start: int | None = None
    for hunk in hunks:
        quality = hunk_preview_quality(hunk)
        new_start = int(hunk.get("new_start", 0))
        if last_new_start is not None and abs(new_start - last_new_start) <= 12:
            adjacent_hunks = True
        last_new_start = new_start
        hunk_summaries.append(
            {
                "hunk_id": hunk.get("hunk_id"),
                "header": hunk.get("header"),
                "tokens": quality["tokens"],
                "preview_lines": quality["preview_lines"],
                "removed_digest": hunk.get("removed_digest"),
                "added_digest": hunk.get("added_digest"),
            }
        )
    reason = dict(packet.get("reason") or {})
    return {
        "line_span": reason.get("line_span"),
        "average_hunk_token_overlap": reason.get("average_hunk_token_overlap"),
        "duplicate_digest_pairs": bool(reason.get("duplicate_digest_pairs")),
        "adjacent_hunks_detected": adjacent_hunks,
        "hunk_summaries": hunk_summaries,
    }


def split_adjacent_hunk_risk(packet: dict[str, Any]) -> dict[str, Any]:
    basis = split_decision_basis(packet)
    adjacent = bool(basis.get("adjacent_hunks_detected"))
    return {
        "present": adjacent,
        "level": "medium" if adjacent else "low",
        "detail": "Neighboring hunks sit close together; prefer whole-file unless the intent boundary stays clear." if adjacent else "No close hunk adjacency was detected.",
    }


def split_rematch_risk(packet: dict[str, Any]) -> dict[str, Any]:
    duplicate = bool((packet.get("reason") or {}).get("duplicate_digest_pairs"))
    return {
        "present": duplicate,
        "level": "high" if duplicate else "low",
        "detail": "Duplicate digest pairs reduce rematch confidence and increase ambiguous hunk risk." if duplicate else "Hunk digests remain distinct enough for rematch.",
    }


def split_quality_escape_hints(packet: dict[str, Any]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    duplicate = bool((packet.get("reason") or {}).get("duplicate_digest_pairs"))
    empty_preview = any(
        not hunk_preview_quality(hunk)["preview_count"] and not hunk_preview_quality(hunk)["token_count"]
        for hunk in packet.get("hunks", [])
    )
    if duplicate and empty_preview:
        hints.append(
            {
                "reason": "insufficient_excerpt_quality",
                "detail": "A split candidate has duplicate digest pairs but no preview or token evidence, so packet-only adjudication is insufficient.",
                "paths": [str(packet.get("path"))],
                "common_path_blocking": True,
            }
        )
    elif duplicate:
        hints.append(
            {
                "reason": "ambiguous_hunk_match",
                "detail": "Duplicate digest pairs remain a quality escape hatch if the packet evidence is still inconclusive.",
                "paths": [str(packet.get("path"))],
                "common_path_blocking": False,
            }
        )
    return hints


def aggregate_quality_escape_hints(*hint_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    for hint_list in hint_lists:
        for item in hint_list:
            reason = str(item.get("reason") or "")
            paths = tuple(str(path) for path in item.get("paths", []) if str(path).strip())
            detail = str(item.get("detail") or "")
            key = (reason, paths, detail)
            if not reason or key in seen:
                continue
            seen.add(key)
            aggregated.append(item)
    return aggregated


def build_result_payload(
    *,
    review_mode: str,
    review_mode_baseline: str,
    review_mode_adjustments: list[str],
    recommended_workers: list[dict[str, Any]],
    packet_order: list[str],
    active_packets: list[str],
    applied_override_signals: list[str],
    candidate_batch_count: int,
    split_file_count: int,
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
        "packet_order": packet_order,
        "active_packets": active_packets,
        "active_packet_count": len(active_packets),
        "candidate_batch_count": candidate_batch_count,
        "split_file_count": split_file_count,
        "applied_override_signals": applied_override_signals,
        "common_path_sufficient": common_path_sufficient,
        "raw_reread_count": len(raw_reread_reasons),
        "raw_reread_reasons": raw_reread_reasons,
        "packet_metrics": packet_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build packet artifacts for token-efficient commit planning."
    )
    parser.add_argument("--rules", type=Path, required=True, help="Path to rules JSON from collect_commit_rules.py")
    parser.add_argument("--worktree", type=Path, required=True, help="Path to worktree JSON from collect_worktree_context.py")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated packets")
    parser.add_argument("--result-output", type=Path, help="Optional path to write build result JSON.")
    args = parser.parse_args()

    rules = load_json(args.rules)
    worktree = load_json(args.worktree)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(list(worktree.get("files", [])), key=lambda item: str(item["path"]))
    changed_paths = [str(entry["path"]) for entry in files]
    diff_totals = parse_shortstat(worktree.get("diff_shortstat"))
    overrides = override_signals(files, diff_totals)
    batches = connected_components(files)
    split_packets: list[dict[str, Any]] = []
    batch_size_by_path = {
        str(entry["path"]): len(batch)
        for batch in batches
        for entry in batch
    }
    for entry in files:
        packet = split_candidate_packet(entry, batch_size_by_path.get(str(entry["path"]), 1))
        if packet is not None:
            split_packets.append(packet)

    review_mode_baseline, worker_count = determine_baseline_review_mode(
        file_count=len(files),
        batch_count=len(batches),
        split_count=len(split_packets),
    )
    review_mode, worker_count, review_mode_adjustments = apply_override_adjustment(
        review_mode_baseline,
        worker_count,
        len(batches),
        len(split_packets),
        overrides,
    )

    worker_selection_guidance = {
        **WORKER_SELECTION_GUIDANCE,
        "notes": (
            "Keep workers narrow: rules_packet for hard commit-message constraints, worktree_packet for touched-surface facts, "
            "candidate batches for logical commit buckets, and split-file packets for split adjudication."
        ),
    }
    candidate_field_bundles = [
        {
            "name": "candidate",
            "description": "Proposal-grade commit bucket candidate data.",
            "required": True,
            "fields": [
                "fact_summary",
                "proposal_classification",
                "classification_rationale",
                "supporting_references",
                "ambiguity",
                "confidence",
                "reread_control",
            ],
        }
    ]
    worker_footer_fields = [
        "packet_ids",
        "candidate_ids",
        "primary_outcome",
        "overall_confidence",
        "coverage_gaps",
        "overall_risk",
    ]
    domain_overlay = {
        "proposal_enum_values": ["commit_bucket", "split_file", "reference_only", "ignore"],
        "candidate_field_aliases": {
            "fact_summary": "intent_summary",
            "proposal_classification": "recommended_type",
            "supporting_references": "supporting_paths",
            "ambiguity": "open_ambiguity",
            "reread_control": "raw_reread_reason",
        },
        "alias_notes": {
            "supporting_paths": (
                "Current domain aliases assume file/path-oriented evidence first; "
                "`supporting_paths` is evidence-only and does not claim path ownership."
            ),
        },
        "reference_only_candidate_values": ["reference_only"],
        "output_inclusion_rules": {
            "commit_bucket": "standalone",
            "split_file": "standalone",
            "reference_only": "support",
            "ignore": "exclude",
        },
        "bundle_overrides": {},
    }

    rules_packet = {
        "purpose": "Extract hard commit-message rules and preferred scope vocabulary.",
        "rule_files": rules.get("rule_files", {}),
        "rules": rules.get("rules", {}),
        "rule_derivation": rules.get("rule_derivation", {}),
        "recent_scope_vocabulary": rules.get("recent_scope_vocabulary", []),
        "recent_subject_samples": rules.get("recent_subject_samples", []),
        "instruction_snippets": rules.get("instruction_snippets", {}),
    }

    batch_map: dict[str, list[str]] = {}
    candidate_batch_names: list[str] = []
    candidate_payloads: dict[str, dict[str, Any]] = {}
    candidate_quality_hints: list[dict[str, Any]] = []
    validation_map = validation_candidate_map(list(worktree.get("validation_candidates", [])))
    for index, batch in enumerate(batches, start=1):
        batch_name = packet_name("candidate-batch", index)
        candidate_batch_names.append(batch_name)
        batch_id = packet_basename(batch_name)
        batch_map[batch_id] = [str(entry["path"]) for entry in batch]
        split_paths = [str(entry["path"]) for entry in batch if any(packet["path"] == entry["path"] for packet in split_packets)]
        relevant_commands = [
            item
            for item in worktree.get("validation_candidates", [])
            if set(item.get("paths", [])) & {str(entry["path"]) for entry in batch}
        ]
        cohesion_basis = batch_cohesion_basis(batch)
        boundary_risks = batch_boundary_risks(batch, split_paths, relevant_commands)
        coverage_gaps = batch_coverage_gaps(batch, split_paths, relevant_commands)
        quality_escape_hints = batch_quality_escape_hints(batch, split_paths)
        candidate_quality_hints.extend(quality_escape_hints)
        batch_packet = {
            "purpose": "Describe one logical commit candidate from the current working tree.",
            "batch_id": batch_id,
            "paths": [str(entry["path"]) for entry in batch],
            "areas": sorted({str(entry.get("area")) for entry in batch}),
            "intent_tokens": sorted({token for entry in batch for token in feature_tokens(entry)})[:20],
            "recommended_type": dominant_type(batch),
            "scope_candidates": candidate_scopes(batch, rules),
            "body_needed": body_needed(batch),
            "split_candidate_paths": split_paths,
            "cohesion_basis": cohesion_basis,
            "boundary_risks": boundary_risks,
            "whole_file_recommendation": batch_whole_file_recommendation(split_paths),
            "supporting_validation_commands": relevant_commands,
            "coverage_gaps": coverage_gaps,
            "quality_escape_hints": quality_escape_hints,
            "validation_candidates": relevant_commands,
            "files": [
                {
                    "path": entry["path"],
                    "change_kind": entry["change_kind"],
                    "area": entry["area"],
                    "generated": entry["generated"],
                    "binary": entry.get("binary"),
                    "split_eligible": entry.get("split_eligible"),
                    "hunk_count": len(entry.get("hunks", [])),
                    "change_synopsis": file_change_synopsis(entry),
                    "validation_candidates": validation_map.get(str(entry["path"]), []),
                }
                for entry in batch
            ],
        }
        candidate_payloads[batch_name] = batch_packet
        (output_dir / batch_name).write_text(
            json.dumps(batch_packet, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    split_packet_names: list[str] = []
    split_payloads: dict[str, dict[str, Any]] = {}
    split_quality_hints: list[dict[str, Any]] = []
    for index, packet in enumerate(split_packets, start=1):
        packet_name_value = packet_name("split-file", index)
        split_packet_names.append(packet_name_value)
        split_hints = split_quality_escape_hints(packet)
        split_quality_hints.extend(split_hints)
        payload = {
            "purpose": "Inspect whether one modified file should stay whole or split across commits.",
            "file": packet,
            "split_decision_basis": split_decision_basis(packet),
            "adjacent_hunk_risk": split_adjacent_hunk_risk(packet),
            "rematch_risk": split_rematch_risk(packet),
            "whole_file_fallback_guidance": {
                "mode": "prefer_whole_file_on_ambiguity",
                "detail": "If the hunk intent boundary stays ambiguous after packet review, keep the file whole or stop instead of improvising a split.",
            },
            "quality_escape_hints": split_hints,
        }
        split_payloads[packet_name_value] = payload
        (output_dir / packet_name_value).write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    active_packets = [PACKET_NAMES["rules"], PACKET_NAMES["worktree"], *candidate_batch_names, *split_packet_names]
    task_packet_names = build_task_packet_names(candidate_batch_names, split_packet_names)
    packet_worker_map = build_packet_worker_map(candidate_batch_names, split_packet_names)

    all_quality_hints = aggregate_quality_escape_hints(candidate_quality_hints, split_quality_hints)
    raw_reread_reasons = dedupe_preserve(
        [
            str(item.get("reason"))
            for item in all_quality_hints
            if item.get("common_path_blocking")
        ]
    )
    common_path_sufficient = not raw_reread_reasons

    worktree_packet = {
        "purpose": "Summarize the current working tree before drafting commit buckets.",
        "head_commit": worktree.get("head_commit"),
        "branch": worktree.get("branch"),
        "status_branch_line": worktree.get("status_branch_line"),
        "changed_paths": changed_paths,
        "changed_file_groups": worktree.get("changed_file_groups", {}),
        "diff_shortstat": worktree.get("diff_shortstat"),
        "diff_stat": worktree.get("diff_stat"),
        "validation_candidates": worktree.get("validation_candidates", []),
        "validation_candidate_map": validation_map,
        "active_operation": worktree.get("active_operation"),
        "review_overrides": overrides,
        "candidate_batch_order": candidate_batch_names,
        "split_candidate_paths": [packet["path"] for packet in split_packets],
        "quality_escape_hints": all_quality_hints,
        "common_path_sufficient": common_path_sufficient,
        "raw_reread_reasons": raw_reread_reasons,
    }

    global_packet = {
        "purpose": "Shared context every worker should keep in view before reading its packet.",
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "repo_profile_name": worktree.get("repo_profile_name"),
        "repo_profile_path": worktree.get("repo_profile_path"),
        "repo_profile_summary": worktree.get("repo_profile_summary"),
        "repo_profile": worktree.get("repo_profile"),
        "input_scope": worktree.get("input_scope"),
        "repo_root": worktree.get("repo_root"),
        "head_commit": worktree.get("head_commit"),
        "branch": worktree.get("branch"),
        "worktree_fingerprint": worktree.get("worktree_fingerprint"),
        "active_operation": worktree.get("active_operation"),
        "required_message_rules": {
            "format": rules.get("rules", {}).get("format"),
            "allowed_types": rules.get("rules", {}).get("allowed_types", []),
            "scope_required": rules.get("rules", {}).get("scope_required"),
            "subject_length_limit": rules.get("rules", {}).get("subject_length_limit"),
            "repo_defaults": rules.get("rules", {}).get("repo_defaults", []),
        },
        "worktree_summary": {
            "changed_file_count": len(files),
            "diff_shortstat": diff_totals,
            "candidate_batch_count": len(batches),
            "split_candidate_count": len(split_packets),
        },
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "task_packet_names": task_packet_names,
        "common_path_contract": COMMON_PATH_CONTRACT,
        "worker_selection_guidance": worker_selection_guidance,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": packet_worker_map,
        "candidate_field_bundles": candidate_field_bundles,
        "worker_footer_fields": worker_footer_fields,
        "reread_reason_values": RAW_REREAD_ALLOWED_REASONS,
        "xhigh_reread_policy": XHIGH_REREAD_POLICY,
        "domain_overlay": domain_overlay,
        "disallowed_actions": [
            "Do not preserve the existing index layout as authoritative.",
            "Do not apply a split to new, deleted, renamed, copied, or binary files.",
            "Do not guess when a hunk id is missing or ambiguous in the current diff.",
            "Do not continue applying later commits after staging or validation fails.",
            "Do not auto-widen a failed split to whole-file unless the plan explicitly chose that fallback.",
        ],
    }

    recommended_workers: list[dict[str, Any]] = []
    optional_workers: list[dict[str, Any]] = []
    if review_mode == "targeted-delegation":
        recommended_workers.append(
            {
                "name": "rules",
                "agent_type": "docs_verifier",
                "packets": ["global_packet.json", "rules_packet.json"],
                "responsibility": "Extract hard commit-message rules, scope requirements, and repo defaults.",
                "reasoning_effort": "medium",
            }
        )
        if candidate_batch_names:
            recommended_workers.append(
                {
                    "name": "commit-batches",
                    "agent_type": "evidence_summarizer",
                    "packets": ["global_packet.json", *candidate_batch_names[:2]],
                    "responsibility": "Summarize the strongest logical commit buckets and recommended type/scope.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                }
            )
        optional_workers.append(
            {
                "name": "worktree",
                "agent_type": "repo_mapper",
                "packets": ["global_packet.json", "worktree_packet.json"],
                "responsibility": "Summarize touched areas, validation-candidate coverage, and override signals.",
                "reasoning_effort": "medium",
            }
        )
        if split_packet_names:
            optional_workers.append(
                {
                    "name": "split-review",
                    "agent_type": "large_diff_auditor",
                    "packets": ["global_packet.json", split_packet_names[0]],
                    "responsibility": "Decide whether the split candidate file is one intent or multiple intents.",
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
                "responsibility": "Extract hard commit-message rules, scope requirements, and repo defaults.",
                "reasoning_effort": "medium",
            }
        )
        for batch_name in candidate_batch_names[: max(worker_count - 1, 1)]:
            recommended_workers.append(
                {
                    "name": packet_basename(batch_name),
                    "agent_type": "evidence_summarizer",
                    "packets": ["global_packet.json", batch_name],
                    "responsibility": "Summarize one candidate batch and recommend type/scope.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                }
            )
        recommended_workers = recommended_workers[:worker_count]
        optional_workers.append(
            {
                "name": "worktree",
                "agent_type": "repo_mapper",
                "packets": ["global_packet.json", "worktree_packet.json"],
                "responsibility": "Summarize touched areas, validation-candidate coverage, and override signals.",
                "reasoning_effort": "medium",
            }
        )
        if split_packet_names:
            optional_workers.append(
                {
                    "name": "split-review",
                    "agent_type": "large_diff_auditor",
                    "packets": ["global_packet.json", *split_packet_names[:2]],
                    "responsibility": "Review the highest-risk split-file packets.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                }
            )
        optional_workers.append(
            {
                "name": "qa",
                "agent_type": "large_diff_auditor",
                "packets": ["global_packet.json", *candidate_batch_names[:3], *split_packet_names[:1]],
                "responsibility": "Compare the draft commit plan against the packet evidence before apply.",
                "reasoning_effort": "medium",
                }
            )

    packet_order = ["global_packet.json", "rules_packet.json", "worktree_packet.json", *candidate_batch_names, *split_packet_names]
    orchestrator = {
        "head_commit": worktree.get("head_commit"),
        "branch": worktree.get("branch"),
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "repo_profile_name": worktree.get("repo_profile_name"),
        "repo_profile_path": worktree.get("repo_profile_path"),
        "repo_profile_summary": worktree.get("repo_profile_summary"),
        "review_mode": review_mode,
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "worker_budget": len(recommended_workers),
        "recommended_worker_count": len(recommended_workers),
        "shared_packet": "global_packet.json",
        "shared_packet_name": "global_packet.json",
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "task_packet_names": task_packet_names,
        "candidate_batch_count": len(candidate_batch_names),
        "split_file_count": len(split_packet_names),
        "worker_selection_guidance": worker_selection_guidance,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": packet_worker_map,
        "common_path_contract": COMMON_PATH_CONTRACT,
        "reread_reason_values": RAW_REREAD_ALLOWED_REASONS,
        "xhigh_reread_policy": XHIGH_REREAD_POLICY,
        "candidate_batch_map": batch_map,
        "split_candidate_paths": [packet["path"] for packet in split_packets],
        "review_overrides": overrides,
        "applied_override_signals": [str(item.get("reason")) for item in overrides if str(item.get("reason") or "").strip()],
        "local_responsibilities": [
            "Read rules_packet.json and worktree_packet.json locally before drafting commit-plan.json.",
            "Keep the current staged state as a hint, not a contract.",
            "Prefer whole-file commits unless a split-file packet clearly justifies a split.",
            "Do not reread raw diffs on the common path; use explicit reread reasons only when packet evidence stays insufficient or conflicting.",
            "Stop and ask when hunk confidence is low or any split packet stays ambiguous.",
            "Validate commit-plan.json before running apply_commit_plan.py.",
        ],
        "packet_order": packet_order,
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
        "common_path_sufficient": common_path_sufficient,
        "raw_reread_reasons": raw_reread_reasons,
    }

    packet_payloads: dict[str, dict[str, Any]] = {
        "orchestrator.json": orchestrator,
        "global_packet.json": global_packet,
        "rules_packet.json": rules_packet,
        "worktree_packet.json": worktree_packet,
        **candidate_payloads,
        **split_payloads,
    }
    local_only_surfaces = {
        "candidate_batches": [
            {
                "batch_id": packet_basename(batch_name),
                "files": [
                    entry
                    for entry in files
                    if str(entry["path"]) in batch_map.get(packet_basename(batch_name), [])
                ],
            }
            for batch_name in candidate_batch_names
        ],
        "split_candidates": split_packets,
    }
    packet_metrics = compute_packet_metrics(
        packet_payloads,
        local_only_sources={
            "rules.json": rules,
            "worktree.json": worktree,
            "raw_focus_surfaces.json": local_only_surfaces,
        },
        shared_packets=[],
    )
    review_mode, worker_count, review_mode_adjustments = maybe_apply_delegation_savings_floor(
        review_mode,
        worker_count,
        packet_metrics,
        review_mode_adjustments,
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
                    "responsibility": "Extract hard commit-message rules, scope requirements, and repo defaults.",
                    "reasoning_effort": "medium",
                }
            )
            if candidate_batch_names:
                recommended_workers.append(
                    {
                        "name": "commit-batches",
                        "agent_type": "evidence_summarizer",
                        "packets": ["global_packet.json", *candidate_batch_names[:2]],
                        "responsibility": "Summarize the strongest logical commit buckets and recommended type/scope.",
                        "reasoning_effort": "medium",
                        "model": "gpt-5.4-mini",
                    }
                )
            optional_workers.append(
                {
                    "name": "worktree",
                    "agent_type": "repo_mapper",
                    "packets": ["global_packet.json", "worktree_packet.json"],
                    "responsibility": "Summarize touched areas, validation-candidate coverage, and override signals.",
                    "reasoning_effort": "medium",
                }
            )
            if split_packet_names:
                optional_workers.append(
                    {
                        "name": "split-review",
                        "agent_type": "large_diff_auditor",
                        "packets": ["global_packet.json", split_packet_names[0]],
                        "responsibility": "Decide whether the split candidate file is one intent or multiple intents.",
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
                    "responsibility": "Extract hard commit-message rules, scope requirements, and repo defaults.",
                    "reasoning_effort": "medium",
                }
            )
            for batch_name in candidate_batch_names[: max(worker_count - 1, 1)]:
                recommended_workers.append(
                    {
                        "name": packet_basename(batch_name),
                        "agent_type": "evidence_summarizer",
                        "packets": ["global_packet.json", batch_name],
                        "responsibility": "Summarize one candidate batch and recommend type/scope.",
                        "reasoning_effort": "medium",
                        "model": "gpt-5.4-mini",
                    }
                )
            recommended_workers = recommended_workers[:worker_count]
            optional_workers.append(
                {
                    "name": "worktree",
                    "agent_type": "repo_mapper",
                    "packets": ["global_packet.json", "worktree_packet.json"],
                    "responsibility": "Summarize touched areas, validation-candidate coverage, and override signals.",
                    "reasoning_effort": "medium",
                }
            )
            if split_packet_names:
                optional_workers.append(
                    {
                        "name": "split-review",
                        "agent_type": "large_diff_auditor",
                        "packets": ["global_packet.json", *split_packet_names[:2]],
                        "responsibility": "Review the highest-risk split-file packets.",
                        "reasoning_effort": "medium",
                        "model": "gpt-5.4-mini",
                    }
                )
            optional_workers.append(
                {
                    "name": "qa",
                    "agent_type": "large_diff_auditor",
                    "packets": ["global_packet.json", *candidate_batch_names[:3], *split_packet_names[:1]],
                    "responsibility": "Compare the draft commit plan against the packet evidence before apply.",
                    "reasoning_effort": "medium",
                }
            )
        orchestrator["review_mode"] = review_mode
        orchestrator["review_mode_baseline"] = review_mode_baseline
        orchestrator["review_mode_adjustments"] = review_mode_adjustments
        orchestrator["worker_budget"] = len(recommended_workers)
        orchestrator["recommended_worker_count"] = len(recommended_workers)
        orchestrator["recommended_workers"] = recommended_workers
        orchestrator["optional_workers"] = optional_workers
        packet_payloads["orchestrator.json"] = orchestrator
        packet_metrics = compute_packet_metrics(
            packet_payloads,
            local_only_sources={
                "rules.json": rules,
                "worktree.json": worktree,
                "raw_focus_surfaces.json": local_only_surfaces,
            },
            shared_packets=[],
        )
    build_result = build_result_payload(
        review_mode=review_mode,
        review_mode_baseline=review_mode_baseline,
        review_mode_adjustments=review_mode_adjustments,
        recommended_workers=recommended_workers,
        packet_order=packet_order,
        active_packets=active_packets,
        applied_override_signals=orchestrator["applied_override_signals"],
        candidate_batch_count=len(candidate_batch_names),
        split_file_count=len(split_packet_names),
        packet_metrics=packet_metrics,
        common_path_sufficient=common_path_sufficient,
        raw_reread_reasons=raw_reread_reasons,
    )

    for path_name, payload in (
        ("rules_packet.json", rules_packet),
        ("worktree_packet.json", worktree_packet),
        ("global_packet.json", global_packet),
        ("orchestrator.json", orchestrator),
        ("packet_metrics.json", packet_metrics),
    ):
        (output_dir / path_name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    if args.result_output:
        args.result_output.write_text(
            json.dumps(build_result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "review_mode": review_mode,
                "candidate_batch_count": len(batches),
                "split_packet_count": len(split_packets),
                "recommended_worker_count": len(recommended_workers),
                "common_path_sufficient": common_path_sufficient,
                "raw_reread_count": len(raw_reread_reasons),
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
