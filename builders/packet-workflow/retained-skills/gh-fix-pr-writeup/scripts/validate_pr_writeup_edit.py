#!/usr/bin/env python3
"""Validate a candidate PR title/body update before guarded apply."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import lint_pr_writeup as lint_pr_writeup
import pr_writeup_contract as contract
import pr_writeup_tools as tools


VALIDATION_ERROR_CODES = contract.VALIDATION_ERROR_CODES
VALIDATION_WARNING_CODES = contract.VALIDATION_WARNING_CODES
APPLICABLE_STOP_CATEGORIES = contract.APPLICABLE_STOP_CATEGORIES
LOCAL_STOP_CATEGORIES = contract.LOCAL_STOP_CATEGORIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Path to JSON from collect_pr_context.py")
    parser.add_argument("--title", required=True, help="Replacement PR title")
    parser.add_argument("--body-file", required=True, help="Path to replacement PR body markdown")
    parser.add_argument("--qa-result", help="Optional QA result JSON.")
    parser.add_argument(
        "--worker-claim-conflict",
        action="store_true",
        help="Require QA because worker and local claim findings conflict.",
    )
    parser.add_argument(
        "--raw-reread-reason",
        action="append",
        choices=contract.RAW_REREAD_ALLOWED_REASONS,
        help="Optional explicit reread reason that can trigger QA.",
    )
    parser.add_argument("--output", help="Optional output path for validation JSON")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return contract.load_json(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    contract.write_json(path, payload)


def json_fingerprint(payload: dict[str, Any]) -> str:
    return contract.json_fingerprint(payload)


def normalize_scalar(value: Any) -> str:
    return str(value or "").strip()


def normalize_paths(paths: list[Any]) -> list[str]:
    return [str(path).replace("\\", "/") for path in paths]


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


def validate_context_contract(context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not normalize_scalar(context.get("repo_root")):
        errors.append("Context is missing `repo_root`.")
    pr = context.get("pr")
    if not isinstance(pr, dict):
        errors.append("Context is missing `pr` metadata.")
        return errors
    for field in ("number", "title", "body", "url", "headRefName", "headRefOid", "baseRefName"):
        if field == "number":
            if pr.get(field) in {None, ""}:
                errors.append("Context is missing `pr.number`.")
        elif not normalize_scalar(pr.get(field)):
            errors.append(f"Context is missing `pr.{field}`.")
    if not isinstance(context.get("changed_files"), list):
        errors.append("Context is missing `changed_files`.")
    return errors


def build_candidate_context(context: dict[str, Any], title: str, body: str) -> dict[str, Any]:
    updated = deepcopy(context)
    updated["pr"] = {**dict(context.get("pr") or {}), "title": title, "body": body}
    updated["current_body_sections"] = list(lint_pr_writeup.section_bodies(body).keys())
    checks = dict(updated.get("checks") or {})
    checks["title_matches_conventional_commit"] = bool(tools.PR_TITLE_RE.match(title))
    checks["title_length"] = len(title)
    checks["body_has_template_sections"] = bool(updated["current_body_sections"])
    updated["checks"] = checks
    return updated


def stale_snapshot_fields(
    context_snapshot: dict[str, Any],
    live_pr: dict[str, Any],
    live_changed_files: list[str],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for field in contract.VALIDATED_SNAPSHOT_FIELDS:
        expected = normalize_scalar(context_snapshot.get(field))
        actual = normalize_scalar(live_pr.get(field))
        if expected != actual:
            mismatches.append({"field": field, "expected": expected, "actual": actual})
    expected_files = normalize_paths(list(context_snapshot.get("changed_files") or []))
    actual_files = normalize_paths(live_changed_files)
    if expected_files != actual_files:
        mismatches.append({"field": "changed_files", "expected": expected_files, "actual": actual_files})
    return mismatches


def infer_review_mode(context: dict[str, Any]) -> str:
    file_count = len(list(context.get("changed_files") or []))
    groups = context.get("changed_file_groups") or {}
    active = [
        name for name in ("runtime", "automation", "docs", "tests", "config", "other")
        if (groups.get(name) or {}).get("count", 0) > 0
    ]
    if file_count <= contract.SMALL_FILE_LIMIT and len(active) <= contract.SMALL_GROUP_LIMIT:
        return "local-only"
    if file_count > contract.MEDIUM_FILE_LIMIT or len(active) >= contract.LARGE_GROUP_LIMIT:
        return "broad-delegation"
    return "targeted-delegation"


def qa_summary(qa_result: dict[str, Any] | None) -> dict[str, Any]:
    payload = qa_result if isinstance(qa_result, dict) else {}
    keep_or_revise = normalize_scalar(payload.get("keep_or_revise")).lower()
    return {
        "keep_or_revise": keep_or_revise or None,
        "rule_violations": [str(item) for item in payload.get("rule_violations", []) if str(item).strip()],
        "coverage_gaps": [str(item) for item in payload.get("coverage_gaps", []) if str(item).strip()],
        "unsupported_claims": [str(item) for item in payload.get("unsupported_claims", []) if str(item).strip()],
    }


def qa_is_clear(qa_result: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not isinstance(qa_result, dict):
        return False, "QA clear result is required but was not provided."
    summary = qa_summary(qa_result)
    if summary["keep_or_revise"] not in {"keep", "accept"}:
        return False, "QA result did not clear the draft for keep/apply."
    for key in ("rule_violations", "coverage_gaps", "unsupported_claims"):
        if summary[key]:
            return False, f"QA result reported {key.replace('_', ' ')}."
    return True, None


def stop_status() -> dict[str, Any]:
    return contract.stop_status()


def validate_pr_writeup_edit(
    context: dict[str, Any],
    title: str,
    body: str,
    *,
    qa_result: dict[str, Any] | None = None,
    worker_claim_conflict: bool = False,
    raw_reread_reasons: list[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    error_details: list[dict[str, Any]] = []
    warning_details: list[dict[str, Any]] = []
    stop_reasons: list[str] = []

    context_errors = validate_context_contract(context)
    for message in context_errors:
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_context_field"],
            message=message,
            stop_category="validator_mismatch",
        )
    if not title.strip():
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_candidate_field"],
            message="Candidate title is empty.",
            field="title",
            stop_category="invalid_candidate",
        )
    if not body.strip():
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["missing_candidate_field"],
            message="Candidate body is empty.",
            field="body",
            stop_category="invalid_candidate",
        )

    candidate_findings: dict[str, Any] = {"errors": [], "warnings": [], "info": [], "detected": {}}
    repo_root = Path(str(context.get("repo_root", "."))).resolve()
    repo_slug = context.get("repo_slug")
    pr = context.get("pr") or {}
    pr_number = int(pr.get("number") or 0) if str(pr.get("number") or "").strip() else 0
    validation_commands: list[str] = [
        "candidate lint",
        "gh auth status",
        f"gh pr view {pr_number} --json number,title,body,headRefName,headRefOid,baseRefName,url,closingIssuesReferences",
        f"gh pr diff {pr_number} --name-only",
    ] if pr_number else ["candidate lint", "gh auth status"]
    if qa_result is not None:
        validation_commands.append("qa result review")

    live_pr: dict[str, Any] | None = None
    live_changed_files: list[str] = []
    stale_fields: list[dict[str, Any]] = []

    if not errors:
        candidate_context = build_candidate_context(context, title.strip(), body)
        candidate_findings = lint_pr_writeup.collect_findings(candidate_context, original_context=context)
        for message in candidate_findings.get("warnings", []):
            push_issue(
                warnings,
                warning_details,
                code=VALIDATION_WARNING_CODES["candidate_warning"],
                message=message,
            )
        unsupported_claim_messages = [
            message
            for message in candidate_findings.get("errors", [])
            if "direct verification" in message.lower() or "claims verification" in message.lower()
        ]
        non_claim_errors = [
            message for message in candidate_findings.get("errors", []) if message not in unsupported_claim_messages
        ]
        for message in non_claim_errors:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["candidate_lint_failed"],
                message=message,
                stop_category="invalid_candidate",
            )
        for message in unsupported_claim_messages:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["unsupported_claims"],
                message=message,
                stop_category="unsupported_claims_detected",
            )

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
            live_pr = tools.load_pr_metadata(pr_number, repo_root, repo_slug)
            live_changed_files = tools.load_pr_changed_files(pr_number, repo_root, repo_slug)
        except Exception as exc:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["live_snapshot_unavailable"],
                message=str(exc),
                stop_category="live_snapshot_unavailable",
            )

    if not errors and live_pr is not None:
        context_snapshot = contract.minimal_validated_snapshot(pr, list(context.get("changed_files") or []))
        stale_fields = stale_snapshot_fields(context_snapshot, live_pr, live_changed_files)
        if stale_fields:
            push_issue(
                errors,
                error_details,
                code=VALIDATION_ERROR_CODES["stale_context"],
                message="The live PR snapshot changed after collection; refresh collect -> lint -> packet build before editing.",
                stop_category="stale_context",
            )

    review_mode = infer_review_mode(context)
    drafting_basis = candidate_findings.get("drafting_basis") or {}
    qa_required, qa_reason = contract.should_require_qa(
        rewrite_strategy=str(drafting_basis.get("rewrite_strategy") or "targeted-touch-up"),
        review_mode=review_mode,
        worker_conflict=worker_claim_conflict,
        raw_reread_reasons=list(raw_reread_reasons or []),
    )
    qa_clear, qa_block_reason = qa_is_clear(qa_result) if qa_required else (False, None)
    if not errors and qa_required and not qa_clear:
        push_issue(
            errors,
            error_details,
            code=VALIDATION_ERROR_CODES["qa_clear_required"] if qa_result is None else VALIDATION_ERROR_CODES["qa_rejected"],
            message=qa_block_reason or "QA review is required before apply-safe validation.",
            stop_category="qa_required",
        )

    for detail in error_details:
        category = detail.get("stop_category")
        if isinstance(category, str) and category not in stop_reasons:
            stop_reasons.append(category)

    validated_snapshot = contract.minimal_validated_snapshot(
        live_pr or pr,
        live_changed_files or list(context.get("changed_files") or []),
    )
    normalized_edit = {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "pr_number": pr_number,
        "title": title.strip(),
        "body": body,
        "validated_snapshot": validated_snapshot,
        "validation_commands": validation_commands,
        "review_mode": review_mode,
        "qa_gate": {
            "required": qa_required,
            "reason": qa_reason,
            "qa_clear": qa_clear if qa_required else False,
            "worker_claim_conflict": worker_claim_conflict,
            "raw_reread_reasons": list(raw_reread_reasons or []),
            "qa_summary": qa_summary(qa_result) if qa_result is not None else None,
        },
    }
    gate = stop_status()
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
        "review_mode": review_mode,
        "qa_required": qa_required,
        "qa_reason": qa_reason,
        "qa_clear": qa_clear if qa_required else False,
        "normalized_edit": normalized_edit,
        "normalized_edit_fingerprint": json_fingerprint(normalized_edit),
        "context_file_fingerprint": json_fingerprint(context),
        "apply_gate_status": gate,
    }


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    body = Path(args.body_file).resolve().read_text(encoding="utf-8")
    qa_result = load_json(Path(args.qa_result).resolve()) if args.qa_result else None
    payload = validate_pr_writeup_edit(
        context,
        args.title,
        body,
        qa_result=qa_result,
        worker_claim_conflict=args.worker_claim_conflict,
        raw_reread_reasons=list(args.raw_reread_reason or []),
    )
    if args.output:
        write_json(Path(args.output).resolve(), payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
