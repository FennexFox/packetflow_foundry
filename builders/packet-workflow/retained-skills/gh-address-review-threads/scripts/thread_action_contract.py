from __future__ import annotations

import hashlib
import json
from typing import Any


PHASES = ("ack", "complete")
DECISIONS = {"accept", "reject", "defer", "defer-outdated"}
ACTION_MODES = {"add", "update", "skip"}
MARKER_CONFLICT_SEVERITIES = ("warning", "adoption-blocking", "hard-stop")

PHASE_FIELD_POLICY = {
    "ack": {
        "mode_field": "ack_mode",
        "body_field": "ack_body",
        "comment_id_field": "ack_comment_id",
        "required_common": ["thread_id", "decision"],
        "allowed_modes": ["add", "update", "skip"],
        "body_required_when": ["add", "update"],
        "comment_id_rules": {
            "add": "ignore",
            "update": "explicit_or_reply_candidate_fallback",
            "skip": "ignore",
        },
        "extra_rules": [],
    },
    "complete": {
        "mode_field": "complete_mode",
        "body_field": "complete_body",
        "comment_id_field": "complete_comment_id",
        "required_common": ["thread_id", "decision"],
        "allowed_modes": ["add", "update", "skip"],
        "body_required_when": ["add", "update"],
        "comment_id_rules": {
            "add": "ignore",
            "update": "explicit_or_reply_candidate_fallback",
            "skip": "ignore",
        },
        "extra_rules": ["accept_only", "resolve_after_complete_requires_non_skip_accept"],
    },
}

VALIDATION_ERROR_CODES = {
    "invalid_plan_shape",
    "missing_thread_id",
    "unknown_thread_id",
    "invalid_decision",
    "invalid_mode",
    "missing_required_body",
    "missing_update_target",
    "invalid_complete_for_non_accept",
    "invalid_resolve_after_complete",
    "adoption_blocked_update",
    "hard_stop_marker_conflict",
    "stale_context_fingerprint",
}

VALIDATION_WARNING_CODES = {
    "unknown_action_field_ignored",
    "ignored_comment_id_for_add",
    "ignored_comment_id_for_skip",
    "ignored_body_for_skip",
    "ignored_resolve_after_complete_outside_complete",
}


def policy_for_phase(phase: str) -> dict[str, Any]:
    if phase not in PHASE_FIELD_POLICY:
        raise RuntimeError(f"Unsupported phase: {phase}")
    return PHASE_FIELD_POLICY[phase]


def _stringify(value: Any) -> str:
    return str(value or "").strip()


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _timestamp(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    return _stringify(value.get("updated_at") or value.get("created_at"))


def comment_sort_key(comment: dict[str, Any]) -> tuple[str, str]:
    return (_timestamp(comment), _stringify(comment.get("id")))


def thread_sort_key(thread: dict[str, Any]) -> tuple[str, int, str]:
    line = thread.get("line")
    if line in {None, ""}:
        line = thread.get("original_line")
    return (
        _stringify(thread.get("path")),
        _int_or_zero(line),
        _stringify(thread.get("thread_id")),
    )


def normalize_marker_conflicts(thread: dict[str, Any]) -> list[dict[str, Any]]:
    raw = thread.get("marker_conflicts")
    normalized: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            phase = _stringify(item.get("phase"))
            severity = _stringify(item.get("severity"))
            if phase not in PHASES or severity not in MARKER_CONFLICT_SEVERITIES:
                continue
            comment_ids = sorted({_stringify(value) for value in item.get("comment_ids", []) if _stringify(value)})
            normalized.append(
                {
                    "phase": phase,
                    "severity": severity,
                    "reason": _stringify(item.get("reason")),
                    "comment_ids": comment_ids,
                    "blocks_adoption": bool(item.get("blocks_adoption")),
                    "blocks_update": bool(item.get("blocks_update")),
                    "blocks_apply": bool(item.get("blocks_apply")),
                }
            )
    elif isinstance(raw, dict):
        for phase in PHASES:
            comment_ids = sorted({_stringify(value) for value in raw.get(phase, []) if _stringify(value)})
            if comment_ids:
                normalized.append(
                    {
                        "phase": phase,
                        "severity": "warning",
                        "reason": "legacy_duplicate_exact_managed_replies",
                        "comment_ids": comment_ids,
                        "blocks_adoption": False,
                        "blocks_update": False,
                        "blocks_apply": False,
                    }
                )
    normalized.sort(
        key=lambda item: (
            _stringify(item.get("phase")),
            _stringify(item.get("severity")),
            _stringify(item.get("reason")),
            list(item.get("comment_ids", [])),
        )
    )
    return normalized


def conflicts_for_phase(thread: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    return [item for item in normalize_marker_conflicts(thread) if item.get("phase") == phase]


def reply_candidate(thread: dict[str, Any], phase: str) -> dict[str, Any]:
    payload = thread.get("reply_candidates")
    if not isinstance(payload, dict):
        return {
            "mode": "add",
            "comment_id": None,
            "reason": "missing_reply_candidates",
            "managed": False,
            "adopted_unmarked_reply": False,
        }
    candidate = payload.get(phase)
    if not isinstance(candidate, dict):
        return {
            "mode": "add",
            "comment_id": None,
            "reason": "missing_reply_candidate_phase",
            "managed": False,
            "adopted_unmarked_reply": False,
        }
    return {
        "mode": _stringify(candidate.get("mode")) or "add",
        "comment_id": _stringify(candidate.get("comment_id")) or None,
        "reason": _stringify(candidate.get("reason")),
        "managed": bool(candidate.get("managed")),
        "adopted_unmarked_reply": bool(candidate.get("adopted_unmarked_reply")),
    }


def exact_managed_target_id(thread: dict[str, Any], phase: str) -> str | None:
    matches = [
        comment
        for comment in thread.get("comments", [])
        if isinstance(comment, dict)
        and bool(comment.get("is_self"))
        and _stringify(comment.get("managed_phase")) == phase
        and bool(comment.get("has_exact_managed_marker"))
    ]
    if not matches:
        return None
    matches.sort(key=comment_sort_key)
    target = _stringify(matches[-1].get("id"))
    return target or None


def marker_conflict_summary(threads: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts = [item for thread in threads for item in normalize_marker_conflicts(thread)]
    by_severity = {severity: 0 for severity in MARKER_CONFLICT_SEVERITIES}
    by_phase = {phase: 0 for phase in PHASES}
    for item in conflicts:
        severity = _stringify(item.get("severity"))
        phase = _stringify(item.get("phase"))
        if severity in by_severity:
            by_severity[severity] += 1
        if phase in by_phase:
            by_phase[phase] += 1
    return {
        "count": len(conflicts),
        "by_severity": by_severity,
        "by_phase": by_phase,
    }


def build_context_fingerprint(context: dict[str, Any]) -> str:
    pr = context.get("pr", {}) if isinstance(context.get("pr"), dict) else {}
    unresolved_threads = [
        thread
        for thread in context.get("threads", [])
        if isinstance(thread, dict) and not bool(thread.get("is_resolved"))
    ]
    unresolved_threads.sort(key=thread_sort_key)

    fingerprint_payload = {
        "pr_number": pr.get("number"),
        "head_ref": pr.get("headRefName"),
        "base_ref": pr.get("baseRefName"),
        "changed_files": sorted({_stringify(path) for path in context.get("changed_files", []) if _stringify(path)}),
        "diff_stat": _stringify(context.get("diff_stat")),
        "threads": [
            {
                "thread_id": _stringify(thread.get("thread_id")),
                "path": _stringify(thread.get("path")),
                "line": thread.get("line"),
                "original_line": thread.get("original_line"),
                "is_outdated": bool(thread.get("is_outdated")),
                "latest_comment_at": max((_timestamp(comment) for comment in thread.get("comments", []) if isinstance(comment, dict)), default=""),
                "latest_reviewer_comment_at": _stringify(thread.get("latest_reviewer_comment_at")),
                "marker_conflicts": normalize_marker_conflicts(thread),
            }
            for thread in unresolved_threads
        ],
        "marker_conflict_summary": marker_conflict_summary(unresolved_threads),
    }
    encoded = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def context_fingerprint(context: dict[str, Any]) -> str:
    existing = _stringify(context.get("context_fingerprint"))
    return existing or build_context_fingerprint(context)


def validation_message(code: str, *, thread_id: str | None = None, phase: str | None = None, field: str | None = None) -> str:
    prefix = f"thread {thread_id}: " if thread_id else ""
    if code == "missing_update_target":
        return f"{prefix}{phase}_mode=update requires explicit {phase}_comment_id or reply_candidates.{phase}.comment_id fallback"
    if code == "invalid_complete_for_non_accept":
        return f"{prefix}complete actions are only valid for accepted threads"
    if code == "adoption_blocked_update":
        return f"{prefix}{phase}_mode=update cannot rely on reply_candidates.{phase} because marker_conflicts severity=adoption-blocking"
    if code == "hard_stop_marker_conflict":
        return f"{prefix}{phase} actions are blocked because marker_conflicts severity=hard-stop"
    if code == "stale_context_fingerprint":
        return "plan context_fingerprint does not match the current context"
    if code == "unknown_action_field_ignored":
        return f"{prefix}ignored unknown field `{field}`"
    if code == "ignored_comment_id_for_add":
        return f"{prefix}{phase}_comment_id is ignored when {phase}_mode=add"
    if code == "ignored_comment_id_for_skip":
        return f"{prefix}{phase}_comment_id is ignored when {phase}_mode=skip"
    if code == "ignored_body_for_skip":
        return f"{prefix}{phase}_body is ignored when {phase}_mode=skip"
    if code == "ignored_resolve_after_complete_outside_complete":
        return f"{prefix}resolve_after_complete is ignored outside a valid complete action"
    if code == "missing_required_body":
        return f"{prefix}{phase}_body is required when {phase}_mode is add or update"
    if code == "invalid_resolve_after_complete":
        return f"{prefix}resolve_after_complete is only valid when phase=complete, decision=accept, and complete_mode is not skip"
    if code == "invalid_mode":
        return f"{prefix}invalid {phase}_mode"
    if code == "invalid_decision":
        return f"{prefix}invalid decision"
    if code == "missing_thread_id":
        return "each plan entry must include thread_id"
    if code == "unknown_thread_id":
        return f"{prefix}thread_id is not present in the context"
    if code == "invalid_plan_shape":
        return "plan JSON must be a list or contain `thread_actions`, `actions`, or `normalized_thread_actions`"
    return code


def build_issue(
    level: str,
    code: str,
    *,
    thread_id: str | None = None,
    phase: str | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    issue = {
        "level": level,
        "code": code,
        "message": validation_message(code, thread_id=thread_id, phase=phase, field=field),
    }
    if thread_id:
        issue["thread_id"] = thread_id
    if phase:
        issue["phase"] = phase
    if field:
        issue["field"] = field
    return issue


def extract_plan_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("thread_actions", "actions", "normalized_thread_actions"):
            value = payload.get(key)
            if isinstance(value, list):
                return list(value)
    raise RuntimeError(validation_message("invalid_plan_shape"))


def _decision_counters() -> dict[str, int]:
    return {
        "threads_accepted": 0,
        "threads_rejected": 0,
        "threads_deferred": 0,
        "threads_defer_outdated": 0,
    }


def _base_counters() -> dict[str, Any]:
    return {
        "entry_count": 0,
        "normalized_entry_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "unknown_fields_ignored": 0,
        "adopted_unmarked_reply_count": 0,
        "skipped_outdated_count": 0,
        "invalid_complete_count": 0,
        "resolve_after_complete_count": 0,
        **_decision_counters(),
    }


def normalize_reconciliation_summary(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("reconciliation_summary")
    if not isinstance(raw, dict):
        return None
    return {
        "outdated_transition_candidates": _int_or_zero(raw.get("outdated_transition_candidates")),
        "outdated_auto_resolved": _int_or_zero(raw.get("outdated_auto_resolved")),
        "outdated_recheck_ambiguous": _int_or_zero(raw.get("outdated_recheck_ambiguous")),
        "outdated_still_applicable": _int_or_zero(raw.get("outdated_still_applicable")),
    }


def validate_thread_action_payload(context: dict[str, Any], payload: Any, phase: str) -> dict[str, Any]:
    policy = policy_for_phase(phase)
    mode_field = policy["mode_field"]
    body_field = policy["body_field"]
    comment_id_field = policy["comment_id_field"]

    result = {
        "phase": phase,
        "valid": True,
        "context_fingerprint": context_fingerprint(context),
        "fingerprint_match": True,
        "errors": [],
        "warnings": [],
        "counters": _base_counters(),
        "normalized_thread_actions": [],
        "stop_reasons": [],
    }
    reconciliation_summary = normalize_reconciliation_summary(payload)
    if reconciliation_summary is not None:
        result["reconciliation_summary"] = reconciliation_summary

    payload_fingerprint = _stringify(payload.get("context_fingerprint")) if isinstance(payload, dict) else ""
    if payload_fingerprint and payload_fingerprint != result["context_fingerprint"]:
        result["fingerprint_match"] = False
        result["errors"].append(build_issue("error", "stale_context_fingerprint"))
        result["stop_reasons"].append(validation_message("stale_context_fingerprint"))

    try:
        entries = extract_plan_entries(payload)
    except RuntimeError:
        result["errors"].append(build_issue("error", "invalid_plan_shape"))
        result["valid"] = False
        result["counters"]["error_count"] = 1
        return result

    result["counters"]["entry_count"] = len(entries)
    threads_by_id = {
        _stringify(thread.get("thread_id")): thread
        for thread in context.get("threads", [])
        if isinstance(thread, dict) and _stringify(thread.get("thread_id"))
    }
    allowed_keys = set(policy["required_common"]) | {mode_field, body_field, comment_id_field, "resolve_after_complete"}

    normalized_entries: list[dict[str, Any]] = []

    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            result["errors"].append(build_issue("error", "invalid_plan_shape"))
            continue

        thread_id = _stringify(raw_entry.get("thread_id"))
        if not thread_id:
            result["errors"].append(build_issue("error", "missing_thread_id", phase=phase))
            continue
        thread = threads_by_id.get(thread_id)
        if thread is None:
            result["errors"].append(build_issue("error", "unknown_thread_id", thread_id=thread_id, phase=phase))
            continue

        for key in sorted(set(raw_entry) - allowed_keys):
            result["warnings"].append(
                build_issue(
                    "warning",
                    "unknown_action_field_ignored",
                    thread_id=thread_id,
                    phase=phase,
                    field=key,
                )
            )
            result["counters"]["unknown_fields_ignored"] += 1

        decision = _stringify(raw_entry.get("decision"))
        if decision not in DECISIONS:
            result["errors"].append(build_issue("error", "invalid_decision", thread_id=thread_id, phase=phase))
            continue

        raw_mode = raw_entry.get(mode_field)
        mode = _stringify(raw_mode) or "skip"
        if mode not in ACTION_MODES:
            result["errors"].append(build_issue("error", "invalid_mode", thread_id=thread_id, phase=phase))
            continue

        phase_conflicts = conflicts_for_phase(thread, phase)
        if any(item.get("severity") == "hard-stop" for item in phase_conflicts) and mode != "skip":
            result["errors"].append(build_issue("error", "hard_stop_marker_conflict", thread_id=thread_id, phase=phase))
            continue

        if phase == "complete" and decision != "accept" and mode != "skip":
            result["errors"].append(build_issue("error", "invalid_complete_for_non_accept", thread_id=thread_id, phase=phase))
            result["counters"]["invalid_complete_count"] += 1
            continue

        normalized_entry: dict[str, Any] = {
            "thread_id": thread_id,
            "decision": decision,
            mode_field: mode,
        }

        body = _stringify(raw_entry.get(body_field))
        explicit_comment_id = _stringify(raw_entry.get(comment_id_field))
        fallback_comment_id = reply_candidate(thread, phase).get("comment_id")
        adopted_candidate = bool(reply_candidate(thread, phase).get("adopted_unmarked_reply"))
        exact_managed_id = exact_managed_target_id(thread, phase)
        adoption_blocked = any(item.get("severity") == "adoption-blocking" for item in phase_conflicts)

        if mode == "skip":
            if body:
                result["warnings"].append(build_issue("warning", "ignored_body_for_skip", thread_id=thread_id, phase=phase))
            if explicit_comment_id:
                result["warnings"].append(build_issue("warning", "ignored_comment_id_for_skip", thread_id=thread_id, phase=phase))
            if bool(raw_entry.get("resolve_after_complete")):
                if phase == "complete":
                    result["errors"].append(build_issue("error", "invalid_resolve_after_complete", thread_id=thread_id, phase=phase))
                    result["counters"]["invalid_complete_count"] += 1
                    continue
                result["warnings"].append(
                    build_issue("warning", "ignored_resolve_after_complete_outside_complete", thread_id=thread_id, phase=phase)
                )
        else:
            if not body:
                result["errors"].append(build_issue("error", "missing_required_body", thread_id=thread_id, phase=phase))
                continue
            normalized_entry[body_field] = body

            if mode == "add":
                if explicit_comment_id:
                    result["warnings"].append(build_issue("warning", "ignored_comment_id_for_add", thread_id=thread_id, phase=phase))
            elif mode == "update":
                resolved_comment_id = explicit_comment_id or _stringify(fallback_comment_id)
                if adoption_blocked:
                    exact_managed_allowed = bool(explicit_comment_id and exact_managed_id and explicit_comment_id == exact_managed_id)
                    fallback_relies_on_adoption = not explicit_comment_id and adopted_candidate
                    explicit_not_exact = bool(explicit_comment_id and (not exact_managed_id or explicit_comment_id != exact_managed_id))
                    if fallback_relies_on_adoption or explicit_not_exact:
                        result["errors"].append(build_issue("error", "adoption_blocked_update", thread_id=thread_id, phase=phase))
                        continue
                if not resolved_comment_id:
                    result["errors"].append(build_issue("error", "missing_update_target", thread_id=thread_id, phase=phase))
                    continue
                normalized_entry[comment_id_field] = resolved_comment_id
                if not explicit_comment_id and adopted_candidate:
                    result["counters"]["adopted_unmarked_reply_count"] += 1

        if phase == "complete":
            resolve_after_complete = bool(raw_entry.get("resolve_after_complete"))
            if resolve_after_complete:
                if decision == "accept" and mode != "skip":
                    normalized_entry["resolve_after_complete"] = True
                    result["counters"]["resolve_after_complete_count"] += 1
                else:
                    result["errors"].append(build_issue("error", "invalid_resolve_after_complete", thread_id=thread_id, phase=phase))
                    result["counters"]["invalid_complete_count"] += 1
                    continue
        elif bool(raw_entry.get("resolve_after_complete")):
            result["warnings"].append(
                build_issue("warning", "ignored_resolve_after_complete_outside_complete", thread_id=thread_id, phase=phase)
            )

        if decision == "accept":
            result["counters"]["threads_accepted"] += 1
        elif decision == "reject":
            result["counters"]["threads_rejected"] += 1
        elif decision == "defer":
            result["counters"]["threads_deferred"] += 1
        elif decision == "defer-outdated":
            result["counters"]["threads_defer_outdated"] += 1
            result["counters"]["skipped_outdated_count"] += 1

        normalized_entries.append(normalized_entry)

    normalized_entries.sort(
        key=lambda item: thread_sort_key(threads_by_id.get(_stringify(item.get("thread_id")), {"thread_id": item.get("thread_id")}))
    )
    result["normalized_thread_actions"] = normalized_entries
    result["counters"]["normalized_entry_count"] = len(normalized_entries)
    result["counters"]["error_count"] = len(result["errors"])
    result["counters"]["warning_count"] = len(result["warnings"])
    result["valid"] = not result["errors"] and bool(result["fingerprint_match"])
    return result


def load_normalized_plan_envelope(context: dict[str, Any], payload: Any, phase: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("normalized_thread_actions"), list):
        raise RuntimeError("plan must be normalized output from validate_thread_action_plan.py")
    if _stringify(payload.get("phase")) not in {"", phase}:
        raise RuntimeError(f"plan phase does not match requested phase `{phase}`")
    validated = validate_thread_action_payload(context, payload, phase)
    if not bool(payload.get("valid")):
        raise RuntimeError("normalized plan is marked invalid")
    if not validated["valid"]:
        first_error = validated["errors"][0]["message"] if validated["errors"] else "normalized plan validation failed"
        raise RuntimeError(first_error)
    return validated
