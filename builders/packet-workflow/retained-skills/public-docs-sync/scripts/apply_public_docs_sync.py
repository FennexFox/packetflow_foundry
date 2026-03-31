#!/usr/bin/env python3
"""Apply validated deterministic public-doc fixes and then persist the last-success marker."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_public_docs_sync import json_fingerprint, load_json

SKILL_VERSION = "0.5.0"
README_SETTINGS_HEADER = "| Setting | Default | Purpose |"
README_SETTINGS_ROW_RE = re.compile(
    r"^\|\s*`(?P<name>[^`]+)`\s*\|\s*`?(?P<default>[^|`]*)`?\s*\|\s*(?P<purpose>.+?)\s*\|\s*$"
)
MARKDOWN_LINK_TARGET_RE = r"(\[[^\]]+\]\()(?P<target>{target})(\))"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True, help="Validator output JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Report the marker update without mutating.")
    parser.add_argument("--state-file", help="Optional override for the last-success marker JSON path.")
    parser.add_argument("--result-output", help="Optional machine-readable apply result JSON.")
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


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


def normalize_relpath(path: str) -> str:
    return str(path).replace("\\", "/")


def newline_style(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def quote_yaml_scalar(value: str) -> str:
    return json.dumps(value)


def render_issue_template_value(field: str, value: Any) -> str:
    if field == "labels":
        items = [quote_yaml_scalar(str(item)) for item in value]
        return "[" + ", ".join(items) + "]"
    return quote_yaml_scalar(str(value))


def relpath_to_abs(repo_root: Path, relpath: str) -> Path:
    return (repo_root / Path(relpath)).resolve()


def load_file_text(
    repo_root: Path,
    relpath: str,
    original_text: dict[str, str],
    current_text: dict[str, str],
) -> str:
    relpath = normalize_relpath(relpath)
    if relpath in current_text:
        return current_text[relpath]
    absolute_path = relpath_to_abs(repo_root, relpath)
    if not absolute_path.is_file():
        raise RuntimeError(f"deterministic apply target does not exist: {relpath}")
    text = absolute_path.read_text(encoding="utf-8", errors="replace")
    original_text[relpath] = text
    current_text[relpath] = text
    return text


def store_file_text(relpath: str, text: str, current_text: dict[str, str]) -> None:
    current_text[normalize_relpath(relpath)] = text


def render_settings_row(setting: str, default: str, purpose: str) -> str:
    safe_purpose = purpose.replace("|", "\\|").strip()
    return f"| `{setting}` | `{default}` | {safe_purpose} |"


def apply_settings_table_default_sync(text: str, action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    table_start = None
    for index, line in enumerate(lines):
        if line.strip() == README_SETTINGS_HEADER:
            table_start = index
            break
    if table_start is None:
        raise RuntimeError("README settings table header was not found.")

    separator_index = table_start + 1
    if separator_index >= len(lines):
        raise RuntimeError("README settings table is missing its separator row.")

    table_end = separator_index + 1
    while table_end < len(lines) and lines[table_end].lstrip().startswith("|"):
        table_end += 1

    details = action.get("details", {})
    setting = str(details.get("setting") or "").strip()
    expected_default = str(details.get("expected_default") or "").strip()
    fallback_purpose = (
        str(details.get("documented_purpose") or "").strip()
        or str(details.get("setting_description") or "").strip()
        or str(details.get("setting_label") or "").strip()
        or setting
    )
    line_ending = newline_style(text)

    for row_index in range(separator_index + 1, table_end):
        raw_line = lines[row_index].rstrip("\r\n")
        match = README_SETTINGS_ROW_RE.match(raw_line)
        if not match or match.group("name") != setting:
            continue
        purpose = match.group("purpose").strip() or fallback_purpose
        replacement = render_settings_row(setting, expected_default, purpose)
        if replacement == raw_line:
            return text, {
                "index": action.get("index"),
                "type": action.get("canonical_type"),
                "path": action.get("path"),
                "summary": action.get("summary"),
                "changed": False,
                "change_kind": "noop",
            }
        lines[row_index] = replacement + line_ending
        return "".join(lines), {
            "index": action.get("index"),
            "type": action.get("canonical_type"),
            "path": action.get("path"),
            "summary": action.get("summary"),
            "changed": True,
            "change_kind": "update",
        }

    insertion = render_settings_row(setting, expected_default, fallback_purpose) + line_ending
    lines.insert(table_end, insertion)
    return "".join(lines), {
        "index": action.get("index"),
        "type": action.get("canonical_type"),
        "path": action.get("path"),
        "summary": action.get("summary"),
        "changed": True,
        "change_kind": "insert",
    }


def apply_relative_link_fix(text: str, action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details = action.get("details", {})
    target = re.escape(str(details.get("target") or ""))
    replacement_target = str(details.get("replacement_target") or "")
    expected_count = int(details.get("expected_count") or 1)
    pattern = re.compile(MARKDOWN_LINK_TARGET_RE.format(target=target))
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1) + replacement_target + match.group(3)

    updated = pattern.sub(replace, text)
    if count != expected_count:
        raise RuntimeError(
            f"expected {expected_count} markdown link target replacement(s) in {action.get('path')}, found {count}"
        )
    return updated, {
        "index": action.get("index"),
        "type": action.get("canonical_type"),
        "path": action.get("path"),
        "summary": action.get("summary"),
        "changed": updated != text,
        "change_kind": "replace",
    }


def apply_public_doc_reference_sync(text: str, action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details = action.get("details", {})
    match_text = str(details.get("match_text") or "")
    replacement_text = str(details.get("replacement_text") or "")
    expected_count = int(details.get("expected_count") or 1)
    count = text.count(match_text)
    if count != expected_count:
        raise RuntimeError(
            f"expected {expected_count} reference replacement(s) in {action.get('path')}, found {count}"
        )
    updated = text.replace(match_text, replacement_text, expected_count)
    return updated, {
        "index": action.get("index"),
        "type": action.get("canonical_type"),
        "path": action.get("path"),
        "summary": action.get("summary"),
        "changed": updated != text,
        "change_kind": "replace",
    }


def apply_issue_template_metadata_sync(text: str, action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details = action.get("details", {})
    field = str(details.get("field") or "")
    rendered = f"{field}: {render_issue_template_value(field, details.get('value'))}"
    pattern = re.compile(rf"^{re.escape(field)}:\s*.*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) > 1:
        raise RuntimeError(f"issue-template metadata field `{field}` appears multiple times in {action.get('path')}")

    if matches:
        updated = pattern.sub(rendered, text, count=1)
    else:
        line_ending = newline_style(text)
        body_match = re.search(r"^body:\s*$", text, flags=re.MULTILINE)
        if body_match:
            updated = text[: body_match.start()] + rendered + line_ending + text[body_match.start() :]
        elif text:
            suffix = "" if text.endswith(("\n", "\r")) else line_ending
            updated = text + suffix + rendered + line_ending
        else:
            updated = rendered + line_ending
    return updated, {
        "index": action.get("index"),
        "type": action.get("canonical_type"),
        "path": action.get("path"),
        "summary": action.get("summary"),
        "changed": updated != text,
        "change_kind": "replace" if matches else "insert",
    }


def apply_action_to_text(text: str, action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    canonical_type = action.get("canonical_type")
    if canonical_type == "settings_table_default_sync":
        return apply_settings_table_default_sync(text, action)
    if canonical_type == "relative_link_fix":
        return apply_relative_link_fix(text, action)
    if canonical_type == "public_doc_reference_sync":
        return apply_public_doc_reference_sync(text, action)
    if canonical_type == "issue_template_metadata_sync":
        return apply_issue_template_metadata_sync(text, action)
    raise RuntimeError(f"unsupported deterministic action type `{canonical_type}` in validator output")


def snapshot_from_validation(validation: dict[str, Any]) -> dict[str, Any]:
    snapshot = validation.get("apply_context_snapshot")
    if not isinstance(snapshot, dict):
        raise RuntimeError("validator output is missing `apply_context_snapshot`")
    snapshot_fingerprint = str(validation.get("apply_context_snapshot_fingerprint", "")).strip()
    if not snapshot_fingerprint:
        raise RuntimeError("validator output is missing `apply_context_snapshot_fingerprint`")
    if json_fingerprint(snapshot) != snapshot_fingerprint:
        raise RuntimeError("validator output apply-context snapshot fingerprint does not match the embedded snapshot")
    return snapshot


def normalized_plan_from_validation(
    validation: dict[str, Any],
) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[dict[str, Any]], bool, dict[str, Any]]:
    normalized_plan = validation.get("normalized_plan")
    if not isinstance(normalized_plan, dict):
        raise RuntimeError("validator output is missing `normalized_plan`")
    normalized_plan_fingerprint = str(validation.get("normalized_plan_fingerprint", "")).strip()
    if not normalized_plan_fingerprint:
        raise RuntimeError("validator output is missing `normalized_plan_fingerprint`")
    if json_fingerprint(normalized_plan) != normalized_plan_fingerprint:
        raise RuntimeError("validator output normalized-plan fingerprint does not match the normalized plan")
    if not validation.get("valid"):
        raise RuntimeError("refusing to apply validator output marked invalid")
    if not validation.get("can_apply"):
        raise RuntimeError("refusing to apply validator output marked not edit-safe")
    apply_gate_status = validation.get("apply_gate_status") or {}
    if apply_gate_status.get("apply_edits_status") != "pass":
        raise RuntimeError("refusing to apply validator output with a failed deterministic edit gate")
    if apply_gate_status.get("uncovered_stop_categories"):
        raise RuntimeError("refusing to apply while applicable stop categories remain uncovered")
    deterministic_actions = validation.get("deterministic_actions")
    if not isinstance(deterministic_actions, list):
        deterministic_actions = [
            action
            for action in normalized_plan.get("actions", [])
            if isinstance(action, dict) and action.get("action_mode") == "deterministic-edit"
        ]
    manual_review_actions = validation.get("manual_review_actions")
    if not isinstance(manual_review_actions, list):
        manual_review_actions = [
            action
            for action in normalized_plan.get("actions", [])
            if isinstance(action, dict) and action.get("action_mode") == "manual-only-review"
        ]
    snapshot = snapshot_from_validation(validation)
    if normalized_plan.get("context_id") != snapshot.get("context_id"):
        raise RuntimeError("validator mismatch: normalized plan context id does not match the apply snapshot")
    if normalized_plan.get("context_fingerprint") != snapshot.get("context_fingerprint"):
        raise RuntimeError("validator mismatch: normalized plan context fingerprint does not match the apply snapshot")
    return (
        normalized_plan,
        normalized_plan_fingerprint,
        deterministic_actions,
        manual_review_actions,
        bool(validation.get("can_update_marker")),
        snapshot,
    )


def build_marker(snapshot: dict[str, Any], normalized_plan: dict[str, Any], state_file: Path) -> dict[str, Any]:
    return {
        "skill_name": "public-docs-sync",
        "skill_version": SKILL_VERSION,
        "repo_root": snapshot.get("repo_root"),
        "repo_hash": snapshot.get("repo_hash"),
        "repo_slug": snapshot.get("repo_slug"),
        "branch": snapshot.get("branch"),
        "baseline_commit": snapshot.get("baseline_commit"),
        "head_commit": snapshot.get("head_commit"),
        "context_id": snapshot.get("context_id"),
        "context_fingerprint": snapshot.get("context_fingerprint"),
        "audited_doc_paths": snapshot.get("audited_doc_paths", []),
        "active_packets": normalized_plan.get("selected_packets", []),
        "relevant_ref": snapshot.get("relevant_ref"),
        "primary_pr_number": snapshot.get("primary_pr_number"),
        "primary_pr_url": snapshot.get("primary_pr_url"),
        "github_evidence_digest": snapshot.get("github_evidence_digest"),
        "ref_selection_source": snapshot.get("ref_selection_source"),
        "state_file": str(state_file),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "doc_update_status": normalized_plan.get("doc_update_status"),
        "marker_reason": normalized_plan.get("marker_reason") or "doc-sync-complete",
    }


def apply_validated_plan(
    validation: dict[str, Any],
    *,
    dry_run: bool,
    state_file: Path | None = None,
) -> dict[str, Any]:
    (
        normalized_plan,
        normalized_plan_fingerprint,
        deterministic_actions,
        manual_review_actions,
        can_update_marker,
        snapshot,
    ) = normalized_plan_from_validation(validation)
    repo_root = Path(str(snapshot.get("repo_root", ""))).resolve()
    expected_head = str(snapshot.get("head_commit", "")).strip()
    if repo_root.exists() and expected_head:
        current_head = run_git(repo_root, ["rev-parse", "HEAD"])
        if current_head != expected_head:
            raise RuntimeError("stale context: repository HEAD changed since validation snapshot")

    resolved_state_file = state_file or Path(str(snapshot.get("state_file", ""))).resolve()
    original_text: dict[str, str] = {}
    current_text: dict[str, str] = {}
    action_results: list[dict[str, Any]] = []
    for action in deterministic_actions:
        relpath = normalize_relpath(str(action.get("path") or ""))
        text = load_file_text(repo_root, relpath, original_text, current_text)
        updated, action_result = apply_action_to_text(text, action)
        store_file_text(relpath, updated, current_text)
        action_results.append(action_result)

    file_mutations: list[dict[str, Any]] = []
    changed_doc_paths: list[str] = []
    for relpath, updated in current_text.items():
        original = original_text[relpath]
        if updated == original:
            continue
        absolute_path = relpath_to_abs(repo_root, relpath)
        file_mutations.append({"type": "write", "path": str(absolute_path), "target_kind": "repo-doc"})
        changed_doc_paths.append(relpath)
        if not dry_run:
            absolute_path.write_text(updated, encoding="utf-8")

    marker = build_marker(snapshot, normalized_plan, resolved_state_file) if can_update_marker else None
    marker_written = False
    if marker is not None and not dry_run:
        write_json(resolved_state_file, marker)
        marker_written = True

    normalized_actions = normalized_plan.get("actions", [])
    validation_stop_reasons = [str(item) for item in validation.get("stop_reasons", []) if str(item).strip()]
    mutations = file_mutations[:]
    if marker is not None and not dry_run:
        mutations.append({"type": "write", "path": str(resolved_state_file), "target_kind": "last-success-marker"})
    return {
        "skill_name": "public-docs-sync",
        "context_id": snapshot.get("context_id"),
        "dry_run": dry_run,
        "validation_source": "validator_normalized_plan",
        "normalized_plan_fingerprint": normalized_plan_fingerprint,
        "apply_succeeded": True,
        "mutation_type": "public-docs-sync",
        "state_file": str(resolved_state_file),
        "marker_update_attempted": can_update_marker,
        "marker_update_written": marker_written,
        "marker_written": marker_written,
        "can_update_marker": can_update_marker,
        "action_count": len(normalized_actions),
        "deterministic_edit_count": len(deterministic_actions),
        "manual_review_count": len(manual_review_actions),
        "doc_edit_count": len(changed_doc_paths),
        "changed_doc_paths": changed_doc_paths,
        "mutations": [] if dry_run else mutations,
        "message": (
            "Applied validated deterministic public-doc edits and wrote the success marker."
            if marker_written
            else "Applied validated deterministic public-doc edits without advancing the success marker."
        ),
        "marker_preview": marker,
        "stop_reasons": validation_stop_reasons,
        "normalized_actions": normalized_actions,
        "deterministic_actions": deterministic_actions,
        "manual_review_actions": manual_review_actions,
        "action_results": action_results,
        "apply_context_snapshot": snapshot,
    }


def main() -> int:
    args = parse_args()
    validation = load_json(Path(args.validation).resolve())
    state_file = Path(args.state_file).resolve() if args.state_file else None
    result = apply_validated_plan(validation, dry_run=args.dry_run, state_file=state_file)
    if args.result_output:
        write_json(Path(args.result_output).resolve(), result)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
