#!/usr/bin/env python3
"""Apply a validated JSON plan of rewritten commit messages."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from reword_plan_contract import (
    branch_state,
    detect_operation,
    load_json,
    load_normalized_plan_envelope,
    recent_hashes,
    run_git,
)


def write_json_output(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def git_result(
    repo: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def runtime_warnings(repo_state: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if repo_state.get("upstream_branch"):
        warnings.append({"level": "warning", "code": "upstream_configured", "message": "branch has an upstream and rewritten history will require coordination"})
    if int(repo_state.get("ahead_count") or 0) > 0:
        warnings.append({"level": "warning", "code": "branch_ahead", "message": "branch is ahead of upstream; force-push is likely after rewrite"})
    if int(repo_state.get("behind_count") or 0) > 0:
        warnings.append({"level": "warning", "code": "branch_behind", "message": "branch is behind upstream; rewrite may diverge from the remote history"})
    if repo_state.get("force_push_likely"):
        warnings.append({"level": "warning", "code": "force_push_likely", "message": "history rewrite will likely require force-push-with-lease"})
    return warnings


def commit_lookup(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(commit.get("hash")): commit
        for commit in context.get("commits", [])
        if isinstance(commit, dict) and str(commit.get("hash") or "").strip()
    }


def build_operations(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    operations = []
    for action in actions:
        subject, _sep, body = str(action.get("new_message") or "").partition("\n")
        operations.append(
            {
                "index": int(action.get("index") or 0),
                "hash": str(action.get("hash") or ""),
                "operation": "rewrite_commit",
                "new_subject": subject,
                "has_body": bool(body.strip()),
            }
        )
    return operations


def cleanup_artifacts(repo_root: Path, temp_root: Path, worktree_path: Path) -> tuple[bool, list[str]]:
    leftover_paths: list[str] = []
    cleanup_succeeded = True
    remove = git_result(repo_root, ["worktree", "remove", "--force", str(worktree_path)])
    if remove.returncode != 0 and worktree_path.exists():
        cleanup_succeeded = False
        leftover_paths.append(str(worktree_path))
    shutil.rmtree(temp_root, ignore_errors=True)
    if temp_root.exists():
        cleanup_succeeded = False
        leftover_paths.append(str(temp_root))
    return cleanup_succeeded, leftover_paths


def build_base_payload(
    context: dict[str, Any],
    validated: dict[str, Any],
    repo_state: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    actions = list(validated["normalized_rewrite_actions"])
    return {
        "status": "dry-run" if dry_run else "pending",
        "dry_run": dry_run,
        "apply_succeeded": None if dry_run else False,
        "fingerprint_match": bool(validated.get("fingerprint_match")),
        "context_fingerprint": validated.get("context_fingerprint"),
        "message_set_fingerprint": validated.get("message_set_fingerprint"),
        "warnings": list(validated.get("warnings", [])) + runtime_warnings(repo_state),
        "counters": dict(validated.get("counters", {})),
        "normalized_rewrite_actions": actions,
        "operations": build_operations(actions),
        "mutation_type": "rewrite_history",
        "mutations": [] if dry_run else [{"kind": "rewrite_history", "branch": context.get("branch")}],
        "branch": context.get("branch"),
        "base_commit": context.get("base_commit"),
        "head_commit": context.get("head_commit"),
        "new_head": None,
        "commit_count": len(actions),
        "applied_commit_hashes": [],
        "stop_reasons": [],
        "rules_reliability": validated.get("rules_reliability"),
        "force_push_needed": bool(repo_state.get("force_push_likely")),
        "cleanup_attempted": False,
        "cleanup_succeeded": None,
        "leftover_paths": [],
        "ref_updated": False,
    }


def check_runtime_blockers(repo_root: Path, context: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    repo_state = branch_state(repo_root)
    stop_reasons: list[str] = []
    if bool(context.get("detached_head")) or not str(context.get("branch") or "").strip():
        stop_reasons.append("detached_head")
    operation = detect_operation(repo_root) or str(context.get("active_operation") or "").strip()
    if operation:
        stop_reasons.append("active_git_operation")
    if repo_state.get("working_tree_dirty"):
        stop_reasons.append("dirty_worktree")
    if not str(context.get("base_commit") or "").strip():
        stop_reasons.append("root_rewrite_unsupported")
    if any(len(commit.get("parent_hashes", []) or []) > 1 for commit in context.get("commits", []) if isinstance(commit, dict)):
        stop_reasons.append("merge_commit_in_scope")

    expected_hashes = [str(action["hash"]) for action in actions]
    current_hashes = recent_hashes(repo_root, len(expected_hashes))
    if current_hashes != expected_hashes:
        stop_reasons.append("recent_hash_drift")
    current_head = run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    if current_head != str(context.get("head_commit") or "").strip():
        stop_reasons.append("head_commit_drift")
    return sorted(dict.fromkeys(stop_reasons)), repo_state


def rewrite_commits(
    repo_root: Path,
    context: dict[str, Any],
    actions: list[dict[str, Any]],
) -> tuple[bool, str | None, list[str], bool, bool, list[str], str | None]:
    branch = str(context.get("branch") or "").strip()
    base_commit = str(context.get("base_commit") or "").strip()
    head_commit = str(context.get("head_commit") or "").strip()
    commits_by_hash = commit_lookup(context)

    temp_root = Path(tempfile.mkdtemp(prefix="reword-recent-commits-"))
    worktree_path = temp_root / "worktree"
    message_path = temp_root / "message.txt"
    new_hashes: list[str] = []
    new_head: str | None = None
    replay_error: str | None = None
    ref_updated = False

    try:
        run_git(repo_root, ["worktree", "add", "--detach", str(worktree_path), base_commit])
        for action in actions:
            commit_hash = str(action["hash"])
            source_commit = commits_by_hash[commit_hash]
            cherry_pick = git_result(worktree_path, ["cherry-pick", "--no-commit", commit_hash])
            if cherry_pick.returncode != 0:
                replay_error = (cherry_pick.stderr or cherry_pick.stdout).strip() or "cherry-pick failed"
                return False, None, new_hashes, ref_updated, *cleanup_artifacts(repo_root, temp_root, worktree_path), replay_error

            message = str(action["new_message"]).strip("\n") + "\n"
            message_path.write_text(message, encoding="utf-8")
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = str(source_commit.get("author_name", ""))
            env["GIT_AUTHOR_EMAIL"] = str(source_commit.get("author_email", ""))
            env["GIT_AUTHOR_DATE"] = str(source_commit.get("author_date", ""))
            commit_result = git_result(
                worktree_path,
                ["commit", "--no-gpg-sign", "-F", str(message_path)],
                env=env,
            )
            if commit_result.returncode != 0:
                replay_error = (commit_result.stderr or commit_result.stdout).strip() or "commit failed"
                return False, None, new_hashes, ref_updated, *cleanup_artifacts(repo_root, temp_root, worktree_path), replay_error
            new_hashes.append(run_git(worktree_path, ["rev-parse", "HEAD"]).strip())

        new_head = run_git(worktree_path, ["rev-parse", "HEAD"]).strip()
        run_git(repo_root, ["update-ref", f"refs/heads/{branch}", new_head, head_commit])
        ref_updated = True
        cleanup_succeeded, leftover_paths = cleanup_artifacts(repo_root, temp_root, worktree_path)
        return True, new_head, new_hashes, ref_updated, cleanup_succeeded, leftover_paths, None
    except Exception as exc:
        replay_error = str(exc)
        cleanup_succeeded, leftover_paths = cleanup_artifacts(repo_root, temp_root, worktree_path)
        return False, new_head, new_hashes, ref_updated, cleanup_succeeded, leftover_paths, replay_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a validated reword plan.")
    parser.add_argument("--context", type=Path, required=True, help="Path to collected plan JSON from collect_recent_commits.py")
    parser.add_argument("--plan", type=Path, required=True, help="Path to validated envelope from validate_reword_plan.py")
    parser.add_argument("--dry-run", action="store_true", help="Validate runtime safety and print planned operations without mutating refs")
    parser.add_argument("--result-output", type=Path, help="Optional path to write the JSON result payload.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload: dict[str, Any] | None = None
    exit_code = 1

    try:
        context = load_json(args.context)
        plan = load_json(args.plan)
        repo_root = Path(str(context.get("repo_root") or ".")).resolve()
        validated = load_normalized_plan_envelope(context, plan)
        stop_reasons, repo_state = check_runtime_blockers(
            repo_root,
            context,
            list(validated["normalized_rewrite_actions"]),
        )
        payload = build_base_payload(context, validated, repo_state, dry_run=args.dry_run)
        payload["stop_reasons"] = stop_reasons
        payload["counters"]["commits_rewritten"] = 0

        if stop_reasons:
            payload["status"] = "failed"
            payload["apply_succeeded"] = False if not args.dry_run else None
            write_json_output(args.result_output, payload)
            print(json.dumps(payload, indent=2, ensure_ascii=True))
            return 1

        if args.dry_run:
            payload["status"] = "dry-run"
            payload["apply_succeeded"] = None
            write_json_output(args.result_output, payload)
            print(json.dumps(payload, indent=2, ensure_ascii=True))
            return 0

        ok, new_head, new_hashes, ref_updated, cleanup_succeeded, leftover_paths, replay_error = rewrite_commits(
            repo_root,
            context,
            list(validated["normalized_rewrite_actions"]),
        )
        payload["cleanup_attempted"] = True
        payload["cleanup_succeeded"] = cleanup_succeeded
        payload["leftover_paths"] = leftover_paths
        payload["ref_updated"] = ref_updated

        if ok:
            payload["status"] = "ok"
            payload["apply_succeeded"] = True
            payload["new_head"] = new_head
            payload["applied_commit_hashes"] = new_hashes
            payload["counters"]["commits_rewritten"] = len(new_hashes)
            exit_code = 0
        else:
            payload["status"] = "failed"
            payload["apply_succeeded"] = False
            payload["stop_reasons"] = ["replay_failed"]
            payload["error_message"] = replay_error
            payload["applied_commit_hashes"] = new_hashes
            payload["counters"]["commits_rewritten"] = len(new_hashes)

        write_json_output(args.result_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return exit_code
    except Exception as exc:
        if payload is None:
            payload = {
                "status": "failed",
                "dry_run": bool(args.dry_run),
                "apply_succeeded": False if not args.dry_run else None,
                "stop_reasons": ["replay_failed"],
                "error_message": str(exc),
            }
        write_json_output(args.result_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
