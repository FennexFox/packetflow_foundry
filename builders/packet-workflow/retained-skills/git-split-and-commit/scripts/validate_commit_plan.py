#!/usr/bin/env python3
"""Validate and normalize a commit plan against a collected worktree snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from collect_worktree_context import build_worktree_context


PLAN_PHASE_FIELD_TABLES = {
    "draft_plan": {
        "top_level": {
            "required": [
                "repo_root",
                "base_head",
                "worktree_fingerprint",
                "input_scope",
                "overall_confidence",
                "validation_commands",
                "omitted_paths",
                "stop_reasons",
                "commits",
            ],
            "allowed": [],
            "ignored": [],
        },
        "commit": {
            "required": [
                "commit_index",
                "intent_summary",
                "type",
                "scope",
                "subject",
                "body",
                "whole_file_paths",
                "untracked_paths",
                "split_paths",
                "selected_hunk_ids",
                "supporting_paths",
                "targeted_checks",
                "confidence",
            ],
            "allowed": [],
            "ignored": [],
        },
    },
    "normalized_plan": {
        "top_level": {
            "required": [
                "repo_root",
                "base_head",
                "worktree_fingerprint",
                "input_scope",
                "overall_confidence",
                "validation_commands",
                "omitted_paths",
                "stop_reasons",
                "commits",
            ],
            "allowed": [],
            "ignored": [],
        },
        "commit": {
            "required": [
                "commit_index",
                "intent_summary",
                "type",
                "scope",
                "subject",
                "body",
                "whole_file_paths",
                "untracked_paths",
                "split_paths",
                "selected_hunk_ids",
                "supporting_paths",
                "targeted_checks",
                "confidence",
            ],
            "allowed": [],
            "ignored": [],
        },
    },
}

VALIDATION_ERROR_CODES = {
    "missing_field": "E_PLAN_MISSING_FIELD",
    "empty_commits": "E_PLAN_EMPTY_COMMITS",
    "head_changed": "E_PLAN_HEAD_CHANGED",
    "fingerprint_changed": "E_PLAN_FINGERPRINT_CHANGED",
    "active_git_operation": "E_PLAN_ACTIVE_GIT_OPERATION",
    "repo_root_mismatch": "E_PLAN_REPO_ROOT_MISMATCH",
    "base_head_mismatch": "E_PLAN_BASE_HEAD_MISMATCH",
    "worktree_fingerprint_mismatch": "E_PLAN_WORKTREE_FINGERPRINT_MISMATCH",
    "duplicate_validation_command": "E_PLAN_DUPLICATE_VALIDATION_COMMAND",
    "commit_not_object": "E_PLAN_COMMIT_NOT_OBJECT",
    "unknown_path": "E_PLAN_UNKNOWN_PATH",
    "invalid_untracked_path": "E_PLAN_INVALID_UNTRACKED_PATH",
    "invalid_split_path": "E_PLAN_INVALID_SPLIT_PATH",
    "partial_split_unsupported": "E_PLAN_PARTIAL_SPLIT_UNSUPPORTED",
    "unknown_hunk": "E_PLAN_UNKNOWN_HUNK",
    "path_assignment_mismatch": "E_PLAN_PATH_ASSIGNMENT_MISMATCH",
    "hunk_assignment_mismatch": "E_PLAN_HUNK_ASSIGNMENT_MISMATCH",
    "ambiguous_split_rematch": "E_PLAN_AMBIGUOUS_SPLIT_REMATCH",
    "adjacent_split_hunks": "E_PLAN_ADJACENT_SPLIT_HUNKS",
    "targeted_check_unavailable": "E_PLAN_TARGETED_CHECK_UNAVAILABLE",
}

VALIDATION_WARNING_CODES = {
    "unknown_top_level_field": "W_PLAN_UNKNOWN_TOP_LEVEL_FIELD",
    "unknown_commit_field": "W_PLAN_UNKNOWN_COMMIT_FIELD",
    "body_string_normalized": "W_PLAN_BODY_STRING_NORMALIZED",
    "commit_index_non_sequential": "W_PLAN_COMMIT_INDEX_NON_SEQUENTIAL",
    "empty_scope": "W_PLAN_EMPTY_SCOPE",
    "non_bullet_body": "W_PLAN_NON_BULLET_BODY",
    "targeted_check_missing_from_plan": "W_PLAN_TARGETED_CHECK_MISSING_FROM_PLAN",
}

VALIDATOR_COVERED_STOP_CATEGORIES = [
    "active_git_operation",
    "ambiguous_split_rematch",
    "low_confidence",
    "partial_split_unsupported",
    "stale_context",
    "targeted_check_unavailable",
    "validator_mismatch",
    "unresolved_stop_reason",
]

LOCAL_HARD_STOP_CATEGORIES = [
    "active_git_operation",
    "ambiguous_split_rematch",
    "commit_creation_failed",
    "partial_split_unsupported",
    "rollback_failed",
    "targeted_check_failed",
    "targeted_check_unavailable",
    "validator_mismatch",
]

NON_APPLICABLE_STOP_CATEGORIES = [
    "missing_auth",
    "missing_required_evidence",
]

WINDOWS_SHELL_BUILTINS = {
    "assoc",
    "break",
    "call",
    "cd",
    "chcp",
    "cls",
    "copy",
    "date",
    "del",
    "dir",
    "echo",
    "endlocal",
    "erase",
    "exit",
    "for",
    "ftype",
    "if",
    "md",
    "mkdir",
    "mklink",
    "move",
    "path",
    "pause",
    "popd",
    "prompt",
    "pushd",
    "rd",
    "rem",
    "ren",
    "rename",
    "rmdir",
    "set",
    "setlocal",
    "shift",
    "start",
    "time",
    "title",
    "type",
    "ver",
    "verify",
    "vol",
}

POSIX_SHELL_BUILTINS = {
    ".",
    ":",
    "alias",
    "bg",
    "break",
    "cd",
    "command",
    "continue",
    "echo",
    "eval",
    "exec",
    "exit",
    "export",
    "false",
    "fg",
    "getopts",
    "hash",
    "jobs",
    "pwd",
    "read",
    "readonly",
    "return",
    "set",
    "shift",
    "test",
    "times",
    "trap",
    "true",
    "type",
    "ulimit",
    "umask",
    "unalias",
    "unset",
    "wait",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def command_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                command = str(item.get("command", "")).strip()
            else:
                command = str(item).strip()
            if command:
                result.append(command)
        return result
    if isinstance(value, dict):
        command = str(value.get("command", "")).strip()
        return [command] if command else []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def normalize_body(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line for line in value.splitlines() if line.strip()]
    return [str(value)]


def normalize_path_string(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return os.path.normcase(os.path.normpath(text))


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def command_head_token(command: str) -> str | None:
    match = re.match(r'\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))', command or "")
    if not match:
        return None
    for group in match.groups():
        if group:
            return group
    return None


def builtin_command_names() -> set[str]:
    return WINDOWS_SHELL_BUILTINS if os.name == "nt" else POSIX_SHELL_BUILTINS


def resolve_command_executable(repo_root: Path, token: str) -> str | None:
    candidate = str(token).strip()
    if not candidate:
        return None
    lowered = candidate.lower()
    if lowered in builtin_command_names():
        return candidate

    path_candidate = Path(candidate)
    if path_candidate.is_absolute() or any(separator in candidate for separator in ("/", "\\")):
        base_path = path_candidate if path_candidate.is_absolute() else (repo_root / path_candidate)
        candidates = [base_path]
        if os.name == "nt" and not base_path.suffix:
            for extension in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";"):
                extension = extension.strip()
                if extension:
                    candidates.append(Path(str(base_path) + extension))
        for resolved in candidates:
            if resolved.is_file():
                return str(resolved)
        return None

    located = shutil.which(candidate)
    if located:
        return located
    if os.name == "nt" and not path_candidate.suffix:
        for extension in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";"):
            extension = extension.strip()
            if not extension:
                continue
            located = shutil.which(candidate + extension)
            if located:
                return located
    return None


def command_feasibility_issues(repo_root: Path, commands: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for command in dedupe_preserve(commands):
        token = command_head_token(command)
        if token is None:
            issues.append(
                {
                    "command": command,
                    "detail": "command is empty or does not expose a launch token",
                }
            )
            continue
        if resolve_command_executable(repo_root, token) is None:
            issues.append(
                {
                    "command": command,
                    "detail": f"command executable `{token}` is unavailable on PATH or at the referenced path",
                }
            )
    return issues


def json_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def push_issue(
    messages: list[str],
    details: list[dict[str, Any]],
    *,
    code: str,
    message: str,
    field: str | None = None,
    commit_index: int | None = None,
    path: str | None = None,
    hunk_id: str | None = None,
    stop_category: str | None = None,
    command: str | None = None,
) -> None:
    messages.append(message)
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    if commit_index is not None:
        detail["commit_index"] = commit_index
    if path is not None:
        detail["path"] = path
    if hunk_id is not None:
        detail["hunk_id"] = hunk_id
    if stop_category is not None:
        detail["stop_category"] = stop_category
    if command is not None:
        detail["command"] = command
    details.append(detail)


def required_keys(
    payload: dict[str, Any],
    keys: list[str],
    errors: list[str],
    error_details: list[dict[str, Any]],
    prefix: str,
    *,
    commit_index: int | None = None,
) -> None:
    for key in keys:
        if key not in payload:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_field"],
                message=f"{prefix} missing required field `{key}`.",
                field=key,
                commit_index=commit_index,
            )


def unknown_fields(
    payload: dict[str, Any],
    *,
    phase: str,
    scope: str,
    warnings: list[str],
    warning_details: list[dict[str, Any]],
    commit_index: int | None = None,
) -> None:
    rules = PLAN_PHASE_FIELD_TABLES[phase][scope]
    allowed = set(rules["required"]) | set(rules["allowed"]) | set(rules["ignored"])
    code = (
        VALIDATION_WARNING_CODES["unknown_top_level_field"]
        if scope == "top_level"
        else VALIDATION_WARNING_CODES["unknown_commit_field"]
    )
    for field in sorted(set(payload) - allowed):
        push_issue(
            warnings,
            warning_details,
            code=code,
            message=f"Removed unknown {scope.replace('_', ' ')} field `{field}` during normalization.",
            field=field,
            commit_index=commit_index,
        )


def normalize_commit(
    commit: dict[str, Any],
    expected_index: int,
    warnings: list[str],
    warning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    commit_index = safe_int(commit.get("commit_index"), expected_index)
    unknown_fields(
        commit,
        phase="draft_plan",
        scope="commit",
        warnings=warnings,
        warning_details=warning_details,
        commit_index=commit_index,
    )
    normalized = {
        "commit_index": commit_index,
        "intent_summary": str(commit.get("intent_summary", "")).strip(),
        "type": str(commit.get("type", "")).strip(),
        "scope": str(commit.get("scope", "")).strip(),
        "subject": str(commit.get("subject", "")).strip(),
        "body": normalize_body(commit.get("body")),
        "whole_file_paths": string_list(commit.get("whole_file_paths")),
        "untracked_paths": string_list(commit.get("untracked_paths")),
        "split_paths": string_list(commit.get("split_paths")),
        "selected_hunk_ids": string_list(commit.get("selected_hunk_ids")),
        "supporting_paths": string_list(commit.get("supporting_paths")),
        "targeted_checks": string_list(commit.get("targeted_checks")),
        "confidence": str(commit.get("confidence", "")).strip().lower(),
    }
    if isinstance(commit.get("body"), str):
        push_issue(
            warnings,
            warning_details,
            code=VALIDATION_WARNING_CODES["body_string_normalized"],
            message=f"Commit {commit_index} normalized string `body` into bullet lines.",
            field="body",
            commit_index=commit_index,
        )
    return normalized


def normalize_plan(
    plan: dict[str, Any],
    warnings: list[str],
    warning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    unknown_fields(
        plan,
        phase="draft_plan",
        scope="top_level",
        warnings=warnings,
        warning_details=warning_details,
    )
    normalized_commits: list[dict[str, Any]] = []
    if isinstance(plan.get("commits"), list):
        for expected_index, commit in enumerate(plan["commits"], start=1):
            if isinstance(commit, dict):
                normalized_commits.append(normalize_commit(commit, expected_index, warnings, warning_details))
    return {
        "repo_root": str(plan.get("repo_root", "")).strip(),
        "base_head": str(plan.get("base_head", "")).strip(),
        "worktree_fingerprint": str(plan.get("worktree_fingerprint", "")).strip(),
        "input_scope": str(plan.get("input_scope", "")).strip(),
        "overall_confidence": str(plan.get("overall_confidence", "")).strip().lower(),
        "validation_commands": command_strings(plan.get("validation_commands")),
        "omitted_paths": string_list(plan.get("omitted_paths")),
        "stop_reasons": string_list(plan.get("stop_reasons")),
        "commits": normalized_commits,
    }


def build_apply_gate_status(current_stop_categories: list[str], can_apply: bool) -> dict[str, Any]:
    return {
        "status": "pass" if can_apply else "fail",
        "applicable_stop_categories": VALIDATOR_COVERED_STOP_CATEGORIES,
        "covered_stop_categories": VALIDATOR_COVERED_STOP_CATEGORIES,
        "uncovered_stop_categories": [],
        "not_applicable_stop_categories": NON_APPLICABLE_STOP_CATEGORIES,
        "local_hard_stop_categories": LOCAL_HARD_STOP_CATEGORIES,
        "current_stop_categories": current_stop_categories,
    }


def validate_plan_against_worktree(worktree: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    error_details: list[dict[str, Any]] = []
    warning_details: list[dict[str, Any]] = []

    required_keys(
        plan,
        PLAN_PHASE_FIELD_TABLES["draft_plan"]["top_level"]["required"],
        errors,
        error_details,
        "plan",
    )
    commits = plan.get("commits", [])
    if not isinstance(commits, list) or not commits:
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["empty_commits"],
            message="plan must contain a non-empty `commits` list.",
            field="commits",
        )
        commits = []
    for expected_index, commit in enumerate(commits, start=1):
        if not isinstance(commit, dict):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["commit_not_object"],
                message=f"plan commit entry {expected_index} is not an object.",
                commit_index=expected_index,
            )
            continue
        required_keys(
            commit,
            PLAN_PHASE_FIELD_TABLES["draft_plan"]["commit"]["required"],
            errors,
            error_details,
            f"commit {expected_index}",
            commit_index=expected_index,
        )

    normalized_plan = normalize_plan(plan, warnings, warning_details)
    normalized_plan_fingerprint = json_fingerprint(normalized_plan)
    repo_root = Path(str(worktree.get("repo_root", "")))
    current_worktree = build_worktree_context(repo_root, list(worktree.get("pathspecs", [])))
    active_operation = str(current_worktree.get("active_operation") or worktree.get("active_operation") or "").strip()
    if active_operation:
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["active_git_operation"],
            message=f"Active git operation `{active_operation}` is in progress; stop and resume after it completes.",
            field="active_operation",
            stop_category="active_git_operation",
        )
    if current_worktree.get("head_commit") != worktree.get("head_commit"):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["head_changed"],
            message="HEAD changed since worktree collection; regenerate the worktree snapshot.",
            field="base_head",
            stop_category="stale_context",
        )
    if current_worktree.get("worktree_fingerprint") != worktree.get("worktree_fingerprint"):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["fingerprint_changed"],
            message="Current worktree fingerprint no longer matches the collected snapshot.",
            field="worktree_fingerprint",
            stop_category="stale_context",
        )
    if normalize_path_string(normalized_plan.get("repo_root")) != normalize_path_string(worktree.get("repo_root")):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["repo_root_mismatch"],
            message="plan `repo_root` does not match the collected worktree repo_root.",
            field="repo_root",
            stop_category="validator_mismatch",
        )
    if str(normalized_plan.get("base_head", "")) != str(worktree.get("head_commit", "")):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["base_head_mismatch"],
            message="plan `base_head` does not match the collected worktree HEAD.",
            field="base_head",
            stop_category="validator_mismatch",
        )
    if str(normalized_plan.get("worktree_fingerprint", "")) != str(worktree.get("worktree_fingerprint", "")):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["worktree_fingerprint_mismatch"],
            message="plan `worktree_fingerprint` does not match the collected worktree fingerprint.",
            field="worktree_fingerprint",
            stop_category="validator_mismatch",
        )

    worktree_files = {str(entry["path"]): entry for entry in worktree.get("files", [])}
    hunk_to_path: dict[str, str] = {}
    for path, entry in worktree_files.items():
        for hunk in entry.get("hunks", []):
            hunk_id = str(hunk["hunk_id"])
            if hunk_id in hunk_to_path:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["hunk_assignment_mismatch"],
                    message=f"Hunk id `{hunk_id}` is duplicated in the collected worktree snapshot.",
                    path=path,
                    hunk_id=hunk_id,
                )
            hunk_to_path[hunk_id] = path

    omitted_paths = set(normalized_plan.get("omitted_paths", []))
    path_assignments: dict[str, int] = {}
    split_hunk_assignments: dict[str, int] = {}
    split_path_to_commits: dict[str, set[int]] = {}
    union_targeted_checks: list[str] = []
    plan_validation_commands = command_strings(normalized_plan.get("validation_commands"))
    if len(plan_validation_commands) != len(dict.fromkeys(plan_validation_commands)):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["duplicate_validation_command"],
            message="plan `validation_commands` contains duplicates.",
            field="validation_commands",
        )

    for expected_index, commit in enumerate(normalized_plan.get("commits", []), start=1):
        commit_index = int(commit.get("commit_index", expected_index))
        if commit_index != expected_index:
            push_issue(
                warnings,
                warning_details,
                code=VALIDATION_WARNING_CODES["commit_index_non_sequential"],
                message=f"Commit indexes are not sequential at position {expected_index}.",
                field="commit_index",
                commit_index=commit_index,
            )
        whole_file_paths = string_list(commit.get("whole_file_paths"))
        untracked_paths = string_list(commit.get("untracked_paths"))
        split_paths = string_list(commit.get("split_paths"))
        selected_hunk_ids = string_list(commit.get("selected_hunk_ids"))
        supporting_paths = string_list(commit.get("supporting_paths"))
        targeted_checks = string_list(commit.get("targeted_checks"))
        body_lines = normalize_body(commit.get("body"))

        for command in targeted_checks:
            if command not in union_targeted_checks:
                union_targeted_checks.append(command)
            if command not in plan_validation_commands:
                push_issue(
                    warnings,
                    warning_details,
                    code=VALIDATION_WARNING_CODES["targeted_check_missing_from_plan"],
                    message=f"Commit {commit_index} targeted check is missing from plan `validation_commands`: {command}",
                    field="targeted_checks",
                    commit_index=commit_index,
                )

        for path in whole_file_paths:
            if path in omitted_paths:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                    message=f"Path `{path}` is both omitted and committed as whole-file.",
                    path=path,
                    commit_index=commit_index,
                )
            if path not in worktree_files:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["unknown_path"],
                    message=f"Commit {commit_index} references unknown path `{path}`.",
                    path=path,
                    commit_index=commit_index,
                )
                continue
            path_assignments[path] = path_assignments.get(path, 0) + 1
            entry = worktree_files[path]
            if entry.get("change_kind") == "untracked":
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["invalid_untracked_path"],
                    message=f"Commit {commit_index} puts untracked path `{path}` in `whole_file_paths`; use `untracked_paths`.",
                    path=path,
                    commit_index=commit_index,
                )
            if path in split_paths:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["invalid_split_path"],
                    message=f"Commit {commit_index} references `{path}` as both whole-file and split.",
                    path=path,
                    commit_index=commit_index,
                )

        # Supporting paths are evidence-only references. Validate that they resolve to
        # known changed paths, but do not count them toward path ownership.
        for path in supporting_paths:
            if path not in worktree_files:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["unknown_path"],
                    message=f"Commit {commit_index} references unknown supporting path `{path}`.",
                    path=path,
                    commit_index=commit_index,
                )

        for path in untracked_paths:
            if path in omitted_paths:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                    message=f"Path `{path}` is both omitted and committed as untracked.",
                    path=path,
                    commit_index=commit_index,
                )
            if path not in worktree_files:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["unknown_path"],
                    message=f"Commit {commit_index} references unknown untracked path `{path}`.",
                    path=path,
                    commit_index=commit_index,
                )
                continue
            path_assignments[path] = path_assignments.get(path, 0) + 1
            entry = worktree_files[path]
            if entry.get("change_kind") != "untracked":
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["invalid_untracked_path"],
                    message=f"Commit {commit_index} lists tracked path `{path}` in `untracked_paths`.",
                    path=path,
                    commit_index=commit_index,
                )
            if path in split_paths:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["invalid_split_path"],
                    message=f"Commit {commit_index} references `{path}` as both untracked and split.",
                    path=path,
                    commit_index=commit_index,
                )

        split_hunks_by_path: dict[str, list[str]] = {}
        for hunk_id in selected_hunk_ids:
            path = hunk_to_path.get(hunk_id)
            if path is None:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["unknown_hunk"],
                    message=f"Commit {commit_index} references unknown hunk id `{hunk_id}`.",
                    commit_index=commit_index,
                    hunk_id=hunk_id,
                )
                continue
            split_hunk_assignments[hunk_id] = split_hunk_assignments.get(hunk_id, 0) + 1
            split_hunks_by_path.setdefault(path, []).append(hunk_id)

        for path in split_paths:
            if path in omitted_paths:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                    message=f"Path `{path}` is both omitted and committed as split.",
                    path=path,
                    commit_index=commit_index,
                )
            if path not in worktree_files:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["unknown_path"],
                    message=f"Commit {commit_index} references unknown split path `{path}`.",
                    path=path,
                    commit_index=commit_index,
                )
                continue
            entry = worktree_files[path]
            split_path_to_commits.setdefault(path, set()).add(commit_index)
            if not entry.get("split_eligible"):
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["partial_split_unsupported"],
                    message=f"Commit {commit_index} uses non-split-eligible path `{path}` in `split_paths`; partial splits are unsupported for this file.",
                    path=path,
                    commit_index=commit_index,
                    stop_category="partial_split_unsupported",
                )
            if entry.get("binary"):
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["partial_split_unsupported"],
                    message=f"Commit {commit_index} uses binary path `{path}` in `split_paths`; partial splits are unsupported for binary files.",
                    path=path,
                    commit_index=commit_index,
                    stop_category="partial_split_unsupported",
                )
            if entry.get("change_kind") != "modified":
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["partial_split_unsupported"],
                    message=f"Commit {commit_index} uses `{path}` in `split_paths`, but only tracked modified text files may be partially split.",
                    path=path,
                    commit_index=commit_index,
                    stop_category="partial_split_unsupported",
                )
            if path_assignments.get(path, 0):
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                    message=f"Commit {commit_index} mixes split and whole-file handling for `{path}`.",
                    path=path,
                    commit_index=commit_index,
                )
            if path not in split_hunks_by_path:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["hunk_assignment_mismatch"],
                    message=f"Commit {commit_index} lists split path `{path}` but assigns no hunks from it.",
                    path=path,
                    commit_index=commit_index,
                )

        if not whole_file_paths and not untracked_paths and not split_paths:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                message=f"Commit {commit_index} does not cover any owned paths.",
                commit_index=commit_index,
            )
        if not str(commit.get("subject", "")).strip():
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_field"],
                message=f"Commit {commit_index} is missing `subject`.",
                field="subject",
                commit_index=commit_index,
            )
        if not str(commit.get("type", "")).strip():
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_field"],
                message=f"Commit {commit_index} is missing `type`.",
                field="type",
                commit_index=commit_index,
            )
        if not str(commit.get("scope", "")).strip():
            push_issue(
                warnings,
                warning_details,
                code=VALIDATION_WARNING_CODES["empty_scope"],
                message=f"Commit {commit_index} has an empty `scope`.",
                field="scope",
                commit_index=commit_index,
            )
        if body_lines and not all(line.lstrip().startswith("- ") for line in body_lines):
            push_issue(
                warnings,
                warning_details,
                code=VALIDATION_WARNING_CODES["non_bullet_body"],
                message=f"Commit {commit_index} body contains non-bullet lines.",
                field="body",
                commit_index=commit_index,
            )

    changed_paths = set(worktree_files)
    covered_paths = set(path_assignments) | set(split_path_to_commits) | omitted_paths
    for path in sorted(changed_paths - covered_paths):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
            message=f"Changed path `{path}` is neither committed nor omitted.",
            path=path,
        )
    for path in sorted(covered_paths - changed_paths):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["unknown_path"],
            message=f"Plan references path `{path}` that is not in the collected worktree.",
            path=path,
        )

    for path, count in sorted(path_assignments.items()):
        if count != 1:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["path_assignment_mismatch"],
                message=f"Path `{path}` is assigned {count} times; expected exactly once.",
                path=path,
            )

    for hunk_id, count in sorted(split_hunk_assignments.items()):
        if count != 1:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["hunk_assignment_mismatch"],
                message=f"Hunk `{hunk_id}` is assigned {count} times; expected exactly once.",
                hunk_id=hunk_id,
            )

    for path, _commit_ids in sorted(split_path_to_commits.items()):
        entry = worktree_files[path]
        hunks = list(entry.get("hunks", []))
        all_hunk_ids = {str(hunk["hunk_id"]) for hunk in hunks}
        assigned_hunk_ids = {
            hunk_id
            for hunk_id, owning_path in hunk_to_path.items()
            if owning_path == path and split_hunk_assignments.get(hunk_id)
        }
        if assigned_hunk_ids != all_hunk_ids:
            missing = sorted(all_hunk_ids - assigned_hunk_ids)
            extra = sorted(assigned_hunk_ids - all_hunk_ids)
            if missing:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["hunk_assignment_mismatch"],
                    message=f"Split path `{path}` has unassigned hunks: {', '.join(missing)}",
                    path=path,
                )
            if extra:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["hunk_assignment_mismatch"],
                    message=f"Split path `{path}` has unexpected assigned hunks: {', '.join(extra)}",
                    path=path,
                )

        digest_pairs = [(str(hunk["removed_digest"]), str(hunk["added_digest"])) for hunk in hunks]
        if len(digest_pairs) != len(set(digest_pairs)):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["ambiguous_split_rematch"],
                message=f"Split path `{path}` has duplicate digest pairs; current-diff rematch would be ambiguous.",
                path=path,
                stop_category="ambiguous_split_rematch",
            )

        ordered_hunks = sorted(hunks, key=lambda item: (int(item["old_start"]), int(item["new_start"])))
        hunk_commit_lookup = {}
        for commit in normalized_plan.get("commits", []):
            commit_index = int(commit.get("commit_index", 0))
            for hunk_id in string_list(commit.get("selected_hunk_ids")):
                if hunk_to_path.get(hunk_id) == path:
                    hunk_commit_lookup[hunk_id] = commit_index
        for left, right in zip(ordered_hunks, ordered_hunks[1:]):
            left_commit = hunk_commit_lookup.get(str(left["hunk_id"]))
            right_commit = hunk_commit_lookup.get(str(right["hunk_id"]))
            if left_commit is None or right_commit is None or left_commit == right_commit:
                continue
            left_old_end = int(left["old_start"]) + max(int(left["old_count"]), 1) - 1
            right_old_gap = int(right["old_start"]) - left_old_end - 1
            left_new_end = int(left["new_start"]) + max(int(left["new_count"]), 1) - 1
            right_new_gap = int(right["new_start"]) - left_new_end - 1
            if right_old_gap <= 0 or right_new_gap <= 0:
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["adjacent_split_hunks"],
                    message=(
                        f"Split path `{path}` assigns adjacent or overlapping hunks to different commits "
                        f"({left['hunk_id']} -> commit {left_commit}, {right['hunk_id']} -> commit {right_commit})."
                    ),
                    path=path,
                    stop_category="partial_split_unsupported",
                )

    for path in sorted(omitted_paths):
        if path not in worktree_files:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["unknown_path"],
                message=f"Omitted path `{path}` is not present in the collected worktree.",
                path=path,
            )

    deduped_validation_commands = dedupe_preserve(plan_validation_commands or union_targeted_checks)
    feasibility_commands = dedupe_preserve(plan_validation_commands + union_targeted_checks)
    for issue in command_feasibility_issues(repo_root, feasibility_commands):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["targeted_check_unavailable"],
            message=f"Targeted check `{issue['command']}` is not feasible locally: {issue['detail']}.",
            field="validation_commands",
            command=issue["command"],
            stop_category="targeted_check_unavailable",
        )

    confidence = str(normalized_plan.get("overall_confidence", "")).strip().lower()
    current_stop_categories = dedupe_preserve(
        [
            str(detail.get("stop_category"))
            for detail in error_details
            if str(detail.get("stop_category", "")).strip()
        ]
    )
    stop_reasons = list(errors)
    if normalized_plan.get("stop_reasons"):
        current_stop_categories = dedupe_preserve([*current_stop_categories, "unresolved_stop_reason"])
        for reason in string_list(normalized_plan.get("stop_reasons")):
            if reason not in stop_reasons:
                stop_reasons.append(reason)
    if confidence != "high":
        current_stop_categories = dedupe_preserve([*current_stop_categories, "low_confidence"])
        low_confidence_reason = (
            "overall_confidence must be `high` before apply may proceed."
        )
        if low_confidence_reason not in stop_reasons:
            stop_reasons.append(low_confidence_reason)

    can_apply = (
        not errors
        and confidence == "high"
        and not normalized_plan.get("stop_reasons")
    )
    apply_gate_status = build_apply_gate_status(current_stop_categories, can_apply)
    return {
        "valid": not errors,
        "can_apply": can_apply,
        "errors": errors,
        "warnings": warnings,
        "error_details": error_details,
        "warning_details": warning_details,
        "stop_reasons": stop_reasons,
        "stop_categories": current_stop_categories,
        "deduped_validation_commands": deduped_validation_commands,
        "path_count": len(worktree_files),
        "commit_count": len([commit for commit in normalized_plan.get("commits", []) if isinstance(commit, dict)]),
        "current_worktree_fingerprint": current_worktree.get("worktree_fingerprint"),
        "expected_worktree_fingerprint": worktree.get("worktree_fingerprint"),
        "normalized_plan": normalized_plan,
        "normalized_plan_fingerprint": normalized_plan_fingerprint,
        "validated_head_commit": current_worktree.get("head_commit"),
        "apply_gate_status": apply_gate_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a commit plan against a worktree snapshot.")
    parser.add_argument("--worktree", type=Path, required=True, help="Path to worktree JSON from collect_worktree_context.py")
    parser.add_argument("--plan", type=Path, required=True, help="Path to drafted commit-plan JSON")
    parser.add_argument("--output", type=Path, help="Optional path to write validation JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        worktree = load_json(args.worktree)
        plan = load_json(args.plan)
        payload = validate_plan_against_worktree(worktree, plan)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"validate_commit_plan.py: {exc}", file=sys.stderr)
        return 1

    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote validation result to {args.output}")
    else:
        sys.stdout.write(serialized)
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
