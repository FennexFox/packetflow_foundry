#!/usr/bin/env python3
"""Apply a validator-approved commit plan to the current working tree."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from collect_worktree_context import detect_operation, parse_patch_hunks, raw_diff_against_head
from validate_commit_plan import (
    command_feasibility_issues,
    json_fingerprint,
    load_json,
    normalize_body,
    string_list,
    validate_plan_against_worktree,
)


class ApplyHardStop(RuntimeError):
    def __init__(self, category: str, message: str, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.category = category
        self.payload = payload


def run_git(
    repo: Path,
    args: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result


def build_commit_message(commit: dict[str, Any]) -> str:
    message_type = str(commit.get("type", "")).strip()
    scope = str(commit.get("scope", "")).strip()
    subject = str(commit.get("subject", "")).strip()
    first_line = f"{message_type}({scope}): {subject}" if scope else f"{message_type}: {subject}"
    body_lines = normalize_body(commit.get("body"))
    if not body_lines:
        return first_line + "\n"
    return first_line + "\n\n" + "\n".join(body_lines) + "\n"


def build_hunk_lookup(worktree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in worktree.get("files", []):
        for hunk in entry.get("hunks", []):
            payload = dict(hunk)
            payload["path"] = entry["path"]
            lookup[str(hunk["hunk_id"])] = payload
    return lookup


def diff_header_text(patch_text: str, path: str) -> str:
    header_lines: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("@@ "):
            break
        header_lines.append(line)
    if header_lines:
        return "\n".join(header_lines) + "\n"
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"


def build_patch_for_current_hunks(path: str, patch_text: str, hunks: list[dict[str, Any]]) -> str:
    ordered_hunks = sorted(hunks, key=lambda item: (int(item["old_start"]), int(item["new_start"])))
    body = "".join(str(hunk["raw_patch"]) for hunk in ordered_hunks)
    return diff_header_text(patch_text, path) + body


def build_apply_status(
    *,
    status: str,
    stop_category: str | None,
    message: str,
    rollback_performed: bool,
    rollback_status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "stop_category": stop_category,
        "message": message,
        "rollback_performed": rollback_performed,
        "rollback_status": rollback_status,
    }


def build_apply_payload(
    *,
    dry_run: bool,
    validation_source: str,
    normalized_plan_fingerprint: str | None,
    validation: dict[str, Any] | None,
    commands: list[str],
    commits: list[dict[str, Any]],
    created_hashes: list[str],
    final_head: str | None,
    apply_succeeded: bool | None,
    applied: bool,
    stop_reasons: list[str],
    apply_status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "validation_source": validation_source,
        "normalized_plan_fingerprint": normalized_plan_fingerprint,
        "validation": validation,
        "commands": commands,
        "commits": commits,
        "created_hashes": created_hashes,
        "final_head": final_head,
        "apply_succeeded": apply_succeeded,
        "ok": apply_succeeded is not False,
        "applied": applied,
        "rollback_needed": bool(apply_status.get("rollback_performed")),
        "stop_reasons": stop_reasons,
        "apply_status": apply_status,
    }


def make_hard_stop(
    category: str,
    message: str,
    *,
    dry_run: bool,
    normalized_plan_fingerprint: str | None = None,
    validation: dict[str, Any] | None = None,
    commands: list[str] | None = None,
    commits: list[dict[str, Any]] | None = None,
    created_hashes: list[str] | None = None,
    rollback_performed: bool = False,
    rollback_status: str = "not_needed",
) -> ApplyHardStop:
    payload = build_apply_payload(
        dry_run=dry_run,
        validation_source="validator_normalized_plan",
        normalized_plan_fingerprint=normalized_plan_fingerprint,
        validation=validation,
        commands=list(commands or []),
        commits=list(commits or []),
        created_hashes=list(created_hashes or []),
        final_head=None,
        apply_succeeded=False,
        applied=False,
        stop_reasons=[message],
        apply_status=build_apply_status(
            status="hard_stop",
            stop_category=category,
            message=message,
            rollback_performed=rollback_performed,
            rollback_status=rollback_status,
        ),
    )
    return ApplyHardStop(category, message, payload)


def current_hunk_match(path: str, original_hunk: dict[str, Any], current_hunks: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [
        hunk
        for hunk in current_hunks
        if str(hunk.get("removed_digest")) == str(original_hunk.get("removed_digest"))
        and str(hunk.get("added_digest")) == str(original_hunk.get("added_digest"))
    ]
    if len(matches) != 1:
        if not matches:
            raise make_hard_stop(
                "ambiguous_split_rematch",
                f"hunk `{original_hunk['hunk_id']}` for `{path}` is missing from the current diff; apply will not reinterpret the split",
                dry_run=False,
            )
        raise make_hard_stop(
            "ambiguous_split_rematch",
            f"hunk `{original_hunk['hunk_id']}` for `{path}` is ambiguous in the current diff; apply will not reinterpret the split",
            dry_run=False,
        )
    return matches[0]


def ensure_targeted_checks_feasible(repo_root: Path, commands: list[str], *, dry_run: bool) -> None:
    issues = command_feasibility_issues(repo_root, commands)
    if not issues:
        return
    first_issue = issues[0]
    raise make_hard_stop(
        "targeted_check_unavailable",
        f"targeted check `{first_issue['command']}` is not feasible locally: {first_issue['detail']}.",
        dry_run=dry_run,
        commands=commands,
    )


def run_targeted_checks(repo_root: Path, commands: list[str]) -> None:
    ensure_targeted_checks_feasible(repo_root, commands, dry_run=False)
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "targeted check failed"
            raise make_hard_stop(
                "targeted_check_failed",
                f"targeted check failed: {command}: {detail}",
                dry_run=False,
                commands=commands,
            )


def apply_cached_patch(repo_root: Path, patch_text: str) -> None:
    temp_root = repo_root / ".codex" / "tmp" / "packet-workflow" / "git-split-and-commit"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        suffix=".patch",
        dir=temp_root,
        delete=False,
    ) as handle:
        patch_path = Path(handle.name)
        handle.write(patch_text)
    try:
        run_git(repo_root, ["apply", "--cached", "--unidiff-zero", "--recount", str(patch_path)])
    finally:
        patch_path.unlink(missing_ok=True)


def reset_index(repo_root: Path, pathspecs: list[str]) -> None:
    if pathspecs:
        run_git(repo_root, ["reset", "HEAD", "--", *pathspecs])
    else:
        run_git(repo_root, ["reset", "--mixed", "HEAD"])


def rollback_created_commits(repo_root: Path, original_head: str) -> None:
    run_git(repo_root, ["reset", "--mixed", original_head])


def stage_commit(repo_root: Path, commit: dict[str, Any], hunk_lookup: dict[str, dict[str, Any]]) -> None:
    for path in string_list(commit.get("whole_file_paths")) + string_list(commit.get("supporting_paths")) + string_list(commit.get("untracked_paths")):
        run_git(repo_root, ["add", "--all", "--", path])

    selected_hunk_ids = string_list(commit.get("selected_hunk_ids"))
    if not selected_hunk_ids:
        return

    split_paths = set(string_list(commit.get("split_paths")))
    hunks_by_path: dict[str, list[dict[str, Any]]] = {}
    for hunk_id in selected_hunk_ids:
        original_hunk = hunk_lookup.get(hunk_id)
        if original_hunk is None:
            raise make_hard_stop(
                "partial_split_unsupported",
                f"plan references unknown hunk id `{hunk_id}` during apply",
                dry_run=False,
            )
        path = str(original_hunk["path"])
        if path not in split_paths:
            raise make_hard_stop(
                "partial_split_unsupported",
                f"hunk `{hunk_id}` belongs to `{path}` which is not listed in `split_paths`",
                dry_run=False,
            )
        hunks_by_path.setdefault(path, []).append(original_hunk)

    for path, original_hunks in hunks_by_path.items():
        current_patch = raw_diff_against_head(repo_root, path)
        current_hunks = parse_patch_hunks(path, current_patch)
        selected_current_hunks = [current_hunk_match(path, original_hunk, current_hunks) for original_hunk in original_hunks]
        apply_cached_patch(repo_root, build_patch_for_current_hunks(path, current_patch, selected_current_hunks))


def created_commit_hash(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "HEAD"]).stdout.strip()


def first_validation_stop_category(validation_payload: dict[str, Any], fallback: str) -> str:
    apply_gate_status = validation_payload.get("apply_gate_status") or {}
    stop_categories = string_list(apply_gate_status.get("current_stop_categories"))
    if stop_categories:
        return stop_categories[0]
    return fallback


def load_validated_plan(validation_payload: dict[str, Any], *, dry_run: bool) -> tuple[dict[str, Any], str]:
    normalized_plan = validation_payload.get("normalized_plan")
    if not isinstance(normalized_plan, dict):
        raise make_hard_stop(
            "validator_mismatch",
            "validator output is missing `normalized_plan`",
            dry_run=dry_run,
            validation=validation_payload,
        )
    normalized_plan_fingerprint = str(validation_payload.get("normalized_plan_fingerprint", "")).strip()
    if not normalized_plan_fingerprint:
        raise make_hard_stop(
            "validator_mismatch",
            "validator output is missing `normalized_plan_fingerprint`",
            dry_run=dry_run,
            validation=validation_payload,
        )
    if json_fingerprint(normalized_plan) != normalized_plan_fingerprint:
        raise make_hard_stop(
            "validator_mismatch",
            "validator output normalized-plan fingerprint does not match the normalized plan",
            dry_run=dry_run,
            validation=validation_payload,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
        )
    if not validation_payload.get("valid"):
        raise make_hard_stop(
            first_validation_stop_category(validation_payload, "validator_mismatch"),
            "refusing to apply validator output marked invalid",
            dry_run=dry_run,
            validation=validation_payload,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
        )
    if not validation_payload.get("can_apply"):
        raise make_hard_stop(
            first_validation_stop_category(validation_payload, "validator_mismatch"),
            "refusing to apply validator output marked not apply-safe",
            dry_run=dry_run,
            validation=validation_payload,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
        )
    apply_gate_status = validation_payload.get("apply_gate_status") or {}
    if string_list(apply_gate_status.get("uncovered_stop_categories")):
        raise make_hard_stop(
            "validator_mismatch",
            "refusing to apply while applicable stop categories remain uncovered",
            dry_run=dry_run,
            validation=validation_payload,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
        )
    return normalized_plan, normalized_plan_fingerprint


def handle_apply_failure(
    failure: ApplyHardStop,
    *,
    repo_root: Path,
    original_head: str,
    pathspecs: list[str],
    created_hashes: list[str],
    dry_run: bool,
    normalized_plan_fingerprint: str,
    validation: dict[str, Any],
    commands: list[str],
    commits: list[dict[str, Any]],
) -> None:
    if created_hashes:
        try:
            rollback_created_commits(repo_root, original_head)
        except Exception as rollback_exc:
            raise make_hard_stop(
                "rollback_failed",
                f"{failure}. Rollback to `{original_head}` failed: {rollback_exc}",
                dry_run=dry_run,
                normalized_plan_fingerprint=normalized_plan_fingerprint,
                validation=validation,
                commands=commands,
                commits=commits,
                created_hashes=created_hashes,
                rollback_performed=True,
                rollback_status="failed",
            ) from rollback_exc
        raise make_hard_stop(
            failure.category,
            str(failure),
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=validation,
            commands=commands,
            commits=commits,
            created_hashes=created_hashes,
            rollback_performed=True,
            rollback_status="success",
        ) from failure

    try:
        reset_index(repo_root, pathspecs)
    except Exception as cleanup_exc:
        raise make_hard_stop(
            "rollback_failed",
            f"{failure}. Index cleanup failed before any commit was created: {cleanup_exc}",
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=validation,
            commands=commands,
            commits=commits,
            created_hashes=created_hashes,
            rollback_performed=False,
            rollback_status="failed",
        ) from cleanup_exc
    raise failure


def apply_validated_plan(worktree: dict[str, Any], validation_payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    repo_root = Path(str(worktree.get("repo_root", "")))
    normalized_plan, normalized_plan_fingerprint = load_validated_plan(validation_payload, dry_run=dry_run)
    revalidated = validate_plan_against_worktree(worktree, normalized_plan)
    if not revalidated.get("valid"):
        raise make_hard_stop(
            first_validation_stop_category(revalidated, "stale_context"),
            "commit plan validation failed after revalidation",
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
        )
    if not revalidated.get("can_apply"):
        raise make_hard_stop(
            first_validation_stop_category(revalidated, "validator_mismatch"),
            "commit plan is no longer apply-safe after revalidation",
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
        )
    if str(revalidated.get("normalized_plan_fingerprint", "")).strip() != normalized_plan_fingerprint:
        raise make_hard_stop(
            "validator_mismatch",
            "validator mismatch: revalidated normalized plan fingerprint changed",
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
        )

    commands = list(revalidated.get("deduped_validation_commands", []))
    commit_summaries = [
        {
            "commit_index": int(commit["commit_index"]),
            "subject": build_commit_message(commit).splitlines()[0],
            "whole_file_paths": string_list(commit.get("whole_file_paths")),
            "supporting_paths": string_list(commit.get("supporting_paths")),
            "untracked_paths": string_list(commit.get("untracked_paths")),
            "split_paths": string_list(commit.get("split_paths")),
            "targeted_checks": string_list(commit.get("targeted_checks")),
        }
        for commit in normalized_plan.get("commits", [])
        if isinstance(commit, dict)
    ]

    active_operation = detect_operation(repo_root)
    if active_operation:
        raise make_hard_stop(
            "active_git_operation",
            f"git operation already in progress: {active_operation}",
            dry_run=dry_run,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
            commands=commands,
            commits=commit_summaries,
        )

    ensure_targeted_checks_feasible(repo_root, commands, dry_run=dry_run)
    original_head = run_git(repo_root, ["rev-parse", "HEAD"]).stdout.strip()

    if dry_run:
        return build_apply_payload(
            dry_run=True,
            validation_source="validator_normalized_plan",
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
            commands=commands,
            commits=commit_summaries,
            created_hashes=[],
            final_head=original_head,
            apply_succeeded=True,
            applied=False,
            stop_reasons=[],
            apply_status=build_apply_status(
                status="dry_run",
                stop_category=None,
                message="Validated normalized plan is ready for apply --dry-run only.",
                rollback_performed=False,
                rollback_status="not_needed",
            ),
        )

    pathspecs = list(worktree.get("pathspecs", []))
    try:
        run_targeted_checks(repo_root, commands)
        reset_index(repo_root, pathspecs)
        hunk_lookup = build_hunk_lookup(worktree)
    except ApplyHardStop:
        raise
    except Exception as exc:
        raise make_hard_stop(
            "commit_creation_failed",
            str(exc),
            dry_run=False,
            normalized_plan_fingerprint=normalized_plan_fingerprint,
            validation=revalidated,
            commands=commands,
            commits=commit_summaries,
        ) from exc
    created_hashes: list[str] = []

    for commit in sorted(normalized_plan.get("commits", []), key=lambda item: int(item["commit_index"])):
        try:
            stage_commit(repo_root, commit, hunk_lookup)
            cached_diff = run_git(repo_root, ["diff", "--cached", "--name-only"], check=False).stdout.strip()
            if not cached_diff:
                raise make_hard_stop(
                    "commit_creation_failed",
                    f"commit {commit['commit_index']} staged no changes",
                    dry_run=False,
                    normalized_plan_fingerprint=normalized_plan_fingerprint,
                    validation=revalidated,
                    commands=commands,
                    commits=commit_summaries,
                    created_hashes=created_hashes,
                )
            message = build_commit_message(commit)
            temp_root = repo_root / ".codex" / "tmp" / "packet-workflow" / "git-split-and-commit"
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=temp_root,
                delete=False,
            ) as handle:
                message_path = Path(handle.name)
                handle.write(message)
            try:
                run_git(repo_root, ["commit", "--no-gpg-sign", "-F", str(message_path)])
            finally:
                message_path.unlink(missing_ok=True)
            created_hashes.append(created_commit_hash(repo_root))
        except ApplyHardStop as failure:
            handle_apply_failure(
                failure,
                repo_root=repo_root,
                original_head=original_head,
                pathspecs=pathspecs,
                created_hashes=created_hashes,
                dry_run=False,
                normalized_plan_fingerprint=normalized_plan_fingerprint,
                validation=revalidated,
                commands=commands,
                commits=commit_summaries,
            )
        except Exception as exc:
            handle_apply_failure(
                make_hard_stop(
                    "commit_creation_failed",
                    str(exc),
                    dry_run=False,
                    normalized_plan_fingerprint=normalized_plan_fingerprint,
                    validation=revalidated,
                    commands=commands,
                    commits=commit_summaries,
                    created_hashes=created_hashes,
                ),
                repo_root=repo_root,
                original_head=original_head,
                pathspecs=pathspecs,
                created_hashes=created_hashes,
                dry_run=False,
                normalized_plan_fingerprint=normalized_plan_fingerprint,
                validation=revalidated,
                commands=commands,
                commits=commit_summaries,
            )

    final_head = created_hashes[-1] if created_hashes else original_head
    return build_apply_payload(
        dry_run=False,
        validation_source="validator_normalized_plan",
        normalized_plan_fingerprint=normalized_plan_fingerprint,
        validation=revalidated,
        commands=commands,
        commits=commit_summaries,
        created_hashes=created_hashes,
        final_head=final_head,
        apply_succeeded=True,
        applied=True,
        stop_reasons=[],
        apply_status=build_apply_status(
            status="applied",
            stop_category=None,
            message=f"Applied {len(created_hashes)} commit(s) from the validator-approved normalized plan.",
            rollback_performed=False,
            rollback_status="not_needed",
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a commit plan to the current working tree.")
    parser.add_argument("--worktree", type=Path, required=True, help="Path to worktree JSON from collect_worktree_context.py")
    parser.add_argument("--validation", type=Path, required=True, help="Path to validator output JSON from validate_commit_plan.py")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating git state")
    parser.add_argument("--result-output", type=Path, help="Optional path to write the JSON result payload.")
    return parser.parse_args()


def write_payload(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        worktree = load_json(args.worktree)
        validation_payload = load_json(args.validation)
        payload = apply_validated_plan(worktree, validation_payload, args.dry_run)
        exit_code = 0
    except ApplyHardStop as exc:  # pragma: no cover - command-line error path
        payload = exc.payload
        exit_code = 1
    except Exception as exc:  # pragma: no cover - command-line error path
        payload = build_apply_payload(
            dry_run=bool(args.dry_run),
            validation_source="validator_normalized_plan",
            normalized_plan_fingerprint=None,
            validation=None,
            commands=[],
            commits=[],
            created_hashes=[],
            final_head=None,
            apply_succeeded=False,
            applied=False,
            stop_reasons=[str(exc)],
            apply_status=build_apply_status(
                status="hard_stop",
                stop_category="validator_mismatch",
                message=str(exc),
                rollback_performed=False,
                rollback_status="not_needed",
            ),
        )
        exit_code = 1

    write_payload(args.result_output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
