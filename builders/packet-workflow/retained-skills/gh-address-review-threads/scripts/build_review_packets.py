#!/usr/bin/env python3
"""Build packet artifacts for token-efficient PR review-thread handling."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from thread_action_contract import context_fingerprint, marker_conflict_summary, normalize_marker_conflicts
from review_thread_packet_contract import (
    ARCHETYPE,
    BROAD_TARGET_LIMIT,
    CHURN_OVERRIDE_LIMIT,
    COMMON_PATH_CONTRACT,
    DELEGATION_SAVINGS_FLOOR,
    DECISION_READY_PACKETS,
    LOCAL_THREAD_LIMIT,
    MEANINGFUL_GENERATED_FILE_MIN_COUNT,
    MEANINGFUL_GENERATED_FILE_MIN_RATIO,
    ORCHESTRATOR_PROFILE,
    PREFERRED_WORKER_FAMILIES,
    TARGETED_THREAD_LIMIT,
    WORKER_OUTPUT_SHAPE,
    WORKER_RETURN_CONTRACT,
    WORKFLOW_FAMILY,
    XHIGH_REREAD_POLICY,
    build_result_payload,
    compute_packet_metrics,
    derive_optional_workers,
    derive_packet_worker_map,
    derive_recommended_workers,
)


SNIPPET_RADIUS = 12
DIFF_SNIPPET_CHAR_LIMIT = 2200
DIFF_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@", re.MULTILINE)
REQUEST_ANCHOR_RE = re.compile(r"`([^`]+)`|\"([^\"]+)\"|'([^']+)'")
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
GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def parse_markdown_headings(markdown_text: str | None) -> list[str]:
    if not markdown_text:
        return []
    return [line[3:].strip() for line in markdown_text.splitlines() if line.startswith("## ")]


def section_bodies(markdown_text: str | None) -> dict[str, str]:
    if not markdown_text:
        return {}
    sections: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


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
        or lower.startswith(".github/instructions/")
    ):
        return "automation"
    if lower.endswith(".md") or lower.startswith("docs/"):
        return "docs"
    if lower.endswith((".yml", ".yaml", ".toml", ".json", ".csproj", ".props", ".targets")):
        return "config"
    if lower.endswith((".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
        return "runtime"
    return "other"


def core_area_for_path(path: str) -> str | None:
    lower = path.replace("\\", "/").lower()
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
    if lower.startswith(runtime_prefixes) or lower in runtime_files:
        return "runtime"
    if lower.startswith(process_prefixes) or lower in process_files:
        return "process"
    if lower.endswith((".csproj", ".props", ".targets")) or lower in config_files:
        return "config"
    return None


def is_generated_file(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return any(pattern.search(lowered) for pattern in GENERATED_FILE_PATTERNS)


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout


def guidance_paths(repo_root: Path) -> dict[str, str]:
    candidates = {
        "pull_request_instructions": ".github/instructions/pull-request.instructions.md",
        "pull_request_template": ".github/pull_request_template.md",
        "commit_message_instructions": ".github/instructions/commit-message.instructions.md",
        "copilot_instructions": ".github/copilot-instructions.md",
        "contributing": "CONTRIBUTING.md",
        "maintaining": "MAINTAINING.md",
    }
    result: dict[str, str] = {}
    for key, relative_path in candidates.items():
        path = repo_root / relative_path
        if path.exists():
            result[key] = str(path)
    return result


def make_line_snippet(path: Path, line_number: int | None, radius: int = SNIPPET_RADIUS) -> str | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    target = line_number if line_number and line_number > 0 else 1
    target = min(max(target, 1), len(lines))
    start = max(target - radius, 1)
    end = min(target + radius, len(lines))
    return "\n".join(f"{index:>5}: {lines[index - 1]}" for index in range(start, end + 1))


def diff_range_candidates(base_ref: str | None, head_ref: str | None) -> list[str]:
    if not base_ref or not head_ref:
        return []
    return [
        f"{base_ref}..{head_ref}",
        f"origin/{base_ref}..{head_ref}",
        f"{base_ref}..origin/{head_ref}",
        f"origin/{base_ref}..origin/{head_ref}",
    ]


def diff_snippet_for_path(
    repo_root: Path,
    base_ref: str | None,
    head_ref: str | None,
    path: str,
    line_number: int | None,
    cache: dict[str, str | None],
) -> str | None:
    if path in cache:
        return cache[path]
    normalized_path = path.replace("\\", "/")
    full_diff = None
    for revision_range in diff_range_candidates(base_ref, head_ref):
        output = run_git(repo_root, ["diff", "-U3", revision_range, "--", normalized_path])
        if output.strip():
            full_diff = output
            break
    if not full_diff:
        cache[path] = None
        return None
    if line_number is None or len(full_diff) <= DIFF_SNIPPET_CHAR_LIMIT:
        cache[path] = full_diff[:DIFF_SNIPPET_CHAR_LIMIT].rstrip()
        return cache[path]
    matches = list(DIFF_HUNK_HEADER_RE.finditer(full_diff))
    selected = None
    for index, match in enumerate(matches):
        start = int(match.group("start"))
        count = int(match.group("count") or "1")
        end = start + max(count, 1) + 3
        if start - 3 <= line_number <= end:
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(full_diff)
            selected = full_diff[match.start():next_start].strip()
            break
    if selected is None:
        selected = full_diff[:DIFF_SNIPPET_CHAR_LIMIT].strip()
    cache[path] = selected[:DIFF_SNIPPET_CHAR_LIMIT].rstrip()
    return cache[path]


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


def normalized_headline(body: str) -> str:
    for raw_line in body.splitlines():
        cleaned = clean_headline_line(raw_line)
        if cleaned:
            return cleaned[:160]
    return clean_headline_line(body)[:160]


def normalize_text_for_matching(text: str | None) -> str:
    if not text:
        return ""
    normalized_lines = [clean_headline_line(line) for line in str(text).splitlines()]
    return " ".join(line for line in normalized_lines if line).strip()


def reviewer_headline(thread: dict[str, Any]) -> str:
    reviewer_comment = thread.get("reviewer_comment") or {}
    return normalized_headline(str(reviewer_comment.get("body") or ""))


def safe_excerpt(text: str | None, limit: int = 220) -> str:
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[: limit - 3] + "..." if len(compact) > limit else compact


def list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()] if str(value).strip() else []


def match_terms(text: str | None) -> list[str]:
    normalized = normalize_text_for_matching(text)
    terms: list[str] = []
    for raw_token in re.findall(r"[a-z0-9_./-]+", normalized):
        token = raw_token.strip(".-/")
        if len(token) >= 3 and token not in REQUEST_ANCHOR_STOPWORDS:
            terms.append(token)
    return terms


def request_anchor_evidence(
    reviewer_body: str,
    *,
    snippet: str | None,
    diff_snippet: str | None,
) -> tuple[bool, list[str], list[str], list[str]]:
    evidence_text = normalize_text_for_matching("\n".join(part for part in (snippet, diff_snippet) if part))
    if not evidence_text:
        return False, [], [], []

    exact_anchors = [
        normalized
        for normalized in (
            normalize_text_for_matching(next(group for group in match.groups() if group))
            for match in REQUEST_ANCHOR_RE.finditer(reviewer_body)
        )
        if normalized
    ]
    matched_exact_anchors = [anchor for anchor in exact_anchors if anchor in evidence_text]
    if exact_anchors:
        return bool(matched_exact_anchors), exact_anchors, matched_exact_anchors, []

    requested_terms = sorted(dict.fromkeys(match_terms(reviewer_body)))
    if len(requested_terms) < 2:
        return False, [], [], requested_terms

    evidence_terms = set(match_terms(evidence_text))
    matched_terms = [term for term in requested_terms if term in evidence_terms]
    return len(matched_terms) >= 2, [], [], matched_terms


def comment_summary(comment: dict[str, Any] | None) -> dict[str, Any] | None:
    if not comment:
        return None
    return {
        "id": comment.get("id"),
        "author_login": comment.get("author_login"),
        "created_at": comment.get("created_at"),
        "updated_at": comment.get("updated_at"),
        "url": comment.get("url"),
        "body": comment.get("body"),
    }


def packet_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index:02d}.json"


def candidate_decision(thread: dict[str, Any]) -> str:
    return "defer-outdated" if thread.get("is_outdated") else "accept"


def load_reconciliation_input(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "default_validation_commands": [],
            "accepted_threads": {},
        }

    payload = load_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError("reconciliation input must be a JSON object")

    default_validation_commands = list_of_strings(payload.get("default_validation_commands"))
    accepted_threads: dict[str, dict[str, Any]] = {}
    for item in payload.get("accepted_threads") or []:
        if not isinstance(item, dict):
            raise RuntimeError("accepted_threads entries must be JSON objects")
        thread_id = str(item.get("thread_id") or "").strip()
        if not thread_id:
            raise RuntimeError("accepted_threads entries must include thread_id")
        validation_commands = list_of_strings(item.get("validation_commands")) or list(default_validation_commands)
        accepted_threads[thread_id] = {
            "thread_id": thread_id,
            "validation_commands": validation_commands,
        }

    return {
        "default_validation_commands": default_validation_commands,
        "accepted_threads": accepted_threads,
    }


def previous_thread_lookup(previous_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(previous_context, dict):
        return {}
    return {
        str(thread.get("thread_id") or ""): thread
        for thread in previous_context.get("threads", [])
        if isinstance(thread, dict) and str(thread.get("thread_id") or "").strip()
    }


def transitioned_to_outdated(
    previous_thread: dict[str, Any] | None,
    current_thread: dict[str, Any],
) -> bool:
    if not previous_thread:
        return False
    if bool(previous_thread.get("is_resolved")) or bool(current_thread.get("is_resolved")):
        return False
    if bool(previous_thread.get("is_outdated")):
        return False
    return bool(current_thread.get("is_outdated"))


def diff_hunk_covers_thread_location(
    diff_snippet: str | None,
    *,
    previous_thread: dict[str, Any],
    current_thread: dict[str, Any],
) -> bool:
    if not isinstance(diff_snippet, str) or not diff_snippet.strip():
        return False
    candidate_lines = {
        int(value)
        for value in (
            current_thread.get("line"),
            current_thread.get("original_line"),
            previous_thread.get("line"),
            previous_thread.get("original_line"),
        )
        if isinstance(value, int) and value > 0
    }
    if not candidate_lines:
        return False
    for match in DIFF_HUNK_HEADER_RE.finditer(diff_snippet):
        start = int(match.group("start"))
        count = int(match.group("count") or "1")
        end = start + max(count, 1) + 3
        if any(start - 3 <= line_number <= end for line_number in candidate_lines):
            return True
    return False


def build_outdated_recheck(
    *,
    thread: dict[str, Any],
    previous_thread: dict[str, Any],
    file_context: dict[str, Any],
    area: str,
    accepted_thread: dict[str, Any] | None,
) -> dict[str, Any]:
    validation_commands = list(accepted_thread.get("validation_commands") or []) if accepted_thread else []
    current_head_visible = diff_hunk_covers_thread_location(
        file_context.get("diff_snippet"),
        previous_thread=previous_thread,
        current_thread=thread,
    )
    reviewer_body = str(
        (thread.get("reviewer_comment") or previous_thread.get("reviewer_comment") or {}).get("body") or ""
    ).strip()
    request_anchor_visible, exact_anchors, matched_exact_anchors, matched_terms = request_anchor_evidence(
        reviewer_body,
        snippet=file_context.get("snippet"),
        diff_snippet=file_context.get("diff_snippet"),
    )

    if accepted_thread is None:
        verdict = "still-applies"
        verdict_reason = "thread_was_not_accepted_before_push"
    elif not validation_commands:
        verdict = "ambiguous"
        verdict_reason = "missing_validation_provenance"
    elif area not in {"docs", "runtime", "tests"}:
        verdict = "ambiguous"
        verdict_reason = "unsupported_area_for_auto_resolve"
    elif not bool(file_context.get("path_exists")):
        verdict = "ambiguous"
        verdict_reason = "path_missing_in_current_head"
    elif not current_head_visible:
        verdict = "ambiguous"
        verdict_reason = "missing_current_head_evidence"
    else:
        verdict = "auto-accept"
        verdict_reason = "accepted_same_run_with_current_head_evidence"

    return {
        "previous_snapshot": {
            "path": str(previous_thread.get("path") or ""),
            "line": previous_thread.get("line"),
            "original_line": previous_thread.get("original_line"),
            "is_outdated": bool(previous_thread.get("is_outdated")),
            "is_resolved": bool(previous_thread.get("is_resolved")),
        },
        "original_request": {
            "reviewer_login": str(thread.get("reviewer_login") or previous_thread.get("reviewer_login") or ""),
            "reviewer_body": str(
                (thread.get("reviewer_comment") or previous_thread.get("reviewer_comment") or {}).get("body") or ""
            ).strip(),
            "latest_reviewer_comment_at": str(
                thread.get("latest_reviewer_comment_at") or previous_thread.get("latest_reviewer_comment_at") or ""
            ).strip(),
        },
        "same_run_acceptance": {
            "accepted_in_previous_plan": accepted_thread is not None,
        },
        "validation_provenance": {
            "commands": validation_commands,
        },
        "current_head_evidence": {
            "path": str(thread.get("path") or ""),
            "line": thread.get("line"),
            "original_line": thread.get("original_line"),
            "path_exists": bool(file_context.get("path_exists")),
            "area": area,
            "snippet": file_context.get("snippet"),
            "diff_snippet": file_context.get("diff_snippet"),
            "evidence_visible": current_head_visible,
            "request_anchor_visible": request_anchor_visible,
            "exact_request_anchors": exact_anchors,
            "matched_exact_request_anchors": matched_exact_anchors,
            "matched_request_terms": matched_terms,
        },
        "resolution_verdict": verdict,
        "verdict_reason": verdict_reason,
        "auto_resolution_candidate": verdict == "auto-accept",
    }


def code_change_policy(path: str) -> dict[str, Any]:
    area = classify_path(path)
    core_area = core_area_for_path(path)
    blockers: list[str] = []
    if core_area in {"config", "process"}:
        blockers.append("Touches config or maintainer workflow paths.")
    if area == "automation":
        blockers.append("Touches automation files.")
    return {
        "small_fix_candidate": area in {"runtime", "tests", "docs"} and not blockers,
        "blockers": blockers,
    }


def validation_candidates_for_path(path: str, area: str, *, is_outdated: bool) -> list[dict[str, Any]]:
    if is_outdated:
        return [
            {
                "kind": "outdated-default",
                "path": path,
                "basis": "Default to defer-outdated unless current HEAD proves the issue still applies or same-run reconciliation proves the accepted fix already covers it.",
            }
        ]
    if area in {"runtime", "tests"}:
        return [
            {
                "kind": "narrow_validation",
                "path": path,
                "basis": "Run the narrowest repo-appropriate check covering this fix surface before completion.",
            }
        ]
    if area == "docs":
        return [
            {
                "kind": "docs_scope_check",
                "path": path,
                "basis": "Confirm the wording still matches the current diff scope before replying.",
            }
        ]
    return [
        {
            "kind": "local_scope_review",
            "path": path,
            "basis": "Re-check config, workflow, or ownership impact locally before accepting and resolving.",
        }
    ]


def reply_update_basis(reply_candidates: dict[str, Any] | None) -> dict[str, Any]:
    basis: dict[str, Any] = {}
    for phase in ("ack", "complete"):
        candidate = (reply_candidates or {}).get(phase) or {}
        basis[phase] = {
            "mode": candidate.get("mode"),
            "comment_id": candidate.get("comment_id"),
            "reason": candidate.get("reason"),
            "managed": bool(candidate.get("managed")),
            "adopted_unmarked_reply": bool(candidate.get("adopted_unmarked_reply")),
        }
    return basis


def packet_quality_basis(
    *,
    reviewer_bodies: list[str],
    path: str,
    path_exists: bool,
    snippet: str | None,
    diff_snippet: str | None,
) -> dict[str, Any]:
    required_evidence_present = bool(
        reviewer_bodies
        and all(body.strip() for body in reviewer_bodies)
        and path.strip()
        and path_exists
        and ((snippet or "").strip() or (diff_snippet or "").strip())
    )
    ownership_ambiguous = not path.strip() or not path_exists
    explicit_escape_reasons: list[str] = []
    if not required_evidence_present:
        explicit_escape_reasons.append("missing_required_evidence")
    if ownership_ambiguous:
        explicit_escape_reasons.append("ownership_ambiguity")
    if not ((snippet or "").strip() or (diff_snippet or "").strip()):
        explicit_escape_reasons.append("insufficient_excerpt_quality")
    explicit_escape_reasons = list(dict.fromkeys(explicit_escape_reasons))
    return {
        "required_evidence_present": required_evidence_present,
        "ownership_ambiguous": ownership_ambiguous,
        "explicit_reread_reasons": explicit_escape_reasons,
        "validator_ready_recommendation_path": required_evidence_present and not explicit_escape_reasons,
        "common_path_sufficient": required_evidence_present and not ownership_ambiguous and not explicit_escape_reasons,
    }


def quality_escape_hints(
    quality_basis: dict[str, Any],
    *,
    path: str,
    is_outdated: bool,
    blockers: list[str] | None = None,
) -> list[str]:
    hints: list[str] = []
    if is_outdated:
        hints.append("Outdated threads stay defer-outdated by default; only reopen after checking current HEAD, except for same-run transitioned threads with proven accepted fixes.")
    if "missing_required_evidence" in quality_basis.get("explicit_reread_reasons", []):
        hints.append(f"Treat missing evidence for {path or '<unknown>'} as a reread trigger only if the packet cannot support a local decision.")
    if "ownership_ambiguity" in quality_basis.get("explicit_reread_reasons", []):
        hints.append("Ownership ambiguity is advisory here; record an explicit allowed reason before widening scope or rereading raw diff.")
    if "insufficient_excerpt_quality" in quality_basis.get("explicit_reread_reasons", []):
        hints.append("Low-quality excerpts are advisory until an explicit reread reason is recorded.")
    for blocker in blockers or []:
        hints.append(f"Blocker: {blocker}")
    return hints


def sort_threads(threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        threads,
        key=lambda thread: (
            str(thread.get("path") or ""),
            int(thread.get("line") or thread.get("original_line") or 0),
            str(thread.get("thread_id") or ""),
        ),
    )


def cluster_non_outdated_threads(threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = sort_threads(
        [thread for thread in threads if not thread.get("is_resolved") and not thread.get("is_outdated")]
    )
    used: set[str] = set()
    batches: list[dict[str, Any]] = []

    by_primary_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for thread in eligible:
        headline = reviewer_headline(thread)
        if headline:
            by_primary_key.setdefault((str(thread.get("path") or ""), headline), []).append(thread)

    for (path, headline), group in by_primary_key.items():
        if len(group) <= 1:
            continue
        batches.append(
            {
                "cluster_reason": "same_path_and_normalized_headline",
                "path": path,
                "normalized_headline": headline,
                "reviewer_login": group[0].get("reviewer_login"),
                "threads": sort_threads(group),
            }
        )
        used.update(str(thread["thread_id"]) for thread in group)

    leftovers = [thread for thread in eligible if str(thread["thread_id"]) not in used]
    by_fallback_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for thread in leftovers:
        by_fallback_key.setdefault(
            (str(thread.get("path") or ""), str(thread.get("reviewer_login") or "")),
            [],
        ).append(thread)

    for (path, reviewer_login), group in by_fallback_key.items():
        group = sort_threads(group)
        if len(group) <= 1:
            continue
        current_cluster = [group[0]]
        for thread in group[1:]:
            previous = current_cluster[-1]
            previous_line = int(previous.get("line") or previous.get("original_line") or 0)
            current_line = int(thread.get("line") or thread.get("original_line") or 0)
            if abs(current_line - previous_line) <= 20:
                current_cluster.append(thread)
                continue
            if len(current_cluster) > 1:
                batches.append(
                    {
                        "cluster_reason": "same_path_reviewer_and_line_window",
                        "path": path,
                        "normalized_headline": reviewer_headline(current_cluster[0]),
                        "reviewer_login": reviewer_login,
                        "threads": current_cluster,
                    }
                )
                used.update(str(item["thread_id"]) for item in current_cluster)
            current_cluster = [thread]
        if len(current_cluster) > 1:
            batches.append(
                {
                    "cluster_reason": "same_path_reviewer_and_line_window",
                    "path": path,
                    "normalized_headline": reviewer_headline(current_cluster[0]),
                    "reviewer_login": reviewer_login,
                    "threads": current_cluster,
                }
            )
            used.update(str(item["thread_id"]) for item in current_cluster)

    return sorted(
        [batch for batch in batches if len(batch["threads"]) > 1],
        key=lambda batch: (
            str(batch.get("path") or ""),
            int(batch["threads"][0].get("line") or batch["threads"][0].get("original_line") or 0),
        ),
    )


def determine_baseline_review_mode(
    unresolved_non_outdated_count: int,
    active_path_count: int,
    active_area_count: int,
    analysis_target_count: int,
) -> str:
    if unresolved_non_outdated_count <= LOCAL_THREAD_LIMIT and active_path_count <= 1 and active_area_count <= 1:
        review_mode = "local-only"
    elif unresolved_non_outdated_count > TARGETED_THREAD_LIMIT or analysis_target_count >= BROAD_TARGET_LIMIT:
        review_mode = "broad-delegation"
    else:
        review_mode = "targeted-delegation"
    return review_mode


def apply_override_adjustment(
    review_mode: str,
    override_signals: list[dict[str, str]],
) -> tuple[str, list[str]]:
    adjustments: list[str] = []
    if override_signals and review_mode == "local-only":
        review_mode = "targeted-delegation"
        adjustments.append("override_signal")
    elif override_signals and review_mode == "targeted-delegation":
        review_mode = "broad-delegation"
        adjustments.append("override_signal")
    return review_mode, adjustments


def maybe_apply_delegation_savings_floor(
    review_mode: str,
    packet_metrics: dict[str, Any],
    adjustments: list[str],
) -> tuple[str, list[str]]:
    estimated_savings = int(packet_metrics.get("estimated_delegation_savings", 0) or 0)
    if (
        review_mode == "local-only"
        and estimated_savings >= DELEGATION_SAVINGS_FLOOR
        and "delegation_savings_floor" not in adjustments
    ):
        return "targeted-delegation", [*adjustments, "delegation_savings_floor"]
    return review_mode, adjustments


def recommended_worker_minimum(
    review_mode: str,
    review_mode_adjustments: list[str],
) -> int:
    if (
        review_mode == "targeted-delegation"
        and "delegation_savings_floor" in review_mode_adjustments
    ):
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build packet artifacts for token-efficient PR review-thread handling."
    )
    parser.add_argument("--context", type=Path, required=True, help="Path to JSON from collect_review_threads.py")
    parser.add_argument("--repo-root", type=Path, required=True, help="Repository root")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated packets")
    parser.add_argument(
        "--previous-context",
        type=Path,
        help="Optional pre-push context JSON used to detect same-run outdated transitions.",
    )
    parser.add_argument(
        "--reconciliation-input",
        type=Path,
        help="Optional JSON describing accepted same-run threads and validation provenance.",
    )
    parser.add_argument("--result-output", type=Path, help="Optional path to write the eval-side build result JSON.")
    args = parser.parse_args()

    context = load_json(args.context)
    previous_context = load_json(args.previous_context) if args.previous_context else None
    reconciliation_input = load_reconciliation_input(args.reconciliation_input)
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pr = context.get("pr", {})
    threads = sort_threads(list(context.get("threads", [])))
    unresolved_threads = [thread for thread in threads if not thread.get("is_resolved")]
    unresolved_non_outdated = [thread for thread in unresolved_threads if not thread.get("is_outdated")]
    unresolved_outdated = [thread for thread in unresolved_threads if thread.get("is_outdated")]
    changed_files = [str(path) for path in context.get("changed_files", [])]
    diff_totals = parse_diff_totals(context.get("diff_stat"))
    generated_file_count = sum(1 for path in changed_files if is_generated_file(path))
    generated_file_ratio = (generated_file_count / len(changed_files)) if changed_files else 0.0
    core_areas_touched = sorted(
        {area for path in changed_files if (area := core_area_for_path(path)) is not None}
    )

    override_signals: list[dict[str, str]] = []
    if (diff_totals or {}).get("churn", 0) >= CHURN_OVERRIDE_LIMIT:
        override_signals.append(
            {
                "reason": "diff_stat_threshold",
                "detail": f"PR diff churn reached {(diff_totals or {}).get('churn', 0)} lines (threshold {CHURN_OVERRIDE_LIMIT}).",
            }
        )
    if len(core_areas_touched) >= 2:
        override_signals.append(
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
        override_signals.append(
            {
                "reason": "generated_files_not_majority",
                "detail": "Generated files are present but are not the majority of the change "
                f"({generated_file_count}/{len(changed_files)}).",
            }
        )

    sections = section_bodies(str(pr.get("body") or ""))
    global_packet_name = "global_packet.json"
    global_packet = {
        "purpose": "Shared context every worker should keep in view before reading thread packets.",
        "workflow_family": "github-review",
        "archetype": "audit-and-apply",
        "decision_ready_packets": False,
        "worker_return_contract": "generic",
        "worker_output_shape": "flat",
        "xhigh_reread_policy": "packet-first local adjudication with raw rereads only for explicit exception reasons",
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "repo_profile": context.get("repo_profile"),
        "pr": {
            "id": pr.get("id"),
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
            "state": pr.get("state"),
            "head_ref": pr.get("headRefName"),
            "base_ref": pr.get("baseRefName"),
        },
        "viewer_login": context.get("viewer_login"),
        "pr_intent": sections.get("Why", ""),
        "user_visible_impact": sections.get("What changed", ""),
        "rollout_migration_risk": {
            "how_excerpt": sections.get("How", ""),
            "risk_excerpt": sections.get("Risk / Rollback", ""),
        },
        "linked_issue": pr.get("closingIssuesReferences", []) or [],
        "required_template_sections": context.get("expected_template_sections")
        or parse_markdown_headings(read_text_if_exists(repo_root / ".github/pull_request_template.md")),
        "repo_guidance_paths": context.get("rule_files") or guidance_paths(repo_root),
        "diff_summary": {
            "diff_stat": context.get("diff_stat"),
            "diff_totals": diff_totals,
            "changed_file_count": len(changed_files),
            "generated_file_count": generated_file_count,
            "generated_file_ratio": round(generated_file_ratio, 3),
            "core_areas_touched": core_areas_touched,
        },
        "outdated_policy": {
            "default_decision": "defer-outdated",
            "code_change_default": "Do not assign implementation work to outdated threads by default.",
            "auto_resolve": "Only same-run outdated transitions may auto-resolve after current HEAD proof and real validation evidence.",
            "upgrade_rule": "Upgrade an outdated thread to accept only after verifying against the current HEAD that the issue still applies.",
            "completion_reply_default": "Do not post a completion reply for outdated threads unless they were upgraded to accept and fixed.",
        },
        "reject_policy": "Reject or defer with a concise reason and leave the thread unresolved.",
        "disallowed_actions": [
            "Do not add a top-level PR comment by default.",
            "Do not resolve rejected, deferred, or defer-outdated threads.",
            "Do not modify comments outside the exact managed marker policy.",
            "Do not claim tests, migrations, rollout safety, or user-visible behavior unless verified.",
            "Do not delegate broad or cross-cutting code changes to mini workers.",
        ],
        "disallowed_claims": [
            "Do not claim the issue is fixed until code and validation are complete.",
            "Do not claim a thread is outdated-and-safe unless current HEAD actually proves it.",
            "Do not claim config, workflow, or public-interface changes are low risk without checking the files.",
        ],
        "context_fingerprint": context_fingerprint(context),
        "review_mode_overrides": override_signals,
        "managed_reply_markers": {
            "ack": "<!-- codex:review-thread v1 phase=ack thread=<thread-id> -->",
            "complete": "<!-- codex:review-thread v1 phase=complete thread=<thread-id> -->",
            "update_priority": [
                "update the newest exact managed reply for the same phase and thread",
                "during ack only, adopt the newest unmarked self-authored reply after the latest reviewer comment and prepend the marker",
                "otherwise add a new reply",
                "never adopt an unmarked reply during complete",
            ],
        },
        "comment_contract": {
            "ack": [
                "summarize the reviewer request",
                "state accept, reject, defer, or defer-outdated",
                "state the implementation direction or blocker",
            ],
            "complete": [
                "summarize what changed",
                "list validation that actually ran",
                "note the remaining caveat only if it matters",
            ],
        },
        "code_change_delegation_policy": {
            "small_fix_only": True,
            "required_conditions": [
                "one batch or one thread",
                "two files or fewer",
                "one subsystem",
                "no schema, public interface, config, or workflow changes",
                "validation path is clear",
            ],
        },
    }

    batches = cluster_non_outdated_threads(unresolved_threads)
    thread_to_batch: dict[str, str] = {}
    batch_files: list[str] = []
    thread_files: list[str] = []
    marker_conflicts: list[dict[str, Any]] = []
    diff_cache: dict[str, str | None] = {}
    packet_quality_records: list[dict[str, Any]] = []
    runtime_payloads: dict[str, Any] = {}
    previous_threads = previous_thread_lookup(previous_context)
    transitioned_outdated_ids: set[str] = set()
    outdated_recheck_records: list[dict[str, Any]] = []

    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"batch-{batch_index:02d}"
        batch_file = packet_name("thread-batch", batch_index)
        batch_files.append(batch_file)
        path = str(batch.get("path") or "")
        line = batch["threads"][0].get("line") or batch["threads"][0].get("original_line")
        common_context = {
            "path": path,
            "path_exists": (repo_root / path).is_file(),
            "area": classify_path(path),
            "core_area": core_area_for_path(path),
            "generated_file": is_generated_file(path),
            "snippet": make_line_snippet(repo_root / path, int(line) if line else None),
            "diff_snippet": diff_snippet_for_path(
                repo_root,
                str(pr.get("baseRefName") or ""),
                str(pr.get("headRefName") or ""),
                path,
                int(line) if line else None,
                diff_cache,
            ),
        }
        batch_quality = packet_quality_basis(
            reviewer_bodies=[str((thread.get("reviewer_comment") or {}).get("body") or "") for thread in batch["threads"]],
            path=path,
            path_exists=bool(common_context["path_exists"]),
            snippet=common_context["snippet"],
            diff_snippet=common_context["diff_snippet"],
        )
        validation_candidates = validation_candidates_for_path(path, str(common_context["area"]), is_outdated=False)
        batch_payload = {
            "purpose": "Analyze a cluster of related unresolved non-outdated review threads together before choosing one fix direction.",
            "batch": {
                "batch_id": batch_id,
                "cluster_reason": batch["cluster_reason"],
                "path": path,
                "normalized_headline": batch.get("normalized_headline"),
                "reviewer_login": batch.get("reviewer_login"),
                "thread_ids": [thread["thread_id"] for thread in batch["threads"]],
            },
            "shared_fix_surface": {
                "path": path,
                "area": common_context["area"],
                "core_area": common_context["core_area"],
                "thread_count": len(batch["threads"]),
                "default_decision_candidate": "accept",
            },
            "common_file_context": common_context,
            "validation_candidates": validation_candidates,
            "quality_escape_hints": quality_escape_hints(batch_quality, path=path, is_outdated=False),
            "adjudication_basis": batch_quality,
            "threads": [],
        }
        for thread in batch["threads"]:
            thread_to_batch[str(thread["thread_id"])] = batch_id
            batch_payload["threads"].append(
                {
                    "thread_id": thread["thread_id"],
                    "line": thread.get("line"),
                    "original_line": thread.get("original_line"),
                    "reviewer_login": thread.get("reviewer_login"),
                    "reviewer_headline": reviewer_headline(thread),
                    "reviewer_comment_excerpt": safe_excerpt((thread.get("reviewer_comment") or {}).get("body")),
                    "latest_self_reply_excerpt": safe_excerpt((thread.get("latest_self_reply") or {}).get("body")),
                    "default_decision_candidate": candidate_decision(thread),
                }
            )
        write_json(output_dir / batch_file, batch_payload)
        runtime_payloads[batch_file] = batch_payload
        packet_quality_records.append({"packet": batch_file, **batch_quality})

    for thread_index, thread in enumerate(unresolved_threads, start=1):
        path = str(thread.get("path") or "")
        batch_id = thread_to_batch.get(str(thread["thread_id"]))
        file_policy = code_change_policy(path)
        thread_file = packet_name("thread", thread_index)
        thread_files.append(thread_file)
        line = thread.get("line") or thread.get("original_line")
        path_exists = (repo_root / path).is_file()
        area = classify_path(path)
        file_context = {
            "path_exists": path_exists,
            "area": area,
            "core_area": core_area_for_path(path),
            "generated_file": is_generated_file(path),
            "snippet": make_line_snippet(repo_root / path, int(line) if line else None),
            "diff_snippet": diff_snippet_for_path(
                repo_root,
                str(pr.get("baseRefName") or ""),
                str(pr.get("headRefName") or ""),
                path,
                int(line) if line else None,
                diff_cache,
            ),
        }
        quality_basis = packet_quality_basis(
            reviewer_bodies=[str((thread.get("reviewer_comment") or {}).get("body") or "")],
            path=path,
            path_exists=path_exists,
            snippet=file_context["snippet"],
            diff_snippet=file_context["diff_snippet"],
        )
        validation_candidates = validation_candidates_for_path(
            path,
            area,
            is_outdated=bool(thread.get("is_outdated")),
        )
        packet = {
            "purpose": "Analyze one unresolved review thread before deciding reply text, implementation scope, and resolution.",
            "thread": {
                "thread_id": thread["thread_id"],
                "batch_id": batch_id,
                "is_outdated": thread.get("is_outdated"),
                "path": path,
                "line": thread.get("line"),
                "start_line": thread.get("start_line"),
                "original_line": thread.get("original_line"),
                "reviewer_login": thread.get("reviewer_login"),
                "reviewer_headline": reviewer_headline(thread),
                "default_decision_candidate": candidate_decision(thread),
            },
            "reviewer_comment": comment_summary(thread.get("reviewer_comment")),
            "discussion": [
                {
                    "id": comment.get("id"),
                    "author_login": comment.get("author_login"),
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                    "managed_phase": comment.get("managed_phase"),
                    "body": comment.get("body"),
                }
                for comment in thread.get("comments", [])
            ],
            "existing_self_reply": comment_summary(thread.get("latest_self_reply")),
            "reply_candidates": thread.get("reply_candidates"),
            "reply_update_basis": reply_update_basis(thread.get("reply_candidates")),
            "file_context": file_context,
            "ownership_summary": {
                "path": path,
                "area": area,
                "core_area": file_context["core_area"],
                "path_exists": path_exists,
                "ownership_ambiguous": quality_basis["ownership_ambiguous"],
                "escape_threshold_exceeded": quality_basis["ownership_ambiguous"],
            },
            "applicability": {
                "default_decision_candidate": candidate_decision(thread),
                "small_fix_candidate": file_policy["small_fix_candidate"],
                "blockers": file_policy["blockers"],
            },
            "validation_candidates": validation_candidates,
            "quality_escape_hints": quality_escape_hints(
                quality_basis,
                path=path,
                is_outdated=bool(thread.get("is_outdated")),
                blockers=file_policy["blockers"],
            ),
            "adjudication_basis": quality_basis,
            "reply_update_basis_policy": "Advisory only; record explicit allowed reread reasons or stops before leaving the packet-first path.",
        }
        previous_thread = previous_threads.get(str(thread["thread_id"]))
        if transitioned_to_outdated(previous_thread, thread):
            accepted_thread = reconciliation_input["accepted_threads"].get(str(thread["thread_id"]))
            recheck = build_outdated_recheck(
                thread=thread,
                previous_thread=previous_thread,
                file_context=file_context,
                area=area,
                accepted_thread=accepted_thread,
            )
            transitioned_outdated_ids.add(str(thread["thread_id"]))
            packet["transitioned_to_outdated"] = True
            packet["thread"]["transitioned_to_outdated"] = True
            packet["outdated_recheck"] = recheck
            outdated_recheck_records.append(
                {
                    "thread_id": str(thread["thread_id"]),
                    "resolution_verdict": recheck["resolution_verdict"],
                    "auto_resolution_candidate": bool(recheck["auto_resolution_candidate"]),
                }
            )
        normalized_conflicts = normalize_marker_conflicts(thread)
        if normalized_conflicts:
            packet["marker_conflicts"] = normalized_conflicts
            marker_conflicts.extend(
                {
                    "thread_id": thread["thread_id"],
                    **item,
                }
                for item in normalized_conflicts
            )
        write_json(output_dir / thread_file, packet)
        runtime_payloads[thread_file] = packet
        packet_quality_records.append({"packet": thread_file, **quality_basis})

    active_paths = sorted({str(thread.get("path") or "") for thread in unresolved_non_outdated})
    active_areas = sorted(
        {
            classify_path(str(thread.get("path") or ""))
            for thread in unresolved_non_outdated
            if classify_path(str(thread.get("path") or "")) != "other"
        }
    )
    batched_thread_ids = set(thread_to_batch)
    singleton_packets = [
        packet_name("thread", index)
        for index, thread in enumerate(unresolved_threads, start=1)
        if not thread.get("is_outdated") and str(thread["thread_id"]) not in batched_thread_ids
    ]
    analysis_target_count = len(batch_files) + len(singleton_packets)
    packet_worker_map = derive_packet_worker_map(batch_files + singleton_packets)
    review_mode_baseline = determine_baseline_review_mode(
        unresolved_non_outdated_count=len(unresolved_non_outdated),
        active_path_count=len(active_paths),
        active_area_count=len(active_areas),
        analysis_target_count=analysis_target_count,
    )
    review_mode, review_mode_adjustments = apply_override_adjustment(
        review_mode_baseline,
        override_signals,
    )

    recommended_workers = derive_recommended_workers(
        review_mode=review_mode,
        global_packet_name=global_packet_name,
        analysis_packet_names=batch_files + singleton_packets,
        packet_worker_map=packet_worker_map,
        minimum_count=recommended_worker_minimum(
            review_mode,
            review_mode_adjustments,
        ),
    )
    optional_workers = derive_optional_workers(
        review_mode=review_mode,
        global_packet_name=global_packet_name,
        optional_qa_packets=(batch_files + singleton_packets)[:6],
    )

    common_path_failures = [
        {
            "packet": item["packet"],
            "required_evidence_present": item["required_evidence_present"],
            "ownership_ambiguous": item["ownership_ambiguous"],
            "explicit_reread_reasons": item["explicit_reread_reasons"],
            "validator_ready_recommendation_path": item["validator_ready_recommendation_path"],
        }
        for item in packet_quality_records
        if not bool(item["common_path_sufficient"])
    ]
    common_path_sufficient = not common_path_failures

    global_packet["orchestrator_profile"] = ORCHESTRATOR_PROFILE
    global_packet["common_path_contract"] = COMMON_PATH_CONTRACT
    global_packet["decision_ready_packets"] = DECISION_READY_PACKETS
    global_packet["worker_return_contract"] = WORKER_RETURN_CONTRACT
    global_packet["worker_output_shape"] = WORKER_OUTPUT_SHAPE
    global_packet["xhigh_reread_policy"] = XHIGH_REREAD_POLICY
    global_packet["preferred_worker_families"] = PREFERRED_WORKER_FAMILIES
    global_packet["packet_worker_map"] = packet_worker_map
    global_packet["routing_contract"] = {
        "routing_authority": "packet_worker_map",
        "preferred_worker_families_role": "registry_metadata_only",
        "derived_worker_fields": ["recommended_workers", "optional_workers"],
    }
    global_packet["marker_conflict_summary"] = marker_conflict_summary(unresolved_threads)
    global_packet["same_run_reconciliation"] = {
        "enabled": args.previous_context is not None,
        "transitioned_to_outdated_thread_ids": sorted(transitioned_outdated_ids),
        "outdated_transition_candidates": len(transitioned_outdated_ids),
        "outdated_auto_resolve_candidates": sum(
            1 for item in outdated_recheck_records if bool(item["auto_resolution_candidate"])
        ),
        "outdated_recheck_ambiguous": sum(
            1 for item in outdated_recheck_records if item["resolution_verdict"] == "ambiguous"
        ),
    }
    write_json(output_dir / global_packet_name, global_packet)
    runtime_payloads[global_packet_name] = global_packet

    packet_files = [global_packet_name, *thread_files, *batch_files, "orchestrator.json"]
    thread_counts = {
        "unresolved": len(unresolved_threads),
        "unresolved_non_outdated": len(unresolved_non_outdated),
        "unresolved_outdated": len(unresolved_outdated),
    }
    orchestrator = {
        "pr": {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "url": pr.get("url"),
        },
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "review_mode": review_mode,
        "review_mode_baseline": review_mode_baseline,
        "review_mode_adjustments": review_mode_adjustments,
        "shared_packet": global_packet_name,
        "context_fingerprint": context_fingerprint(context),
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "common_path_contract": COMMON_PATH_CONTRACT,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": packet_worker_map,
        "recommended_worker_count": len(recommended_workers),
        "optional_worker_count": len(optional_workers),
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
        "thread_counts": thread_counts,
        "active_paths": active_paths,
        "active_areas": active_areas,
        "analysis_targets": {
            "batch_count": len(batch_files),
            "singleton_count": len(singleton_packets),
        },
        "review_mode_overrides": override_signals,
        "marker_conflict_summary": marker_conflict_summary(unresolved_threads),
        "same_run_reconciliation": global_packet["same_run_reconciliation"],
        "thread_batches": {
            batch_id: [thread_id for thread_id, assigned_batch in thread_to_batch.items() if assigned_batch == batch_id]
            for batch_id in sorted(set(thread_to_batch.values()))
        },
        "local_responsibilities": [
            "Decide accept, reject, defer, or defer-outdated locally for each unresolved thread.",
            "Draft final acknowledgement and completion replies locally.",
            "Keep top-level PR comments out of scope unless the user asks for one.",
            "Keep broad or cross-cutting code changes local.",
            "Resolve a thread only after accepted work and validation are complete.",
        ],
        "raw_diff_policy": {
            "allowed_reasons": COMMON_PATH_CONTRACT["allowed_reread_reasons"],
            "note": "quality_escape_hints is advisory only; explicit reread or escape decisions must use the allowed reason enum or an explicit stop.",
        },
        "packet_files": packet_files,
    }
    write_json(output_dir / "orchestrator.json", orchestrator)
    runtime_payloads["orchestrator.json"] = orchestrator

    common_path_packet_names = [global_packet_name]
    analysis_packet_names = batch_files + thread_files
    if analysis_packet_names:
        largest_analysis_packet = max(
            analysis_packet_names,
            key=lambda name: len(json.dumps(runtime_payloads.get(name, {}), indent=2, ensure_ascii=True)),
        )
        common_path_packet_names.append(largest_analysis_packet)
    packet_metrics = compute_packet_metrics(
        runtime_payloads,
        common_path_packet_names=common_path_packet_names,
        local_only_sources={
            "context": context,
            "threads": unresolved_threads,
            "pr": pr,
            "changed_files": changed_files,
            "override_signals": override_signals,
        },
    )
    review_mode, review_mode_adjustments = maybe_apply_delegation_savings_floor(
        review_mode,
        packet_metrics,
        review_mode_adjustments,
    )
    recommended_workers = derive_recommended_workers(
        review_mode=review_mode,
        global_packet_name=global_packet_name,
        analysis_packet_names=batch_files + singleton_packets,
        packet_worker_map=packet_worker_map,
        minimum_count=recommended_worker_minimum(
            review_mode,
            review_mode_adjustments,
        ),
    )
    optional_workers = derive_optional_workers(
        review_mode=review_mode,
        global_packet_name=global_packet_name,
        optional_qa_packets=(batch_files + singleton_packets)[:6],
    )
    orchestrator["review_mode"] = review_mode
    orchestrator["review_mode_baseline"] = review_mode_baseline
    orchestrator["review_mode_adjustments"] = review_mode_adjustments
    orchestrator["recommended_worker_count"] = len(recommended_workers)
    orchestrator["optional_worker_count"] = len(optional_workers)
    orchestrator["recommended_workers"] = recommended_workers
    orchestrator["optional_workers"] = optional_workers
    runtime_payloads["orchestrator.json"] = orchestrator
    write_json(output_dir / "orchestrator.json", orchestrator)
    packet_metrics = compute_packet_metrics(
        runtime_payloads,
        common_path_packet_names=common_path_packet_names,
        local_only_sources={
            "context": context,
            "threads": unresolved_threads,
            "pr": pr,
            "changed_files": changed_files,
            "override_signals": override_signals,
        },
    )
    packet_metrics_path = output_dir / "packet_metrics.json"
    write_json(packet_metrics_path, packet_metrics)

    build_result = build_result_payload(
        review_mode=review_mode,
        review_mode_baseline=review_mode_baseline,
        review_mode_adjustments=review_mode_adjustments,
        recommended_workers=recommended_workers,
        optional_workers=optional_workers,
        thread_batch_count=len(batch_files),
        singleton_thread_packet_count=len(thread_files),
        active_paths=active_paths,
        override_signals=override_signals,
        common_path_sufficient=common_path_sufficient,
        common_path_failures=common_path_failures,
        thread_counts=thread_counts,
        same_run_reconciliation_enabled=args.previous_context is not None,
        outdated_transition_candidates=len(transitioned_outdated_ids),
        outdated_auto_resolve_candidates=sum(
            1 for item in outdated_recheck_records if bool(item["auto_resolution_candidate"])
        ),
        outdated_recheck_ambiguous=sum(
            1 for item in outdated_recheck_records if item["resolution_verdict"] == "ambiguous"
        ),
        packet_metrics_path=str(packet_metrics_path),
    )
    if args.result_output is not None:
        write_json(args.result_output, build_result)

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "review_mode": review_mode,
                "packet_files": packet_files,
                "recommended_worker_count": len(recommended_workers),
                "common_path_sufficient": common_path_sufficient,
                "result_output": str(args.result_output) if args.result_output else None,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
