#!/usr/bin/env python3
"""Validate a candidate PR create request before guarded apply."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import lint_pr_create as lint_pr_create
import pr_create_contract as contract
import pr_create_tools as tools


VALIDATION_ERROR_CODES = contract.VALIDATION_ERROR_CODES
VALIDATION_WARNING_CODES = contract.VALIDATION_WARNING_CODES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Path to JSON from collect_pr_create_context.py")
    parser.add_argument("--title", required=True, help="Draft PR title")
    parser.add_argument("--body-file", required=True, help="Path to draft PR body markdown")
    parser.add_argument("--output", help="Optional output path for validation JSON")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return contract.load_json(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    contract.write_json(path, payload)


def normalize_scalar(value: Any) -> str:
    return contract.normalize_scalar(value)


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
    detail: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    if stop_category is not None:
        detail["stop_category"] = stop_category
    details.append(detail)


def normalize_handles(values: list[Any]) -> list[str]:
    tokens: dict[str, str] = {}
    for value in values:
        for piece in str(value or "").split(","):
            token = piece.strip().lower()
            if token and token not in tokens:
                tokens[token] = token
    return sorted(tokens.values())


def normalize_labels(values: list[Any]) -> list[str]:
    tokens: dict[str, str] = {}
    for value in values:
        for piece in str(value or "").split(","):
            token = piece.strip()
            if token and token not in tokens:
                tokens[token] = token
    return sorted(tokens.values())


def normalize_milestone(value: Any) -> str | None:
    milestone = normalize_scalar(value)
    return milestone or None


def validate_context_contract(context: dict[str, Any]) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    if not normalize_scalar(context.get("repo_root")):
        errors.append(("validator_mismatch", "Context is missing `repo_root`."))
    if not normalize_scalar(context.get("resolved_head")):
        errors.append(("validator_mismatch", "Context is missing `resolved_head`."))
    if not normalize_scalar(context.get("repo_slug")):
        errors.append(("repo_inference_failed", "Context could not resolve `repo_slug`."))
    if not normalize_scalar(context.get("resolved_base")):
        errors.append(("base_resolution_failed", "Context could not resolve `resolved_base`."))
    template_selection = context.get("template_selection")
    if not isinstance(template_selection, dict):
        errors.append(("validator_mismatch", "Context is missing `template_selection`."))
    if not isinstance(context.get("changed_files"), list):
        errors.append(("validator_mismatch", "Context is missing `changed_files`."))
    return errors


def infer_review_mode(context: dict[str, Any]) -> str:
    groups = context.get("changed_file_groups") or {}
    active = [
        name
        for name in ("runtime", "automation", "docs", "tests", "config", "other")
        if (groups.get(name) or {}).get("count", 0) > 0
    ]
    file_count = len(list(context.get("changed_files") or []))
    if file_count <= contract.SMALL_FILE_LIMIT and len(active) <= contract.SMALL_GROUP_LIMIT:
        return "local-only"
    if file_count > contract.MEDIUM_FILE_LIMIT or len(active) >= contract.LARGE_GROUP_LIMIT:
        return "broad-delegation"
    return "targeted-delegation"


def context_snapshot_subset(context: dict[str, Any]) -> dict[str, Any]:
    template_selection = context.get("template_selection") or {}
    return {
        "local_head_oid": normalize_scalar(context.get("local_head_oid")),
        "remote_head_oid": normalize_scalar(context.get("remote_head_oid")),
        "repo_slug": normalize_scalar(context.get("repo_slug")),
        "base_ref": normalize_scalar(context.get("resolved_base")),
        "head_ref": normalize_scalar(context.get("resolved_head")),
        "changed_files_fingerprint": normalize_scalar(context.get("changed_files_fingerprint")),
        "template_path": normalize_scalar(template_selection.get("selected_path")).replace("\\", "/"),
        "template_fingerprint": normalize_scalar(template_selection.get("fingerprint")),
    }


def live_state(context: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(str(context.get("repo_root") or ".")).resolve()
    repo_slug = normalize_scalar(context.get("repo_slug")) or None
    head_ref = normalize_scalar(context.get("resolved_head"))
    base_ref = normalize_scalar(context.get("resolved_base"))
    template_selection = tools.select_pr_template(repo_root)
    duplicate_summary = tools.duplicate_check_summary(repo_root, repo_slug, head_ref) if repo_slug and head_ref else {}
    changed_files = tools.load_changed_files_between(repo_root, base_ref, head_ref)
    return {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "head_ref": head_ref,
        "base_ref": base_ref,
        "local_head_oid": tools.local_head_oid(repo_root, head_ref),
        "remote_head_oid": tools.remote_head_oid(repo_root, head_ref),
        "changed_files": changed_files,
        "changed_files_fingerprint": contract.json_fingerprint(changed_files),
        "template_selection": template_selection,
        "duplicate_check_summary": duplicate_summary,
    }


def subset_mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for field in contract.VALIDATED_SNAPSHOT_FIELDS:
        if field == "duplicate_check_summary":
            continue
        expected_value = normalize_scalar(expected.get(field))
        actual_value = normalize_scalar(actual.get(field))
        if field == "template_path":
            expected_value = expected_value.replace("\\", "/")
            actual_value = actual_value.replace("\\", "/")
        if expected_value != actual_value:
            mismatches.append({"field": field, "expected": expected_value, "actual": actual_value})
    return mismatches


def validate_pr_create(context: dict[str, Any], title: str, body: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    error_details: list[dict[str, Any]] = []
    warning_details: list[dict[str, Any]] = []
    stop_reasons: list[str] = []
    stale_fields: list[dict[str, Any]] = []

    for stop_category, message in validate_context_contract(context):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_context_field"],
            message=message,
            stop_category=stop_category,
        )

    if not title.strip():
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_candidate_field"],
            message="Candidate title is empty.",
            field="title",
            stop_category="invalid_title",
        )
    if not body.strip():
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_candidate_field"],
            message="Candidate body is empty.",
            field="body",
            stop_category="invalid_body",
        )

    template_selection = context.get("template_selection") or {}
    template_status = normalize_scalar(template_selection.get("status"))
    if template_status == "not_found":
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["template_not_found"],
            message="No unique default PR template was found.",
            stop_category="template_not_found",
        )
    elif template_status == "ambiguous":
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["template_ambiguous"],
            message="Multiple PR template candidates were found; fail closed.",
            stop_category="template_ambiguous",
        )
    if not normalize_scalar(context.get("remote_head_oid")):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["remote_head_missing"],
            message="Resolved head branch does not exist on origin.",
            stop_category="remote_head_missing",
        )
    elif normalize_scalar(context.get("local_head_oid")) != normalize_scalar(context.get("remote_head_oid")):
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["head_oid_mismatch"],
            message="Local and remote head OIDs differ.",
            stop_category="head_oid_mismatch",
        )

    candidate_findings: dict[str, Any] = {"errors": [], "warnings": [], "info": [], "detected": {}}
    if not errors:
        candidate_findings = lint_pr_create.collect_candidate_findings(context, title.strip(), body)
        for message in candidate_findings.get("warnings", []):
            push_issue(
                warnings,
                warning_details,
                code=VALIDATION_WARNING_CODES["candidate_warning"],
                message=message,
            )
        detected = candidate_findings.get("detected", {})
        for message in detected.get("title_errors", []):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["invalid_title"],
                message=message,
                stop_category="invalid_title",
            )
        for message in detected.get("body_errors", []):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["invalid_body"],
                message=message,
                stop_category="invalid_body",
            )
        for message in detected.get("unsupported_claims", []):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["unsupported_claim"],
                message=message,
                stop_category="unsupported_claim",
            )

    repo_root = Path(str(context.get("repo_root") or ".")).resolve()
    repo_slug = normalize_scalar(context.get("repo_slug")) or None
    head_ref = normalize_scalar(context.get("resolved_head"))
    base_ref = normalize_scalar(context.get("resolved_base"))
    validation_commands = [
        "candidate lint",
        "gh auth status",
        f"git rev-parse {head_ref}",
        f"git rev-parse refs/remotes/origin/{head_ref}",
        f"git diff --name-only origin/{base_ref}..origin/{head_ref}",
        "template selection recheck",
        f"gh pr list --head {head_ref} --state open",
    ]

    fresh_state: dict[str, Any] | None = None
    if not errors:
        try:
            tools.run_command(["gh", "auth", "status"], cwd=repo_root)
        except Exception as exc:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["missing_auth"],
                message=str(exc),
                stop_category="missing_auth",
            )

    if not errors:
        try:
            fresh_state = live_state(context)
        except Exception as exc:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["live_snapshot_unavailable"],
                message=str(exc),
                stop_category="live_snapshot_unavailable",
            )

    if not errors and fresh_state is not None:
        fresh_template = fresh_state.get("template_selection") or {}
        fresh_template_status = normalize_scalar(fresh_template.get("status"))
        if fresh_template_status == "not_found":
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["template_not_found"],
                message="No unique default PR template was found during validation recheck.",
                stop_category="template_not_found",
            )
        elif fresh_template_status == "ambiguous":
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["template_ambiguous"],
                message="Multiple PR template candidates were found during validation recheck.",
                stop_category="template_ambiguous",
            )

    if not errors and fresh_state is not None:
        if not normalize_scalar(fresh_state.get("remote_head_oid")):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["remote_head_missing"],
                message="Resolved head branch is missing on origin during validation recheck.",
                stop_category="remote_head_missing",
            )
        elif normalize_scalar(fresh_state.get("local_head_oid")) != normalize_scalar(fresh_state.get("remote_head_oid")):
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["head_oid_mismatch"],
                message="Local and remote head OIDs differ during validation recheck.",
                stop_category="head_oid_mismatch",
            )

    if not errors and fresh_state is not None:
        duplicate_summary = fresh_state.get("duplicate_check_summary") or {}
        if not contract.duplicate_summary_is_clear(duplicate_summary):
            existing_url = duplicate_summary.get("existing_pr_url")
            message = "A same-head open PR already exists."
            if existing_url:
                message += f" Existing PR: {existing_url}"
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["existing_open_pr"],
                message=message,
                stop_category="existing_open_pr",
            )

    if not errors and fresh_state is not None:
        stale_fields = subset_mismatches(context_snapshot_subset(context), {
            "local_head_oid": fresh_state.get("local_head_oid"),
            "remote_head_oid": fresh_state.get("remote_head_oid"),
            "repo_slug": fresh_state.get("repo_slug"),
            "base_ref": fresh_state.get("base_ref"),
            "head_ref": fresh_state.get("head_ref"),
            "changed_files_fingerprint": fresh_state.get("changed_files_fingerprint"),
            "template_path": (fresh_state.get("template_selection") or {}).get("selected_path"),
            "template_fingerprint": (fresh_state.get("template_selection") or {}).get("fingerprint"),
        })
        if stale_fields:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["stale_snapshot"],
                message="Collected context no longer matches the current branch/template snapshot.",
                stop_category="stale_snapshot",
            )

    for detail in error_details:
        category = detail.get("stop_category")
        if isinstance(category, str) and category not in stop_reasons:
            stop_reasons.append(category)

    reviewers = normalize_handles(list((context.get("create_options") or {}).get("reviewers") or []))
    assignees = normalize_handles(list((context.get("create_options") or {}).get("assignees") or []))
    labels = normalize_labels(list((context.get("create_options") or {}).get("labels") or []))
    milestone = normalize_milestone((context.get("create_options") or {}).get("milestone"))
    draft = bool((context.get("create_options") or {}).get("draft"))
    maintainer_can_modify = not bool((context.get("create_options") or {}).get("no_maintainer_edit"))

    normalized_create_request = {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "base": base_ref,
        "head": head_ref,
        "title": title.strip(),
        "body": body.rstrip(),
        "draft": draft,
        "reviewers": reviewers,
        "assignees": assignees,
        "labels": labels,
        "milestone": milestone,
        "maintainer_can_modify": maintainer_can_modify,
        "validation_commands": validation_commands,
        "review_mode": infer_review_mode(context),
        "qa_gate": {
            "required": False,
            "reason": None,
            "qa_clear": False,
        },
        "validated_snapshot": contract.build_validated_snapshot(
            {
                **context,
                "repo_slug": fresh_state.get("repo_slug") if fresh_state else context.get("repo_slug"),
                "resolved_base": fresh_state.get("base_ref") if fresh_state else context.get("resolved_base"),
                "resolved_head": fresh_state.get("head_ref") if fresh_state else context.get("resolved_head"),
                "local_head_oid": fresh_state.get("local_head_oid") if fresh_state else context.get("local_head_oid"),
                "remote_head_oid": fresh_state.get("remote_head_oid") if fresh_state else context.get("remote_head_oid"),
                "changed_files_fingerprint": fresh_state.get("changed_files_fingerprint") if fresh_state else context.get("changed_files_fingerprint"),
                "template_selection": fresh_state.get("template_selection") if fresh_state else context.get("template_selection"),
            },
            fresh_state.get("duplicate_check_summary") if fresh_state else {},
        ),
    }
    gate = contract.stop_status()
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
        "candidate_findings": candidate_findings,
        "validation_commands": validation_commands,
        "stale_fields": stale_fields,
        "review_mode": infer_review_mode(context),
        "normalized_create_request": normalized_create_request,
        "normalized_create_request_fingerprint": contract.json_fingerprint(normalized_create_request),
        "context_file_fingerprint": contract.json_fingerprint(context),
        "apply_gate_status": gate,
    }


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    body = Path(args.body_file).resolve().read_text(encoding="utf-8")
    payload = validate_pr_create(context, args.title, body)
    if args.output:
        write_json(Path(args.output).resolve(), payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
