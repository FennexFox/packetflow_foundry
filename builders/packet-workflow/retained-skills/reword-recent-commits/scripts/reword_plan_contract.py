from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SUBJECT_WITH_SCOPE_RE = re.compile(
    r"^(?P<type>[a-z][a-z0-9-]*)(?:\((?P<scope>[A-Za-z0-9._/-]+)\))?(?P<breaking>!)?: (?P<summary>.+)$"
)
SUBJECT_WITHOUT_SCOPE_RE = re.compile(
    r"^(?P<type>[a-z][a-z0-9-]*)(?P<breaking>!)?: (?P<summary>.+)$"
)

RULES_RELIABILITY_VALUES = ("explicit", "derived", "fallback")
VALIDATION_ERROR_CODES = {
    "invalid_plan_shape",
    "missing_commit",
    "missing_new_message",
    "duplicate_commit",
    "unknown_commit",
    "invalid_subject_format",
    "invalid_type",
    "missing_required_scope",
    "subject_too_long",
    "dirty_worktree",
    "detached_head",
    "active_git_operation",
    "merge_commit_in_scope",
    "root_rewrite_unsupported",
    "stale_context_fingerprint",
}
VALIDATION_WARNING_CODES = {
    "derived_rules_only",
    "fallback_rules_only",
    "body_recommended_missing",
    "upstream_configured",
    "branch_ahead",
    "branch_behind",
    "force_push_likely",
    "unchanged_message",
}
STOP_CATEGORIES = {
    "active_git_operation",
    "detached_head",
    "dirty_worktree",
    "merge_commit_in_scope",
    "root_rewrite_unsupported",
    "stale_context_fingerprint",
    "head_commit_drift",
    "recent_hash_drift",
    "replay_failed",
}

DECISION_READY_PACKETS = False
WORKER_RETURN_CONTRACT = "generic"
WORKER_OUTPUT_SHAPE = "flat"
COMMON_PATH_CONTRACT = {
    "shared_packets": ["rules_packet.json"],
    "focused_packet_mode": "read one commit packet at a time while keeping rules_packet.json in view",
    "goal": "Draft replacement messages without rereading raw commit history on the common path.",
}
RAW_REREAD_ALLOWED_REASONS = [
    "conflicting_signals",
    "missing_required_evidence",
    "schema_mismatch",
    "insufficient_excerpt_quality",
    "branch_tip_changed",
    "merge_commit_in_scope",
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
XHIGH_REREAD_POLICY = (
    "Packet-first local adjudication is required on the common path; raw rereads are only allowed for explicit exception reasons."
)
RUNTIME_STATUS_IGNORE_PREFIXES = (".codex/tmp/",)


def _stringify(value: Any) -> str:
    return str(value or "").strip()


def _normalize_path(value: Any) -> str:
    return _stringify(value).replace("\\", "/")


def _status_line_paths(line: str) -> list[str]:
    payload = line[3:].strip()
    if not payload:
        return []
    parts = payload.split(" -> ") if " -> " in payload else [payload]
    return [_normalize_path(part.strip().strip('"')) for part in parts if part.strip()]


def _is_runtime_status_line(line: str) -> bool:
    paths = _status_line_paths(line)
    return bool(paths) and all(
        any(path.startswith(prefix) for prefix in RUNTIME_STATUS_IGNORE_PREFIXES)
        for path in paths
    )


def _normalize_string_list(value: Any, *, sort_values: bool = False) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _stringify(item)
        if text:
            items.append(text)
    if sort_values:
        items = sorted(dict.fromkeys(items))
    return items


def _normalize_rules_section(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    normalized = {
        "format": _stringify(payload.get("format")) or None,
        "allowed_types": _normalize_string_list(payload.get("allowed_types")),
        "scope_required": None if payload.get("scope_required") is None else bool(payload.get("scope_required")),
        "scope_suggestions": _normalize_string_list(payload.get("scope_suggestions")),
        "subject_length_limit": None if payload.get("subject_length_limit") in {None, ""} else int(payload.get("subject_length_limit")),
        "subject_rules": _normalize_string_list(payload.get("subject_rules")),
        "body_rules": _normalize_string_list(payload.get("body_rules")),
        "references_rules": _normalize_string_list(payload.get("references_rules")),
        "repo_defaults": _normalize_string_list(payload.get("repo_defaults")),
    }
    return normalized


def _normalize_rule_derivation(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    keys = (
        "format_source",
        "allowed_types_source",
        "scope_required_source",
        "subject_length_limit_source",
        "repo_defaults_source",
    )
    return {key: _stringify(payload.get(key)) or None for key in keys}


def _normalize_rules_snapshot(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "rules": _normalize_rules_section(rules.get("rules")),
        "rule_derivation": _normalize_rule_derivation(rules.get("rule_derivation")),
        "recent_scope_vocabulary": _normalize_string_list(rules.get("recent_scope_vocabulary")),
        "recent_subject_samples": _normalize_string_list(rules.get("recent_subject_samples")),
    }


def _normalize_commit_snapshot(commit: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": int(commit.get("index") or 0),
        "hash": _stringify(commit.get("hash")),
        "parent_hashes": _normalize_string_list(commit.get("parent_hashes")),
        "subject": _stringify(commit.get("subject")),
        "files": [_normalize_path(path) for path in _normalize_string_list(commit.get("files"))],
        "shortstat": _stringify(commit.get("shortstat")),
    }


def _normalize_plan_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    commits = [
        _normalize_commit_snapshot(commit)
        for commit in plan.get("commits", [])
        if isinstance(commit, dict)
    ]
    commits.sort(key=lambda item: (int(item["index"]), item["hash"]))
    return {
        "branch": _stringify(plan.get("branch")),
        "head_commit": _stringify(plan.get("head_commit")),
        "base_commit": _stringify(plan.get("base_commit")) or None,
        "detached_head": bool(plan.get("detached_head")),
        "active_operation": _stringify(plan.get("active_operation")) or None,
        "count": int(plan.get("count") or len(commits)),
        "commits": commits,
    }


def stable_json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha256(payload: Any) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()


def packet_id(name: str) -> str:
    return Path(name).stem


def build_task_packet_names(commit_packet_names: list[str]) -> list[str]:
    return ["rules_packet.json", *commit_packet_names]


def build_task_packet_ids(commit_packet_names: list[str]) -> list[str]:
    return ["rules_packet", *[packet_id(name) for name in commit_packet_names]]


def build_packet_worker_map(commit_packet_names: list[str]) -> dict[str, list[str]]:
    return {
        "rules_packet": ["docs_verifier"],
        **{packet_id(name): ["evidence_summarizer"] for name in commit_packet_names},
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
    shared_packet_names = shared_packets or COMMON_PATH_CONTRACT["shared_packets"]
    packet_sizes = {
        name: json_bytes(payload)
        for name, payload in packet_payloads.items()
    }
    total_packet_bytes = sum(packet_sizes.values())
    largest_sizes = sorted(packet_sizes.values(), reverse=True)
    focused_sizes = [
        size
        for name, size in packet_sizes.items()
        if name.startswith("commit-")
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


def rules_reliability(rules: dict[str, Any]) -> str:
    sources = [value for value in _normalize_rule_derivation(rules.get("rule_derivation")).values() if value]
    if any(source not in {"recent_subjects", "fallback_default"} for source in sources):
        return "explicit"
    if any(source == "recent_subjects" for source in sources):
        return "derived"
    return "fallback"


def build_context_fingerprint(plan: dict[str, Any], rules: dict[str, Any]) -> str:
    payload = {
        "plan": _normalize_plan_snapshot(plan),
        "rules": _normalize_rules_snapshot(rules),
    }
    return _sha256(payload)


def context_fingerprint(plan: dict[str, Any], rules: dict[str, Any] | None = None) -> str:
    existing = _stringify(plan.get("context_fingerprint"))
    if existing:
        return existing
    if rules is None:
        raise RuntimeError("context_fingerprint is missing and rules were not provided")
    return build_context_fingerprint(plan, rules)


def normalize_rewrite_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for action in actions:
        normalized.append(
            {
                "index": int(action.get("index") or 0),
                "hash": _stringify(action.get("hash")),
                "new_message": str(action.get("new_message") or "").strip("\n"),
            }
        )
    normalized.sort(key=lambda item: (int(item["index"]), item["hash"]))
    return normalized


def build_message_set_fingerprint(actions: list[dict[str, Any]]) -> str:
    return _sha256(normalize_rewrite_actions(actions))


def message_set_fingerprint(actions: list[dict[str, Any]], existing: str | None = None) -> str:
    text = _stringify(existing)
    return text or build_message_set_fingerprint(actions)


def parse_subject_line(subject: str, format_hint: str | None = None) -> dict[str, Any] | None:
    subject = _stringify(subject)
    if not subject:
        return None
    parser = SUBJECT_WITH_SCOPE_RE if format_hint != "<type>: <subject>" else SUBJECT_WITHOUT_SCOPE_RE
    match = parser.match(subject)
    if not match and parser is SUBJECT_WITH_SCOPE_RE:
        match = SUBJECT_WITH_SCOPE_RE.match(subject)
    if not match:
        return None
    return {
        "type": match.group("type"),
        "scope": match.groupdict().get("scope") or "",
        "breaking": bool(match.groupdict().get("breaking")),
        "summary": match.group("summary"),
    }


def validation_message(code: str, *, commit_hash: str | None = None, index: int | None = None) -> str:
    prefix = ""
    if index is not None:
        prefix += f"commit #{index}"
    if commit_hash:
        prefix += f" ({commit_hash})" if prefix else f"commit {commit_hash}"
    if prefix:
        prefix += ": "
    mapping = {
        "invalid_plan_shape": "plan JSON must be an object with a `commits` list",
        "missing_commit": "raw plan must include every collected commit exactly once",
        "missing_new_message": "new_message is required for every commit",
        "duplicate_commit": "duplicate commit entry detected in raw plan",
        "unknown_commit": "commit is not present in the collected context",
        "invalid_subject_format": "new_message subject does not match the repo format",
        "invalid_type": "new_message type is not allowed by repo rules",
        "missing_required_scope": "new_message is missing a required scope",
        "subject_too_long": "new_message subject exceeds the repo limit",
        "dirty_worktree": "working tree must be clean before applying a history rewrite",
        "detached_head": "detached HEAD rewrites are not supported",
        "active_git_operation": "another git operation is already in progress",
        "merge_commit_in_scope": "merge commits are not supported by this workflow",
        "root_rewrite_unsupported": "root-commit rewrite is not supported because base_commit is null",
        "stale_context_fingerprint": "context_fingerprint does not match the current rules + context snapshot",
        "derived_rules_only": "repo rules were derived from recent history instead of explicit repo guidance",
        "fallback_rules_only": "repo rules fell back to the default format because explicit guidance was not found",
        "body_recommended_missing": "message body is recommended for this commit shape but is empty",
        "upstream_configured": "branch has an upstream and rewritten history will require coordination",
        "branch_ahead": "branch is ahead of upstream; force-push is likely after rewrite",
        "branch_behind": "branch is behind upstream; rewrite may diverge from the remote history",
        "force_push_likely": "history rewrite will likely require force-push-with-lease",
        "unchanged_message": "new_message matches the original commit message",
    }
    return prefix + mapping.get(code, code)


def build_issue(
    level: str,
    code: str,
    *,
    commit_hash: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    issue = {
        "level": level,
        "code": code,
        "message": validation_message(code, commit_hash=commit_hash, index=index),
    }
    if commit_hash:
        issue["hash"] = commit_hash
    if index is not None:
        issue["index"] = index
    return issue


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_git(repo: Path, args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout


def detect_operation(repo_root: Path) -> str | None:
    git_dir = Path(run_git(repo_root, ["rev-parse", "--git-dir"]).strip())
    if not git_dir.is_absolute():
        git_dir = repo_root / git_dir
    markers = {
        "rebase": [git_dir / "rebase-merge", git_dir / "rebase-apply"],
        "cherry-pick": [git_dir / "CHERRY_PICK_HEAD"],
        "merge": [git_dir / "MERGE_HEAD"],
        "bisect": [git_dir / "BISECT_LOG"],
    }
    for name, paths in markers.items():
        if any(path.exists() for path in paths):
            return name
    return None


def branch_state(repo_root: Path) -> dict[str, Any]:
    branch = run_git(repo_root, ["branch", "--show-current"]).strip()
    status_porcelain = run_git(repo_root, ["status", "--porcelain", "--untracked-files=all"], check=False)
    status_branch = run_git(repo_root, ["status", "--short", "--branch"], check=False)
    upstream = run_git(
        repo_root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    ).strip()
    ahead = 0
    behind = 0
    if upstream:
        counts = run_git(repo_root, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], check=False).strip()
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])
    dirty_lines = [
        line
        for line in status_porcelain.splitlines()
        if line.strip() and not _is_runtime_status_line(line)
    ]
    return {
        "branch": branch,
        "status_branch_line": status_branch.splitlines()[0] if status_branch.splitlines() else "",
        "working_tree_dirty": bool(dirty_lines),
        "upstream_branch": upstream or None,
        "ahead_count": ahead,
        "behind_count": behind,
        "force_push_likely": bool(upstream),
    }


def recent_hashes(repo_root: Path, count: int) -> list[str]:
    output = run_git(repo_root, ["rev-list", "--max-count", str(count), "--reverse", "HEAD"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _raw_plan_commits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    commits = payload.get("commits")
    if isinstance(commits, list):
        return [commit for commit in commits if isinstance(commit, dict)]
    raise RuntimeError("plan JSON must be an object with a `commits` list")


def _validate_runtime_state(
    context: dict[str, Any],
    *,
    repo_state: dict[str, Any] | None = None,
    active_operation: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    stop_reasons: list[str] = []

    if bool(context.get("detached_head")):
        errors.append(build_issue("error", "detached_head"))
        stop_reasons.append("detached_head")
    operation = _stringify(active_operation or context.get("active_operation"))
    if operation:
        errors.append(build_issue("error", "active_git_operation"))
        stop_reasons.append("active_git_operation")
    if not _stringify(context.get("base_commit")):
        errors.append(build_issue("error", "root_rewrite_unsupported"))
        stop_reasons.append("root_rewrite_unsupported")
    merge_indexes = [
        int(commit.get("index") or 0)
        for commit in context.get("commits", [])
        if isinstance(commit, dict) and len(commit.get("parent_hashes", []) or []) > 1
    ]
    if merge_indexes:
        errors.append(build_issue("error", "merge_commit_in_scope"))
        stop_reasons.append("merge_commit_in_scope")

    state = repo_state or {}
    if state.get("working_tree_dirty"):
        errors.append(build_issue("error", "dirty_worktree"))
        stop_reasons.append("dirty_worktree")
    if state.get("upstream_branch"):
        warnings.append(build_issue("warning", "upstream_configured"))
    if int(state.get("ahead_count") or 0) > 0:
        warnings.append(build_issue("warning", "branch_ahead"))
    if int(state.get("behind_count") or 0) > 0:
        warnings.append(build_issue("warning", "branch_behind"))
    if state.get("force_push_likely"):
        warnings.append(build_issue("warning", "force_push_likely"))
    return errors, warnings, stop_reasons


def validate_reword_plan_payload(
    context: dict[str, Any],
    rules: dict[str, Any],
    raw_plan: dict[str, Any],
    *,
    repo_state: dict[str, Any] | None = None,
    active_operation: str | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    stop_reasons: list[str] = []

    expected_context_fingerprint = build_context_fingerprint(context, rules)
    actual_context_fingerprint = context_fingerprint(context, rules)
    fingerprint_match = expected_context_fingerprint == actual_context_fingerprint
    if not fingerprint_match:
        errors.append(build_issue("error", "stale_context_fingerprint"))
        stop_reasons.append("stale_context_fingerprint")

    runtime_errors, runtime_warnings, runtime_stop_reasons = _validate_runtime_state(
        context,
        repo_state=repo_state,
        active_operation=active_operation,
    )
    errors.extend(runtime_errors)
    warnings.extend(runtime_warnings)
    stop_reasons.extend(runtime_stop_reasons)

    reliability = rules_reliability(rules)
    if reliability == "derived":
        warnings.append(build_issue("warning", "derived_rules_only"))
    elif reliability == "fallback":
        warnings.append(build_issue("warning", "fallback_rules_only"))

    context_commits = [
        commit
        for commit in context.get("commits", [])
        if isinstance(commit, dict)
    ]
    context_by_hash = {_stringify(commit.get("hash")): commit for commit in context_commits}
    context_by_index = {int(commit.get("index") or 0): commit for commit in context_commits}

    try:
        raw_commits = _raw_plan_commits(raw_plan)
    except RuntimeError:
        raw_commits = []
        errors.append(build_issue("error", "invalid_plan_shape"))

    seen_hashes: set[str] = set()
    seen_indexes: set[int] = set()
    normalized_actions: list[dict[str, Any]] = []

    for raw_commit in raw_commits:
        commit_hash = _stringify(raw_commit.get("hash"))
        index = int(raw_commit.get("index") or 0)
        if not commit_hash or commit_hash not in context_by_hash:
            errors.append(build_issue("error", "unknown_commit", commit_hash=commit_hash or None, index=index or None))
            continue
        if index and index not in context_by_index:
            errors.append(build_issue("error", "unknown_commit", commit_hash=commit_hash, index=index))
            continue
        if commit_hash in seen_hashes or index in seen_indexes:
            errors.append(build_issue("error", "duplicate_commit", commit_hash=commit_hash, index=index))
            continue
        seen_hashes.add(commit_hash)
        seen_indexes.add(index)

        context_commit = context_by_hash[commit_hash]
        actual_index = int(context_commit.get("index") or index)
        new_message = str(raw_commit.get("new_message") or "").strip("\n")
        if not new_message.strip():
            errors.append(build_issue("error", "missing_new_message", commit_hash=commit_hash, index=actual_index))
            continue

        normalized_actions.append(
            {
                "index": actual_index,
                "hash": commit_hash,
                "new_message": new_message,
            }
        )

    if len(raw_commits) != len(context_commits):
        errors.append(build_issue("error", "missing_commit"))
    elif len(seen_hashes) != len(context_commits):
        errors.append(build_issue("error", "missing_commit"))

    rules_section = _normalize_rules_section(rules.get("rules"))
    format_hint = rules_section.get("format")
    allowed_types = set(rules_section.get("allowed_types") or [])
    scope_required = rules_section.get("scope_required")
    subject_length_limit = rules_section.get("subject_length_limit")

    normalized_actions = normalize_rewrite_actions(normalized_actions)
    for action in normalized_actions:
        commit_hash = action["hash"]
        index = int(action["index"])
        new_message = str(action["new_message"])
        subject, _sep, body = new_message.partition("\n")
        parsed_subject = parse_subject_line(subject, format_hint)
        if parsed_subject is None:
            errors.append(build_issue("error", "invalid_subject_format", commit_hash=commit_hash, index=index))
            continue
        message_type = _stringify(parsed_subject.get("type"))
        scope = _stringify(parsed_subject.get("scope"))
        if allowed_types and message_type not in allowed_types:
            errors.append(build_issue("error", "invalid_type", commit_hash=commit_hash, index=index))
        if scope_required and not scope:
            errors.append(build_issue("error", "missing_required_scope", commit_hash=commit_hash, index=index))
        if subject_length_limit and len(subject.strip()) > int(subject_length_limit):
            errors.append(build_issue("error", "subject_too_long", commit_hash=commit_hash, index=index))

        context_commit = context_by_hash.get(commit_hash, {})
        original_message = str(context_commit.get("full_message") or "").strip("\n")
        if original_message == new_message.strip("\n"):
            warnings.append(build_issue("warning", "unchanged_message", commit_hash=commit_hash, index=index))
        body_recommended = False
        files = context_commit.get("files", []) or []
        if len(files) > 1:
            body_recommended = True
        elif str(context_commit.get("body") or "").strip():
            body_recommended = True
        if body_recommended and not body.strip():
            warnings.append(build_issue("warning", "body_recommended_missing", commit_hash=commit_hash, index=index))

    counters = {
        "entry_count": len(raw_commits),
        "normalized_entry_count": len(normalized_actions),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "commits_validated": len(normalized_actions),
        "rules_reliability": reliability,
        "force_push_needed": bool((repo_state or {}).get("force_push_likely")),
    }
    envelope = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counters": counters,
        "context_fingerprint": expected_context_fingerprint,
        "message_set_fingerprint": build_message_set_fingerprint(normalized_actions),
        "normalized_rewrite_actions": normalized_actions,
        "rewrite_scope": {
            "branch": _stringify(context.get("branch")),
            "count": int(context.get("count") or len(context_commits)),
            "head_commit": _stringify(context.get("head_commit")),
            "base_commit": _stringify(context.get("base_commit")) or None,
        },
        "rules_reliability": reliability,
        "fingerprint_match": fingerprint_match,
        "stop_reasons": sorted(dict.fromkeys(stop_reasons)),
    }
    return envelope


def load_normalized_plan_envelope(context: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise RuntimeError("validated plan must be a JSON object")
    actions = plan.get("normalized_rewrite_actions")
    if not isinstance(actions, list):
        raise RuntimeError("validated plan is missing normalized_rewrite_actions")
    if not bool(plan.get("valid")):
        raise RuntimeError("validated plan is not valid")
    expected_fingerprint = context_fingerprint(context)
    actual_fingerprint = _stringify(plan.get("context_fingerprint"))
    if expected_fingerprint != actual_fingerprint:
        raise RuntimeError(validation_message("stale_context_fingerprint"))
    return {
        "context_fingerprint": actual_fingerprint,
        "message_set_fingerprint": message_set_fingerprint(actions, existing=_stringify(plan.get("message_set_fingerprint"))),
        "fingerprint_match": True,
        "normalized_rewrite_actions": normalize_rewrite_actions(actions),
        "warnings": plan.get("warnings", []),
        "counters": plan.get("counters", {}),
        "rewrite_scope": plan.get("rewrite_scope", {}),
        "rules_reliability": _stringify(plan.get("rules_reliability")) or None,
        "stop_reasons": plan.get("stop_reasons", []),
    }
