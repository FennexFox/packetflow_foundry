#!/usr/bin/env python3
"""Validate and normalize a public-docs-sync plan before marker apply."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from public_docs_sync_contract import (
    APPLY_CONTEXT_SNAPSHOT_FIELDS,
    DETERMINISTIC_ACTION_ALIASES,
    MANUAL_ONLY_ACTION_PREFIXES,
    MANUAL_ONLY_ACTION_TYPES,
    PLAN_PHASE_FIELD_TABLES,
    STOP_CATEGORY_SCOPES,
    VALIDATION_ERROR_CODES,
    VALIDATION_WARNING_CODES,
    dedupe_preserve,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--plan", required=True, help="Planned action JSON.")
    parser.add_argument("--output", help="Optional path to write the validation JSON.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def json_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def push_issue(
    messages: list[str],
    details: list[dict[str, Any]],
    *,
    code: str,
    message: str,
    field: str | None = None,
    action_index: int | None = None,
) -> None:
    messages.append(message)
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    if action_index is not None:
        detail["action_index"] = action_index
    details.append(detail)


def push_stop(stop_messages: dict[str, list[str]], category: str, message: str) -> None:
    stop_messages.setdefault(category, [])
    if message not in stop_messages[category]:
        stop_messages[category].append(message)


def required_keys(
    payload: dict[str, Any],
    keys: list[str],
    errors: list[str],
    error_details: list[dict[str, Any]],
    prefix: str,
    *,
    action_index: int | None = None,
) -> None:
    for key in keys:
        if key not in payload:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_field"],
                message=f"{prefix} missing required field `{key}`.",
                field=key,
                action_index=action_index,
            )


def unknown_fields(
    payload: dict[str, Any],
    *,
    scope: str,
    warnings: list[str],
    warning_details: list[dict[str, Any]],
    action_index: int | None = None,
) -> None:
    rules = PLAN_PHASE_FIELD_TABLES["draft_plan"][scope]
    allowed = set(rules["required"]) | set(rules["allowed"]) | set(rules["ignored"])
    code = (
        VALIDATION_WARNING_CODES["unknown_top_level_field"]
        if scope == "top_level"
        else VALIDATION_WARNING_CODES["unknown_action_field"]
    )
    for field in sorted(set(payload) - allowed):
        push_issue(
            warnings,
            warning_details,
            code=code,
            message=f"Removed unknown {scope.replace('_', ' ')} field `{field}` during normalization.",
            field=field,
            action_index=action_index,
        )


def normalize_details(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_manual_only_action_type(raw_type: str) -> bool:
    lowered = raw_type.strip().lower()
    return lowered in MANUAL_ONLY_ACTION_TYPES or lowered.startswith(MANUAL_ONLY_ACTION_PREFIXES)


def classify_action_type(raw_type: str) -> tuple[str, str | None, bool]:
    lowered = raw_type.strip().lower()
    canonical_type = DETERMINISTIC_ACTION_ALIASES.get(lowered)
    if canonical_type:
        return "deterministic-edit", canonical_type, False
    if is_manual_only_action_type(lowered):
        return "manual-only-review", None, False
    return "manual-only-review", None, True


def normalize_action(
    action: Any,
    index: int,
    warnings: list[str],
    warning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(action, str):
        push_issue(
            warnings,
            warning_details,
            code=VALIDATION_WARNING_CODES["action_string_normalized"],
            message=f"Normalized string action at index {index} into a manual review action.",
            field="actions",
            action_index=index,
        )
        action = {"type": "manual_review", "summary": action.strip()}
    if not isinstance(action, dict):
        action = {"type": "manual_review", "summary": str(action)}
    unknown_fields(
        action,
        scope="action",
        warnings=warnings,
        warning_details=warning_details,
        action_index=index,
    )
    raw_type = str(action.get("type", "")).strip()
    action_mode, canonical_type, scope_exceeded = classify_action_type(raw_type)
    return {
        "index": index,
        "type": raw_type,
        "canonical_type": canonical_type,
        "summary": str(action.get("summary", "")).strip(),
        "path": str(action.get("path", "")).strip() or None,
        "details": normalize_details(action.get("details")),
        "action_mode": action_mode,
        "scope_exceeded": scope_exceeded,
    }


def normalize_plan(
    plan: dict[str, Any],
    warnings: list[str],
    warning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    unknown_fields(plan, scope="top_level", warnings=warnings, warning_details=warning_details)
    raw_actions = plan.get("actions")
    normalized_actions = []
    if isinstance(raw_actions, list):
        for index, action in enumerate(raw_actions, start=1):
            normalized_actions.append(normalize_action(action, index, warnings, warning_details))
    return {
        "context_id": str(plan.get("context_id", "")).strip(),
        "context_fingerprint": str(plan.get("context_fingerprint", "")).strip(),
        "overall_confidence": str(plan.get("overall_confidence", "")).strip().lower(),
        "doc_update_status": str(plan.get("doc_update_status", "")).strip(),
        "allow_marker_update": bool(plan.get("allow_marker_update")),
        "actions": normalized_actions,
        "stop_reasons": string_list(plan.get("stop_reasons")),
        "marker_reason": str(plan.get("marker_reason", "")).strip() or None,
        "selected_packets": string_list(plan.get("selected_packets")),
        "remaining_manual_reviews": string_list(plan.get("remaining_manual_reviews")),
    }


def public_doc_paths(context: dict[str, Any]) -> set[str]:
    return {
        str(path)
        for path in context.get("public_doc_paths", [])
        if str(path).strip()
    }


def validate_settings_table_action(context: dict[str, Any], action: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    readme_path = str(context.get("readme", {}).get("path") or "README.md")
    action["path"] = action.get("path") or readme_path
    if action["path"] != readme_path:
        issues.append("settings-table default sync is only supported for the collected README settings table.")
    setting = str(action["details"].get("setting") or "").strip()
    if not setting:
        issues.append("settings-table default sync requires `details.setting`.")
        return issues

    defaults = (context.get("settings") or {}).get("defaults") or {}
    setting_info = defaults.get(setting)
    if not isinstance(setting_info, dict):
        issues.append(f"settings-table default sync cannot find runtime metadata for `{setting}`.")
        return issues

    action["details"]["setting"] = setting
    action["details"]["expected_default"] = str(setting_info.get("default"))
    action["details"]["setting_label"] = setting_info.get("label")
    action["details"]["setting_description"] = setting_info.get("description")
    documented = ((context.get("readme") or {}).get("settings_table") or {}).get(setting)
    if isinstance(documented, dict):
        action["details"]["documented_default"] = str(documented.get("default"))
        action["details"]["documented_purpose"] = str(documented.get("purpose") or "").strip() or None
    return issues


def validate_relative_link_action(context: dict[str, Any], action: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    path = str(action.get("path") or "").strip()
    if not path:
        issues.append("relative-link fix requires `path`.")
        return issues
    inventory = (context.get("public_doc_inventory") or {}).get(path) or {}
    target = str(action["details"].get("target") or "").strip()
    replacement = str(action["details"].get("replacement_target") or "").strip()
    if not target or not replacement:
        issues.append("relative-link fix requires `details.target` and `details.replacement_target`.")
    elif replacement == target:
        issues.append("relative-link fix replacement must differ from the current target.")
    if "\n" in target or "\n" in replacement:
        issues.append("relative-link fix targets must stay single-line.")
    missing_targets = {
        str(item.get("target") or "").strip()
        for item in inventory.get("missing_links", [])
        if str(item.get("target") or "").strip()
    }
    if target and missing_targets and target not in missing_targets:
        issues.append("relative-link fix target is not one of the collected broken links for this file.")
    action["details"]["target"] = target
    action["details"]["replacement_target"] = replacement
    action["details"]["expected_count"] = int(action["details"].get("expected_count") or 1)
    return issues


def validate_public_doc_reference_action(context: dict[str, Any], action: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    path = str(action.get("path") or "").strip()
    if not path:
        issues.append("public doc reference sync requires `path`.")
        return issues
    if path not in public_doc_paths(context):
        issues.append("public doc reference sync must target a collected public doc path.")
    match_text = str(action["details"].get("match_text") or "").strip()
    replacement = str(action["details"].get("replacement_text") or "").strip()
    if not match_text or not replacement:
        issues.append("public doc reference sync requires `details.match_text` and `details.replacement_text`.")
    elif replacement == match_text:
        issues.append("public doc reference sync replacement must differ from the current text.")
    if "\n" in match_text or "\n" in replacement:
        issues.append("public doc reference sync is limited to single-line replacements.")
    action["details"]["match_text"] = match_text
    action["details"]["replacement_text"] = replacement
    action["details"]["expected_count"] = int(action["details"].get("expected_count") or 1)
    return issues


def validate_issue_template_metadata_action(context: dict[str, Any], action: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    path = str(action.get("path") or "").strip()
    if not path:
        issues.append("issue-template metadata sync requires `path`.")
        return issues
    if not path.startswith(".github/ISSUE_TEMPLATE/"):
        issues.append("issue-template metadata sync must target a public issue-template YAML file.")
    inventory = (context.get("public_doc_inventory") or {}).get(path) or {}
    if inventory.get("kind") not in {"yaml", "text"}:
        issues.append("issue-template metadata sync requires a YAML issue template target.")
    field = str(action["details"].get("field") or "").strip()
    if field not in {"name", "description", "title", "labels"}:
        issues.append("issue-template metadata sync supports only `name`, `description`, `title`, or `labels`.")
    value = action["details"].get("value")
    if field == "labels":
        labels = string_list(value)
        if not labels:
            issues.append("issue-template metadata sync requires a non-empty `details.value` label list.")
        action["details"]["value"] = labels
    else:
        text = str(value or "").strip()
        if not text:
            issues.append("issue-template metadata sync requires a non-empty string `details.value`.")
        elif "\n" in text:
            issues.append("issue-template metadata sync is limited to single-line metadata values.")
        action["details"]["value"] = text
    action["details"]["field"] = field
    return issues


def validate_deterministic_action(context: dict[str, Any], action: dict[str, Any]) -> list[str]:
    canonical_type = action.get("canonical_type")
    if canonical_type == "settings_table_default_sync":
        return validate_settings_table_action(context, action)
    if canonical_type == "relative_link_fix":
        return validate_relative_link_action(context, action)
    if canonical_type == "public_doc_reference_sync":
        return validate_public_doc_reference_action(context, action)
    if canonical_type == "issue_template_metadata_sync":
        return validate_issue_template_metadata_action(context, action)
    return ["action type is outside the deterministic apply contract."]


def build_stop_status(stop_messages: dict[str, list[str]], *, marker_requested: bool) -> dict[str, Any]:
    applicable = sorted(STOP_CATEGORY_SCOPES)
    not_applicable: list[str] = []
    if not marker_requested:
        not_applicable.append("marker_update_without_doc_completion")
    statuses: dict[str, dict[str, Any]] = {}
    triggered: list[str] = []
    for category in applicable:
        triggered_here = bool(stop_messages.get(category))
        if triggered_here:
            triggered.append(category)
        statuses[category] = {
            "scope": STOP_CATEGORY_SCOPES[category],
            "triggered": triggered_here,
            "messages": stop_messages.get(category, []),
        }
    covered = [category for category in applicable if category not in not_applicable]
    return {
        "applicable_stop_categories": applicable,
        "covered_stop_categories": covered,
        "uncovered_stop_categories": [],
        "not_applicable_stop_categories": not_applicable,
        "triggered_stop_categories": triggered,
        "stop_category_statuses": statuses,
    }


def build_apply_context_snapshot(context: dict[str, Any], normalized_plan: dict[str, Any]) -> dict[str, Any]:
    relevant_ref = context.get("relevant_ref")
    if isinstance(relevant_ref, dict):
        relevant_ref_value: Any = relevant_ref.get("name") or relevant_ref.get("base_commit") or relevant_ref.get("kind")
        ref_selection_source = relevant_ref.get("source")
        primary_pr_number = relevant_ref.get("primary_pr_number")
        primary_pr_url = relevant_ref.get("primary_pr_url")
    else:
        relevant_ref_value = relevant_ref
        ref_selection_source = None
        primary_pr_number = None
        primary_pr_url = None

    primary_pr = (context.get("github_evidence") or {}).get("primary_pr") or {}
    snapshot = {
        "repo_root": str(context.get("repo_root", "")).strip(),
        "state_file": str(context.get("state_file", "")).strip(),
        "context_id": str(context.get("context_id", "")).strip(),
        "context_fingerprint": str(context.get("context_fingerprint", "")).strip(),
        "head_commit": str(context.get("head_commit", "")).strip(),
        "repo_hash": str(context.get("repo_hash", "")).strip() or None,
        "repo_slug": str(context.get("repo_slug", "")).strip() or None,
        "branch": str(context.get("branch", "")).strip() or None,
        "baseline_commit": (
            str(context.get("effective_base_commit", "")).strip()
            or str((context.get("baseline") or {}).get("base_commit") or "").strip()
            or None
        ),
        "relevant_ref": relevant_ref_value,
        "primary_pr_number": primary_pr.get("number") or primary_pr_number,
        "primary_pr_url": primary_pr.get("url") or primary_pr_url,
        "github_evidence_digest": str(context.get("github_evidence_digest", "")).strip() or None,
        "ref_selection_source": ref_selection_source,
        "audited_doc_paths": list(context.get("public_doc_paths", [])),
    }
    if normalized_plan.get("selected_packets"):
        snapshot["selected_packets"] = list(normalized_plan["selected_packets"])
    return {key: snapshot.get(key) for key in APPLY_CONTEXT_SNAPSHOT_FIELDS if key in snapshot}


def validate_public_docs_sync_plan(context: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    error_details: list[dict[str, Any]] = []
    warning_details: list[dict[str, Any]] = []
    stop_messages: dict[str, list[str]] = {name: [] for name in STOP_CATEGORY_SCOPES}
    required_keys(
        plan,
        PLAN_PHASE_FIELD_TABLES["draft_plan"]["top_level"]["required"],
        errors,
        error_details,
        "plan",
    )
    raw_actions = plan.get("actions", [])
    if isinstance(raw_actions, list):
        for index, action in enumerate(raw_actions, start=1):
            if isinstance(action, dict):
                required_keys(
                    action,
                    PLAN_PHASE_FIELD_TABLES["draft_plan"]["action"]["required"],
                    errors,
                    error_details,
                    f"action {index}",
                    action_index=index,
                )

    normalized_plan = normalize_plan(plan, warnings, warning_details)
    if normalized_plan["context_id"] != str(context.get("context_id", "")):
        message = "plan `context_id` does not match the collected context."
        push_issue(errors, error_details, code=VALIDATION_ERROR_CODES["context_id_mismatch"], message=message, field="context_id")
        push_stop(stop_messages, "stale_marker_context", message)
    if normalized_plan["context_fingerprint"] != str(context.get("context_fingerprint", "")):
        message = "plan `context_fingerprint` does not match the collected context fingerprint."
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["context_fingerprint_mismatch"],
            message=message,
            field="context_fingerprint",
        )
        push_stop(stop_messages, "stale_marker_context", message)

    repo_root = Path(str(context.get("repo_root", ""))).resolve()
    expected_head = str(context.get("head_commit", "")).strip()
    if repo_root.exists() and expected_head:
        current_head = run_git(repo_root, ["rev-parse", "HEAD"])
        if current_head != expected_head:
            message = "Repository HEAD changed since context collection."
            push_issue(errors, error_details, code=VALIDATION_ERROR_CODES["head_changed"], message=message, field="head_commit")
            push_stop(stop_messages, "stale_marker_context", message)

    selected_packets = normalized_plan.get("selected_packets", [])
    active_packets = [
        name
        for name, packet in (context.get("packet_candidates", {}) or {}).items()
        if isinstance(packet, dict) and packet.get("active")
    ]
    if len(selected_packets) != len(set(selected_packets)):
        message = "plan `selected_packets` contains duplicates."
        push_issue(errors, error_details, code=VALIDATION_ERROR_CODES["ambiguous_selected_packet"], message=message, field="selected_packets")
        push_stop(stop_messages, "deterministic_scope_exceeded", message)
    for packet_name in selected_packets:
        if packet_name.endswith(".json"):
            packet_name = packet_name[:-5]
        if packet_name not in active_packets:
            message = f"plan selects inactive or unknown packet `{packet_name}`."
            push_issue(errors, error_details, code=VALIDATION_ERROR_CODES["ambiguous_selected_packet"], message=message, field="selected_packets")
            push_stop(stop_messages, "deterministic_scope_exceeded", message)
    if bool(context.get("github_evidence_required")):
        evidence_urls = string_list((context.get("evidence_summary") or {}).get("urls"))
        evidence_digest = str(context.get("github_evidence_digest", "")).strip()
        if not evidence_urls and not evidence_digest:
            message = "GitHub evidence is required for this run but no evidence digest or evidence URLs were collected."
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_required_evidence"],
                message=message,
                field="github_evidence_required",
            )
            push_stop(stop_messages, "missing_required_evidence", message)

    deterministic_actions: list[dict[str, Any]] = []
    manual_review_actions: list[dict[str, Any]] = []
    for action in normalized_plan["actions"]:
        if action["action_mode"] == "deterministic-edit":
            issues = validate_deterministic_action(context, action)
            if issues:
                for message in issues:
                    push_issue(
                        errors,
                        error_details,
                        code=VALIDATION_ERROR_CODES["deterministic_scope_exceeded"],
                        message=f"action {action['index']}: {message}",
                        field="actions",
                        action_index=action["index"],
                    )
                    push_stop(stop_messages, "deterministic_scope_exceeded", f"action {action['index']}: {message}")
            else:
                deterministic_actions.append(action)
        else:
            manual_review_actions.append(action)
            if action.get("scope_exceeded"):
                message = f"action {action['index']}: `{action.get('type')}` is outside the deterministic apply contract."
                push_issue(
                    errors,
                    error_details,
                    code=VALIDATION_ERROR_CODES["deterministic_scope_exceeded"],
                    message=message,
                    field="actions",
                    action_index=action["index"],
                )
                push_stop(stop_messages, "deterministic_scope_exceeded", message)

    if normalized_plan["remaining_manual_reviews"]:
        push_stop(
            stop_messages,
            "narrative_drift_remaining",
            "remaining_manual_reviews is non-empty; marker update must wait for manual doc review to finish.",
        )
    if normalized_plan["stop_reasons"]:
        push_stop(
            stop_messages,
            "narrative_drift_remaining",
            "plan `stop_reasons` is non-empty; marker update must wait for the remaining review blockers.",
        )
    if manual_review_actions:
        push_stop(
            stop_messages,
            "narrative_drift_remaining",
            "manual-only-review actions remain in the plan; marker update must wait for local narrative review to finish.",
        )
    marker_requested = bool(normalized_plan["allow_marker_update"])
    doc_update_complete = normalized_plan["doc_update_status"] in {"completed", "noop"}
    if marker_requested and not doc_update_complete:
        push_stop(
            stop_messages,
            "marker_update_without_doc_completion",
            "plan requested a marker update before `doc_update_status` reached `completed` or `noop`.",
        )
    if marker_requested and normalized_plan["overall_confidence"] == "low":
        push_stop(
            stop_messages,
            "marker_update_without_doc_completion",
            "low-confidence plans cannot persist a success marker.",
        )

    stop_status = build_stop_status(stop_messages, marker_requested=marker_requested)
    apply_blocking_categories = {
        "stale_marker_context",
        "deterministic_scope_exceeded",
        "missing_required_evidence",
    }
    marker_blocking_categories = {
        "narrative_drift_remaining",
        "marker_update_without_doc_completion",
    }
    triggered = set(stop_status["triggered_stop_categories"])
    can_apply = not errors and not (triggered & apply_blocking_categories)
    can_update_marker = can_apply and marker_requested and not (triggered & marker_blocking_categories)
    stop_reasons = dedupe_preserve(
        [
            *errors,
            *[message for category in stop_status["triggered_stop_categories"] for message in stop_messages.get(category, [])],
        ]
    )
    apply_context_snapshot = build_apply_context_snapshot(context, normalized_plan)
    return {
        "valid": not errors,
        "can_apply": can_apply,
        "can_update_marker": can_update_marker,
        "errors": errors,
        "warnings": warnings,
        "error_details": error_details,
        "warning_details": warning_details,
        "stop_reasons": stop_reasons,
        "normalized_plan": normalized_plan,
        "normalized_plan_fingerprint": json_fingerprint(normalized_plan),
        "context_file_fingerprint": json_fingerprint(context),
        "apply_context_snapshot": apply_context_snapshot,
        "apply_context_snapshot_fingerprint": json_fingerprint(apply_context_snapshot),
        "deterministic_actions": deterministic_actions,
        "manual_review_actions": manual_review_actions,
        "action_summary": {
            "deterministic_edit_count": len(deterministic_actions),
            "manual_only_review_count": len(manual_review_actions),
        },
        "apply_gate_status": {
            "status": "pass" if can_apply else "fail",
            "apply_edits_status": "pass" if can_apply else "fail",
            "marker_update_status": (
                "pass"
                if can_update_marker
                else "not-requested"
                if not marker_requested
                else "blocked"
            ),
            **stop_status,
        },
    }


def main() -> int:
    args = parse_args()
    try:
        context = load_json(Path(args.context).resolve())
        plan = load_json(Path(args.plan).resolve())
        payload = validate_public_docs_sync_plan(context, plan)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"validate_public_docs_sync_plan.py: {exc}", file=sys.stderr)
        return 1

    if args.output:
        write_json(Path(args.output).resolve(), payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
