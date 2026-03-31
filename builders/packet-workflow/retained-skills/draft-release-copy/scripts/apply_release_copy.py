#!/usr/bin/env python3
"""Apply a validated release-copy plan using normalized validator output only."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import create_release_issue as issue_tools
import release_copy_plan_tools as plan_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True, help="Path to validator output JSON")
    parser.add_argument("--dry-run", action="store_true", help="Plan mutations without writing files or mutating GitHub")
    parser.add_argument("--result-output", help="Optional path to write the apply result JSON")
    return parser.parse_args()


def fail(payload: dict[str, Any], output_path: Path | None, reason: str, message: str, **extra: Any) -> int:
    payload.update(extra)
    payload["apply_succeeded"] = False
    payload["stop_reason"] = reason
    payload["stop_reasons"] = [reason]
    if output_path is not None:
        plan_tools.write_json(output_path, payload)
    print(f"apply_release_copy.py: {message}")
    return 1


def normalized_plan_from_validation(validation: dict[str, Any]) -> dict[str, Any]:
    normalized_plan = validation.get("normalized_plan")
    if not isinstance(normalized_plan, dict):
        raise RuntimeError("validator output is missing `normalized_plan`")
    expected_fingerprint = str(validation.get("normalized_plan_fingerprint") or "").strip()
    if not expected_fingerprint:
        raise RuntimeError("validator output is missing `normalized_plan_fingerprint`")
    if plan_tools.json_fingerprint(normalized_plan) != expected_fingerprint:
        raise RuntimeError("validator mismatch: normalized-plan fingerprint changed")
    if not validation.get("valid"):
        raise RuntimeError("refusing to apply validator output marked invalid")
    if not validation.get("can_apply"):
        raise RuntimeError("refusing to apply validator output marked not apply-safe")
    gate = validation.get("apply_gate_status") or {}
    if gate.get("uncovered_stop_categories"):
        raise RuntimeError("refusing to apply while applicable stop categories remain uncovered")
    return normalized_plan


def check_source_fingerprints(normalized_plan: dict[str, Any]) -> list[str]:
    stale_sources: list[str] = []
    source_fingerprints = normalized_plan.get("source_fingerprints") or {}
    rule_files = normalized_plan.get("rule_files") or {}
    for key in ("publish_configuration", "readme"):
        path_text = str(rule_files.get(key) or "").strip()
        expected = str(source_fingerprints.get(key) or "").strip()
        if not path_text or not expected:
            continue
        current_text = Path(path_text).read_text(encoding="utf-8")
        if plan_tools.json_fingerprint(current_text) != expected:
            stale_sources.append(key)
    return stale_sources


def main() -> int:
    args = parse_args()
    validation = plan_tools.load_json(Path(args.validation).resolve())
    result_output = Path(args.result_output).resolve() if args.result_output else None
    payload: dict[str, Any] = {
        "dry_run": args.dry_run,
        "validation_source": "validator_normalized_plan",
        "mutation_type": "release_copy_apply",
        "mutations": [],
        "rollback_needed": False,
        "rolled_back_files": [],
        "deterministic_file_edit_count": 0,
        "issue_action_attempted": False,
        "raw_reread_count": 0,
        "compensatory_reread_detected": False,
    }

    try:
        normalized_plan = normalized_plan_from_validation(validation)
    except Exception as exc:
        return fail(payload, result_output, "validator_mismatch", str(exc))

    repo_root = Path(str(normalized_plan.get("repo_root") or ".")).resolve()
    payload["normalized_plan_fingerprint"] = str(validation.get("normalized_plan_fingerprint") or "")
    payload["validation_commands"] = list(normalized_plan.get("validation_commands") or [])
    draft_basis = normalized_plan.get("draft_basis") or {}
    payload["raw_reread_count"] = int(draft_basis.get("raw_reread_count", 0) or 0)
    payload["compensatory_reread_detected"] = bool(draft_basis.get("compensatory_reread_detected"))

    try:
        current_head = plan_tools.current_head_commit(repo_root)
    except Exception as exc:
        return fail(payload, result_output, "stale_context", str(exc))

    expected_head = str((normalized_plan.get("freshness_tuple") or {}).get("head_commit") or "").strip()
    if expected_head and current_head != expected_head:
        return fail(
            payload,
            result_output,
            "stale_context",
            "HEAD changed after validation; rerun collect -> lint -> validate before apply",
            current_head=current_head,
            expected_head=expected_head,
        )

    stale_sources = check_source_fingerprints(normalized_plan)
    if stale_sources:
        return fail(
            payload,
            result_output,
            "stale_context",
            "Release source files changed after validation; rerun validation before apply",
            stale_sources=stale_sources,
        )

    issue_action = normalized_plan.get("issue_action") or {}
    issue_mode = str(issue_action.get("mode") or "noop").strip()
    repo_slug = normalized_plan.get("repo_slug")
    validated_issue_snapshot = normalized_plan.get("validated_existing_issue_snapshot")

    if issue_mode != "noop":
        try:
            auth_status = issue_tools.run_command(["gh", "auth", "status"], cwd=repo_root)
        except Exception as exc:
            return fail(payload, result_output, "missing_auth", str(exc))
        if str(issue_action.get("project_mode") or "") == "require-scope" and "project" not in auth_status.lower():
            return fail(
                payload,
                result_output,
                "project_scope_required",
                "validated issue action requires project scope, but current gh auth status does not include it",
            )
        if issue_mode in {"reuse-existing", "sync-existing-body"} and isinstance(validated_issue_snapshot, dict):
            issue_number = int(validated_issue_snapshot.get("number") or 0)
            live_issue = plan_tools.fetch_issue_snapshot(repo_root, repo_slug, issue_number)
            live_snapshot = plan_tools.existing_issue_snapshot(live_issue)
            if live_snapshot != validated_issue_snapshot:
                return fail(
                    payload,
                    result_output,
                    "stale_issue_snapshot",
                    "release issue snapshot changed after validation; rerun validation before apply",
                )

    backups: dict[Path, str] = {}

    def remember_backup(path: Path) -> None:
        if path not in backups:
            backups[path] = path.read_text(encoding="utf-8")

    mutations: list[dict[str, Any]] = []
    try:
        publish_update = normalized_plan.get("publish_update") or {}
        if publish_update.get("mode") == "replace-fields":
            publish_path = Path(str((normalized_plan.get("rule_files") or {}).get("publish_configuration") or "")).resolve()
            remember_backup(publish_path)
            mutations.append(
                plan_tools.apply_publish_update(
                    publish_path,
                    dict(publish_update.get("fields") or {}),
                    args.dry_run,
                )
            )

        readme_update = normalized_plan.get("readme_update") or {}
        if readme_update.get("mode") == "replace-sections":
            readme_path = Path(str((normalized_plan.get("rule_files") or {}).get("readme") or "")).resolve()
            remember_backup(readme_path)
            mutations.append(
                plan_tools.apply_readme_update(
                    readme_path,
                    readme_update.get("intro_text"),
                    dict(readme_update.get("sections") or {}),
                    args.dry_run,
                )
            )

        if issue_mode != "noop":
            payload["issue_action_attempted"] = True
            body_markdown = str(issue_action.get("body_markdown") or "")
            temp_root = repo_root / ".codex" / "tmp" / "packet-workflow" / "draft-release-copy"
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                suffix=".md",
                dir=temp_root,
                delete=False,
            ) as temp_file:
                temp_file.write(body_markdown)
                body_path = Path(temp_file.name)
            try:
                issue_payload = issue_tools.execute_issue_action(
                    title=str(issue_action.get("title") or ""),
                    body_path=body_path,
                    repo_root=repo_root,
                    project_title=str(issue_action.get("project_title") or issue_tools.DEFAULT_PROJECT_TITLE),
                    project_mode=str(issue_action.get("project_mode") or "auto-add-first"),
                    local_release_helper_status=str(normalized_plan.get("local_release_helper_status") or "unknown"),
                    reuse_existing=issue_mode in {"reuse-existing", "sync-existing-body"},
                    sync_existing_body=issue_mode == "sync-existing-body",
                    dry_run=args.dry_run,
                    result_output=None,
                )
            finally:
                body_path.unlink(missing_ok=True)

            mutations.append(
                {
                    "kind": "issue_action",
                    "mode": issue_mode,
                    "url": issue_payload.get("created_issue_url"),
                    "issue_number": issue_payload.get("existing_issue_number"),
                    "changed": True,
                    "command": issue_payload.get("command"),
                }
            )
            payload["release_issue_url"] = issue_payload.get("created_issue_url")

    except Exception as exc:
        payload["deterministic_file_edit_count"] = sum(
            1 for item in mutations if item.get("kind") in {"publish_configuration", "readme"}
        )
        if not args.dry_run:
            for path, original in backups.items():
                path.write_text(original, encoding="utf-8")
            payload["rolled_back_files"] = [str(path) for path in backups]
            payload["rollback_needed"] = bool(backups)
        return fail(payload, result_output, "apply_failed", str(exc), mutations=mutations)

    payload["mutations"] = mutations
    payload["deterministic_file_edit_count"] = sum(
        1 for item in mutations if item.get("kind") in {"publish_configuration", "readme"}
    )
    payload["apply_succeeded"] = True
    payload["primary_artifact"] = payload.get("release_issue_url")
    if result_output is not None:
        plan_tools.write_json(result_output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
