#!/usr/bin/env python3
"""Validate a local release-copy plan before deterministic apply."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import create_release_issue as issue_tools
import release_copy_plan_contract as contract
import release_copy_plan_tools as plan_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Path to collect_release_copy_context.py JSON")
    parser.add_argument("--lint", required=True, help="Path to lint_release_copy.py JSON")
    parser.add_argument("--plan", required=True, help="Path to local release-copy plan JSON")
    parser.add_argument("--output", help="Optional output path for validation JSON")
    return parser.parse_args()


def push_issue(
    bucket: list[str],
    details: list[dict[str, Any]],
    *,
    code: str,
    message: str,
    field: str | None = None,
    stop_category: str | None = None,
) -> None:
    bucket.append(message)
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    if stop_category is not None:
        detail["stop_category"] = stop_category
    details.append(detail)


def normalize_mapping(
    name: str,
    payload: dict[str, Any],
    *,
    warnings: list[str],
    warning_details: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = contract.PLAN_PHASE_FIELDS[name]
    normalized: dict[str, Any] = {}
    allowed = set(fields["allowed"])
    for key, value in payload.items():
        if key in allowed:
            normalized[key] = value
            continue
        push_issue(
            warnings,
            warning_details,
            code=contract.VALIDATION_WARNING_CODES["ignored_field"],
            message=f"Ignored unexpected `{name}` field `{key}`.",
            field=f"{name}.{key}",
        )
    return normalized


def normalize_string(value: Any) -> str:
    return str(value or "").strip()


def unique_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    ordered: list[str] = []
    for value in values:
        text = normalize_string(value)
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def normalize_bool(value: Any) -> bool:
    return bool(value)


def normalize_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def normalized_reread_reason(reason: str) -> str:
    return normalize_string(reason).lower().replace("-", "_").replace(" ", "_")


def expected_issue_title(context: dict[str, Any]) -> str:
    return f"[Release] {plan_tools.normalize_release_version(str(context.get('target_version') or ''))}"


def apply_gate_status(issue_action_mode: str, lint: dict[str, Any]) -> dict[str, Any]:
    applicable = ["stale_context", "validator_mismatch", "unresolved_stop_reason"]
    not_applicable = ["ambiguous_routing"]
    tracks = ((lint.get("checks") or {}).get("applicable_validation_tracks") or {})
    if any(bool(value) for value in tracks.values()):
        applicable.append("missing_required_evidence")
    else:
        not_applicable.append("missing_required_evidence")

    if issue_action_mode != "noop":
        applicable.append("missing_auth")
    else:
        not_applicable.append("missing_auth")

    return {
        "status": "pass",
        "applicable_stop_categories": applicable,
        "covered_stop_categories": applicable.copy(),
        "uncovered_stop_categories": [],
        "not_applicable_stop_categories": not_applicable,
        "local_stop_categories": contract.LOCAL_STOP_CATEGORIES.copy(),
    }


def validate_plan_contract(
    context: dict[str, Any],
    lint: dict[str, Any],
    raw_plan: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    error_details: list[dict[str, Any]] = []
    warning_details: list[dict[str, Any]] = []
    stop_reasons: list[str] = []
    validation_commands: list[str] = [
        "git rev-parse --short HEAD",
        "source fingerprint check",
        "synthesis packet sufficiency check",
    ]

    normalized_plan = normalize_mapping(
        "top_level",
        raw_plan,
        warnings=warnings,
        warning_details=warning_details,
    )

    for field in contract.PLAN_PHASE_FIELDS["top_level"]["required"]:
        if field not in normalized_plan:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["missing_field"],
                message=f"Release-copy plan is missing `{field}`.",
                field=field,
                stop_category="validator_mismatch",
            )

    if errors:
        gate = apply_gate_status("noop", lint)
        gate["status"] = "fail"
        return {
            "valid": False,
            "can_apply": False,
            "errors": errors,
            "warnings": warnings,
            "error_details": error_details,
            "warning_details": warning_details,
            "stop_reasons": ["validator_mismatch"],
            "validation_commands": validation_commands,
            "normalized_plan": {},
            "normalized_plan_fingerprint": "",
            "apply_gate_status": gate,
        }

    expected_context_fingerprint = plan_tools.expected_context_fingerprint(context)
    if normalize_string(normalized_plan.get("context_fingerprint")) != expected_context_fingerprint:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["context_fingerprint"],
            message="Plan context fingerprint does not match the collected context.",
            field="context_fingerprint",
            stop_category="validator_mismatch",
        )

    expected_freshness = plan_tools.expected_freshness_tuple(context)
    if normalized_plan.get("freshness_tuple") != expected_freshness:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["freshness_tuple"],
            message="Plan freshness tuple does not match the collected context.",
            field="freshness_tuple",
            stop_category="validator_mismatch",
        )

    draft_basis = normalized_plan.get("draft_basis")
    if not isinstance(draft_basis, dict):
        draft_basis = {}
    draft_basis = normalize_mapping("draft_basis", draft_basis, warnings=warnings, warning_details=warning_details)
    for field in contract.PLAN_PHASE_FIELDS["draft_basis"]["required"]:
        if field not in draft_basis:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["missing_field"],
                message=f"draft_basis is missing `{field}`.",
                field=f"draft_basis.{field}",
                stop_category="validator_mismatch",
            )

    common_path_sufficient = normalize_bool(draft_basis.get("common_path_sufficient"))
    raw_reread_count = normalize_int(draft_basis.get("raw_reread_count"))
    reread_reasons = unique_strings(draft_basis.get("reread_reasons"))
    focused_packets_used = unique_strings(draft_basis.get("focused_packets_used"))
    compensatory_reread_detected = normalize_bool(draft_basis.get("compensatory_reread_detected"))
    normalized_reasons = [normalized_reread_reason(reason) for reason in reread_reasons]

    invalid_reread_reasons = [
        reason
        for reason in normalized_reasons
        if reason not in contract.RAW_REREAD_ALLOWED_REASONS
    ]
    if invalid_reread_reasons:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["invalid_reread_reason"],
            message="draft_basis contains unsupported reread reason(s): " + ", ".join(invalid_reread_reasons),
            field="draft_basis.reread_reasons",
            stop_category="validator_mismatch",
        )

    if any(reason in {"packet_insufficiency", "packet_insufficient"} for reason in normalized_reasons):
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["packet_insufficient"],
            message="draft_basis recorded packet insufficiency as a reread reason; treat this as a hard stop instead of compensating with rereads.",
            field="draft_basis.reread_reasons",
            stop_category="synthesis_packet_insufficient",
        )

    if not common_path_sufficient:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["packet_insufficient"],
            message="synthesis_packet was not sufficient for local final drafting in the common path.",
            field="draft_basis.common_path_sufficient",
            stop_category="synthesis_packet_insufficient",
        )

    if compensatory_reread_detected:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["packet_insufficient"],
            message="draft_basis marked the reread path as compensatory; this run should stop instead of relying on packet insufficiency.",
            field="draft_basis.compensatory_reread_detected",
            stop_category="synthesis_packet_insufficient",
        )

    if raw_reread_count == 0 and reread_reasons:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["validator_mismatch"],
            message="draft_basis lists reread reasons even though raw_reread_count is 0.",
            field="draft_basis.reread_reasons",
            stop_category="validator_mismatch",
        )

    if raw_reread_count > 0 and not reread_reasons:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["missing_field"],
            message="draft_basis.raw_reread_count > 0 requires explicit reread_reasons.",
            field="draft_basis.reread_reasons",
            stop_category="validator_mismatch",
        )

    if raw_reread_count == 0 and len(focused_packets_used) > contract.COMMON_PATH_MAX_FOCUSED_PACKETS:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["packet_insufficient"],
            message="common-path drafting used more than one focused packet without an allowed reread reason.",
            field="draft_basis.focused_packets_used",
            stop_category="synthesis_packet_insufficient",
        )

    publish_update = normalized_plan.get("publish_update")
    if not isinstance(publish_update, dict):
        publish_update = {}
    publish_update = normalize_mapping("publish_update", publish_update, warnings=warnings, warning_details=warning_details)
    publish_mode = normalize_string(publish_update.get("mode"))
    if publish_mode not in {"noop", "replace-fields"}:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["invalid_mode"],
            message="publish_update.mode must be `noop` or `replace-fields`.",
            field="publish_update.mode",
            stop_category="validator_mismatch",
        )
    publish_fields = {
        key: normalize_string(publish_update.get(key))
        for key in ("short_description", "long_description", "change_log", "mod_version")
        if normalize_string(publish_update.get(key))
    }
    if publish_mode == "replace-fields" and not publish_fields:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["missing_field"],
            message="publish_update.mode `replace-fields` requires at least one replacement field.",
            field="publish_update",
            stop_category="validator_mismatch",
        )
    if "mod_version" in publish_fields and publish_fields["mod_version"] != normalize_string(context.get("target_version")):
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["validator_mismatch"],
            message="publish_update.mod_version must match the collected target_version.",
            field="publish_update.mod_version",
            stop_category="validator_mismatch",
        )

    readme_update = normalized_plan.get("readme_update")
    if not isinstance(readme_update, dict):
        readme_update = {}
    readme_update = normalize_mapping("readme_update", readme_update, warnings=warnings, warning_details=warning_details)
    readme_mode = normalize_string(readme_update.get("mode"))
    if readme_mode not in {"noop", "replace-sections"}:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["invalid_mode"],
            message="readme_update.mode must be `noop` or `replace-sections`.",
            field="readme_update.mode",
            stop_category="validator_mismatch",
        )
    intro_text = readme_update.get("intro_text")
    if intro_text is not None:
        intro_text = str(intro_text).strip()
    raw_sections = readme_update.get("sections")
    sections = raw_sections if isinstance(raw_sections, dict) else {}
    normalized_sections: dict[str, str] = {}
    for key, value in sections.items():
        heading = normalize_string(key)
        if heading not in plan_tools.README_ALLOWED_SECTIONS:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["unsupported_layout"],
                message=f"README section `{heading}` is outside the deterministic allowlist.",
                field=f"readme_update.sections.{heading}",
                stop_category="rewrite_block_unsupported",
            )
            continue
        normalized_sections[heading] = str(value or "").strip()
    if readme_mode == "replace-sections" and intro_text is None and not normalized_sections:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["missing_field"],
            message="readme_update.mode `replace-sections` requires intro_text or at least one allowed section replacement.",
            field="readme_update",
            stop_category="validator_mismatch",
        )
    existing_readme_sections = ((context.get("readme") or {}).get("sections") or {})
    for heading in normalized_sections:
        if heading not in existing_readme_sections:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["unsupported_layout"],
                message=f"Collected README snapshot is missing section `{heading}`.",
                field=f"readme_update.sections.{heading}",
                stop_category="rewrite_block_unsupported",
            )

    issue_action = normalized_plan.get("issue_action")
    if not isinstance(issue_action, dict):
        issue_action = {}
    issue_action = normalize_mapping("issue_action", issue_action, warnings=warnings, warning_details=warning_details)
    issue_mode = normalize_string(issue_action.get("mode"))
    if issue_mode not in {"noop", "create", "reuse-existing", "sync-existing-body"}:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["invalid_mode"],
            message="issue_action.mode must be `noop`, `create`, `reuse-existing`, or `sync-existing-body`.",
            field="issue_action.mode",
            stop_category="validator_mismatch",
        )
    issue_title = normalize_string(issue_action.get("title"))
    issue_body_markdown = str(issue_action.get("body_markdown") or "")
    issue_defaults = context.get("issue_defaults") if isinstance(context.get("issue_defaults"), dict) else {}
    project_mode = normalize_string(
        issue_action.get("project_mode") or issue_defaults.get("project_mode") or "auto-add-first"
    ) or "auto-add-first"
    project_title = normalize_string(
        issue_action.get("project_title")
        or context.get("project_title_default")
        or issue_tools.DEFAULT_PROJECT_TITLE
    ) or issue_tools.DEFAULT_PROJECT_TITLE
    if issue_mode != "noop":
        if not issue_title:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["missing_field"],
                message="issue_action requires `title` when mode is not `noop`.",
                field="issue_action.title",
                stop_category="validator_mismatch",
            )
        if issue_mode in {"create", "sync-existing-body"} and not issue_body_markdown.strip():
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["missing_field"],
                message="issue_action requires `body_markdown` for create/sync modes.",
                field="issue_action.body_markdown",
                stop_category="validator_mismatch",
            )
        if issue_title and issue_title != expected_issue_title(context):
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["validator_mismatch"],
                message=f"Issue title must match the target release title `{expected_issue_title(context)}`.",
                field="issue_action.title",
                stop_category="validator_mismatch",
            )
        if project_mode not in {"auto-add-first", "require-scope", "issue-only"}:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["invalid_mode"],
                message="issue_action.project_mode must be `auto-add-first`, `require-scope`, or `issue-only`.",
                field="issue_action.project_mode",
                stop_category="validator_mismatch",
            )

    existing_issue = context.get("existing_release_issue")
    validated_issue_snapshot = plan_tools.existing_issue_snapshot(existing_issue)
    if issue_mode in {"reuse-existing", "sync-existing-body"} and not isinstance(existing_issue, dict):
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["stale_issue_snapshot"],
            message="issue_action requires a collected existing release issue snapshot, but none is available.",
            field="issue_action.mode",
            stop_category="stale_issue_snapshot",
        )

    evidence_status = normalize_string(normalized_plan.get("evidence_status")).lower()
    if evidence_status not in {"complete", "incomplete", "not-applicable"}:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["invalid_mode"],
            message="evidence_status must be `complete`, `incomplete`, or `not-applicable`.",
            field="evidence_status",
            stop_category="validator_mismatch",
        )
    lint_checks = lint.get("checks") or {}
    if lint_checks.get("evidence_complete") is False and evidence_status == "complete":
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["release_gate_incomplete"],
            message="Plan claims complete release-gate evidence, but lint marked evidence as incomplete.",
            field="evidence_status",
            stop_category="release_gate_incomplete",
        )

    repo_root = Path(str(context.get("repo_root") or ".")).resolve()
    try:
        current_head = plan_tools.current_head_commit(repo_root)
    except Exception as exc:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["stale_context"],
            message=str(exc),
            field="head_commit",
            stop_category="stale_context",
        )
        current_head = ""

    if current_head and current_head != normalize_string(context.get("head_commit")):
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["stale_context"],
            message="HEAD changed after collection; rerun collect -> lint -> packet build before apply.",
            field="head_commit",
            stop_category="stale_context",
        )

    source_fingerprints = context.get("source_fingerprints") or {}
    rule_files = context.get("rule_files") or {}
    stale_sources: list[str] = []
    for key in ("publish_configuration", "readme"):
        path_text = normalize_string(rule_files.get(key))
        fingerprint = normalize_string(source_fingerprints.get(key))
        if not path_text or not fingerprint:
            continue
        current_text = Path(path_text).read_text(encoding="utf-8")
        if plan_tools.json_fingerprint(current_text) != fingerprint:
            stale_sources.append(key)
    if stale_sources:
        push_issue(
            errors,
            error_details,
            code=contract.VALIDATION_ERROR_CODES["stale_context"],
            message="Collected release source files changed after collection: " + ", ".join(stale_sources),
            field="source_fingerprints",
            stop_category="stale_context",
        )

    if not errors and issue_mode != "noop":
        validation_commands.append("gh auth status")
        try:
            auth_status = issue_tools.run_command(["gh", "auth", "status"], cwd=repo_root)
        except Exception as exc:
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["missing_auth"],
                message=str(exc),
                field="issue_action",
                stop_category="missing_auth",
            )
            auth_status = ""

        if not errors and project_mode == "require-scope" and "project" not in auth_status.lower():
            push_issue(
                errors,
                error_details,
                code=contract.VALIDATION_ERROR_CODES["project_scope_required"],
                message="Issue action requires project scope, but current gh auth status does not include it.",
                field="issue_action.project_mode",
                stop_category="project_scope_required",
            )

        if not errors and issue_mode in {"reuse-existing", "sync-existing-body"} and isinstance(existing_issue, dict):
            issue_number = int(existing_issue.get("number") or 0)
            validation_commands.append(f"gh issue view {issue_number}")
            live_issue = plan_tools.fetch_issue_snapshot(repo_root, context.get("repo_slug"), issue_number)
            live_snapshot = plan_tools.existing_issue_snapshot(live_issue)
            if live_snapshot != validated_issue_snapshot:
                push_issue(
                    errors,
                    error_details,
                    code=contract.VALIDATION_ERROR_CODES["stale_issue_snapshot"],
                    message="The live release issue snapshot changed after collection; refresh before syncing or reusing it.",
                    field="existing_release_issue",
                    stop_category="stale_issue_snapshot",
                )
            else:
                validated_issue_snapshot = live_snapshot

    for detail in error_details:
        category = detail.get("stop_category")
        if isinstance(category, str) and category not in stop_reasons:
            stop_reasons.append(category)

    normalized = {
        "repo_root": str(repo_root),
        "repo_slug": context.get("repo_slug"),
        "context_fingerprint": expected_context_fingerprint,
        "freshness_tuple": expected_freshness,
        "source_fingerprints": {
            key: normalize_string(value)
            for key, value in source_fingerprints.items()
            if normalize_string(value)
        },
        "rule_files": {
            key: normalize_string(value)
            for key, value in rule_files.items()
            if normalize_string(value)
        },
        "local_release_helper_status": (context.get("local_release_helper") or {}).get("status"),
        "overall_confidence": normalize_string(normalized_plan.get("overall_confidence")).lower() or "medium",
        "stop_reasons": unique_strings(normalized_plan.get("stop_reasons")),
        "evidence_status": evidence_status,
        "draft_basis": {
            "common_path_sufficient": common_path_sufficient,
            "raw_reread_count": raw_reread_count,
            "reread_reasons": normalized_reasons,
            "focused_packets_used": focused_packets_used,
            "compensatory_reread_detected": compensatory_reread_detected,
            "synthesis_packet_fingerprint": normalize_string(draft_basis.get("synthesis_packet_fingerprint")),
        },
        "publish_update": {
            "mode": publish_mode,
            "fields": publish_fields,
        },
        "readme_update": {
            "mode": readme_mode,
            "intro_text": intro_text,
            "sections": normalized_sections,
        },
        "issue_action": {
            "mode": issue_mode,
            "title": issue_title,
            "body_markdown": issue_body_markdown,
            "project_mode": project_mode,
            "project_title": project_title,
        },
        "validated_existing_issue_snapshot": validated_issue_snapshot,
        "validation_commands": validation_commands,
    }

    gate = apply_gate_status(issue_mode, lint)
    can_apply = not errors and not gate["uncovered_stop_categories"]
    gate["status"] = "pass" if can_apply else "fail"
    return {
        "valid": not errors,
        "can_apply": can_apply,
        "errors": errors,
        "warnings": warnings,
        "error_details": error_details,
        "warning_details": warning_details,
        "stop_reasons": stop_reasons,
        "validation_commands": validation_commands,
        "normalized_plan": normalized,
        "normalized_plan_fingerprint": plan_tools.json_fingerprint(normalized),
        "apply_gate_status": gate,
    }


def main() -> int:
    args = parse_args()
    context = plan_tools.load_json(Path(args.context).resolve())
    lint = plan_tools.load_json(Path(args.lint).resolve())
    plan = plan_tools.load_json(Path(args.plan).resolve())
    payload = validate_plan_contract(context, lint, plan)
    if args.output:
        plan_tools.write_json(Path(args.output).resolve(), payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
