#!/usr/bin/env python3
"""Express driver for rewriting the current HEAD commit message."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_NAMESPACE = Path(".codex") / "tmp" / "packet-workflow" / "reword-head-commit"
RULES_FILE = "rules.json"
CONTEXT_FILE = "context.json"
VALIDATION_FILE = "validation.json"
APPLY_RESULT_FILE = "apply-result.json"
EVAL_LOG_FILE = "eval-log.json"
MESSAGE_COPY_FILE = "message.txt"


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def shared_reword_scripts_dir() -> Path:
    candidate = skill_root().parent / "reword-recent-commits" / "scripts"
    if candidate.is_dir():
        return candidate
    raise RuntimeError(f"missing sibling reword-recent-commits scripts: {candidate}")


SHARED_REWORD_SCRIPTS_DIR = shared_reword_scripts_dir()
if str(SHARED_REWORD_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_REWORD_SCRIPTS_DIR))

from apply_reword_plan import check_runtime_blockers  # type: ignore  # noqa: E402
from collect_commit_rules import build_rules  # type: ignore  # noqa: E402
from collect_recent_commits import build_plan  # type: ignore  # noqa: E402
from reword_plan_contract import (  # type: ignore  # noqa: E402
    branch_state,
    detect_operation,
    load_normalized_plan_envelope,
    run_git,
    validate_reword_plan_payload,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime | None = None) -> str:
    return (value or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_message(args: argparse.Namespace, repo_root: Path) -> str:
    if args.message is not None:
        return str(args.message).strip("\n")
    if args.message_file is None:
        raise RuntimeError("either --message or --message-file is required")
    message_path = args.message_file.expanduser()
    if not message_path.is_absolute():
        message_path = repo_root / message_path
    message_path = message_path.resolve()
    repo_codex_tmp = (repo_root / ".codex" / "tmp").resolve()
    if message_path.is_relative_to(repo_root) and not message_path.is_relative_to(repo_codex_tmp):
        raise RuntimeError("message-file paths inside the repo must live under .codex/tmp/")
    return message_path.read_text(encoding="utf-8-sig").strip("\n")


def runtime_namespace_root(repo_root: Path) -> Path:
    return repo_root / ARTIFACT_NAMESPACE


def create_artifact_root(repo_root: Path) -> Path:
    root = runtime_namespace_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"{isoformat_utc().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    artifact_root = root / run_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    return artifact_root


def build_raw_plan(context: dict[str, Any], message: str) -> dict[str, Any]:
    commits = context.get("commits") or []
    if not isinstance(commits, list) or len(commits) != 1 or not isinstance(commits[0], dict):
        raise RuntimeError("expected exactly one collected HEAD commit")
    commit = commits[0]
    return {
        "commits": [
            {
                "index": int(commit.get("index") or 1),
                "hash": str(commit.get("hash") or ""),
                "new_message": message,
            }
        ]
    }


def issue(level: str, code: str, message: str) -> dict[str, Any]:
    return {"level": level, "code": code, "message": message}


def finalize_validation(
    validation: dict[str, Any],
    *,
    repo_root: Path,
    rules: dict[str, Any],
    repo_state: dict[str, Any],
) -> dict[str, Any]:
    errors = list(validation.get("errors", []))
    warnings = list(validation.get("warnings", []))
    stop_reasons = list(validation.get("stop_reasons", []))
    reliability = str(rules.get("rules_reliability") or validation.get("rules_reliability") or "")
    if reliability != "explicit":
        errors.append(
            issue(
                "error",
                "explicit_rules_required",
                "reword-head-commit requires explicit repo commit-message guidance",
            )
        )
        stop_reasons.append("explicit_rules_required")

    validation["errors"] = errors
    validation["warnings"] = warnings
    validation["stop_reasons"] = sorted(dict.fromkeys(stop_reasons))
    validation["rules_reliability"] = reliability
    counters = dict(validation.get("counters", {}))
    counters["error_count"] = len(errors)
    counters["warning_count"] = len(warnings)
    counters["force_push_needed"] = bool(repo_state.get("force_push_likely"))
    validation["counters"] = counters
    validation["valid"] = not errors
    validation["amend_allowed"] = not errors
    validation["force_push_likely"] = bool(repo_state.get("force_push_likely"))
    validation["repo_root"] = str(repo_root)
    return validation


def validation_result(
    repo_root: Path,
    message: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    rules = build_rules(repo_root)
    context = build_plan(repo_root, 1, rules)
    repo_state = branch_state(repo_root)
    raw_plan = build_raw_plan(context, message)
    validation = validate_reword_plan_payload(
        context,
        rules,
        raw_plan,
        repo_state=repo_state,
        active_operation=detect_operation(repo_root),
    )
    return rules, context, repo_state, finalize_validation(
        validation,
        repo_root=repo_root,
        rules=rules,
        repo_state=repo_state,
    )


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for issue_payload in issues:
        key = (
            str(issue_payload.get("level") or ""),
            str(issue_payload.get("code") or ""),
            str(issue_payload.get("message") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(issue_payload)
    return result


def base_apply_result(
    *,
    context: dict[str, Any],
    validation: dict[str, Any],
    repo_state: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    action = next(iter(validation.get("normalized_rewrite_actions", [])), None)
    new_message = str(action.get("new_message") or "") if isinstance(action, dict) else ""
    subject, _sep, body = new_message.partition("\n")
    return {
        "status": "dry-run" if dry_run else "pending",
        "dry_run": dry_run,
        "apply_requested": not dry_run,
        "apply_attempted": False,
        "amend_succeeded": None if dry_run else False,
        "validation_boundary_enforced": True,
        "branch": context.get("branch"),
        "head_commit": context.get("head_commit"),
        "new_head": None,
        "force_push_likely": bool(repo_state.get("force_push_likely")),
        "warnings": dedupe_issues(list(validation.get("warnings", []))),
        "stop_reasons": [],
        "context_fingerprint": validation.get("context_fingerprint"),
        "message_set_fingerprint": validation.get("message_set_fingerprint"),
        "rules_reliability": validation.get("rules_reliability"),
        "operation": {
            "kind": "amend_head_commit",
            "new_subject": subject or None,
            "has_body": bool(body.strip()),
        },
        "mutation_type": "none",
        "ref_updated": False,
        "tree_unchanged": None,
        "error_message": None,
    }


def dry_run_result(
    repo_root: Path,
    context: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    normalized = load_normalized_plan_envelope(context, validation)
    stop_reasons, repo_state = check_runtime_blockers(
        repo_root,
        context,
        normalized["normalized_rewrite_actions"],
    )
    result = base_apply_result(
        context=context,
        validation=validation,
        repo_state=repo_state,
        dry_run=True,
    )
    if stop_reasons:
        result["status"] = "blocked"
        result["amend_succeeded"] = False
        result["stop_reasons"] = stop_reasons
    return result


def invalid_result(
    *,
    context: dict[str, Any],
    validation: dict[str, Any],
    repo_state: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    result = base_apply_result(
        context=context,
        validation=validation,
        repo_state=repo_state,
        dry_run=dry_run,
    )
    result["status"] = "blocked"
    result["amend_succeeded"] = False
    result["stop_reasons"] = list(validation.get("stop_reasons", []))
    return result


def git_result(
    repo_root: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def apply_message(
    repo_root: Path,
    artifact_root: Path,
    context: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    normalized = load_normalized_plan_envelope(context, validation)
    stop_reasons, repo_state = check_runtime_blockers(
        repo_root,
        context,
        normalized["normalized_rewrite_actions"],
    )
    result = base_apply_result(
        context=context,
        validation=validation,
        repo_state=repo_state,
        dry_run=False,
    )
    if stop_reasons:
        result["status"] = "blocked"
        result["stop_reasons"] = stop_reasons
        return result

    action = normalized["normalized_rewrite_actions"][0]
    commit = list(context.get("commits", []))[0]
    old_head = run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    old_tree = run_git(repo_root, ["show", "-s", "--format=%T", old_head]).strip()
    committer_name = run_git(repo_root, ["show", "-s", "--format=%cn", old_head]).strip()
    committer_email = run_git(repo_root, ["show", "-s", "--format=%ce", old_head]).strip()
    committer_date = run_git(repo_root, ["show", "-s", "--format=%cI", old_head]).strip()
    message_path = artifact_root / MESSAGE_COPY_FILE
    message_path.write_text(str(action.get("new_message") or "").strip("\n") + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = str(commit.get("author_name") or "")
    env["GIT_AUTHOR_EMAIL"] = str(commit.get("author_email") or "")
    env["GIT_AUTHOR_DATE"] = str(commit.get("author_date") or "")
    env["GIT_COMMITTER_NAME"] = committer_name
    env["GIT_COMMITTER_EMAIL"] = committer_email
    env["GIT_COMMITTER_DATE"] = committer_date
    result["apply_attempted"] = True
    result["mutation_type"] = "amend_head_commit"
    amend = git_result(
        repo_root,
        ["commit", "--amend", "--no-gpg-sign", "--allow-empty", "-F", str(message_path)],
        env=env,
    )
    if amend.returncode != 0:
        result["status"] = "failed"
        result["error_message"] = amend.stderr.strip() or amend.stdout.strip() or "git commit --amend failed"
        return result

    new_head = run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    new_tree = run_git(repo_root, ["show", "-s", "--format=%T", new_head]).strip()
    result["status"] = "ok"
    result["amend_succeeded"] = True
    result["new_head"] = new_head
    result["ref_updated"] = old_head != new_head
    result["tree_unchanged"] = old_tree == new_tree
    return result


def evaluation_log(
    *,
    run_id: str,
    context: dict[str, Any],
    validation: dict[str, Any],
    apply_result: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp_utc": isoformat_utc(),
        "skill": {
            "name": "reword-head-commit",
            "family": "git-history-express",
            "archetype": "validate-and-amend",
            "skill_version": "unversioned",
        },
        "repo": {
            "repo_root": str(context.get("repo_root") or ""),
            "branch": context.get("branch"),
            "head_sha": context.get("head_commit"),
            "base_ref": context.get("base_commit"),
        },
        "quality": {
            "result_status": apply_result.get("status"),
            "first_pass_usable": bool(validation.get("valid")),
            "human_post_edit_required": False,
            "human_post_edit_severity": "none",
        },
        "safety": {
            "validation_run": True,
            "validation_passed": bool(validation.get("valid")),
            "apply_attempted": bool(apply_result.get("apply_attempted")),
            "apply_succeeded": bool(apply_result.get("amend_succeeded")),
            "mutation_type": str(apply_result.get("mutation_type") or "none"),
            "fingerprint_match": bool(validation.get("fingerprint_match")),
            "force_push_likely": bool(apply_result.get("force_push_likely")),
        },
        "outputs": {
            "artifact_root": str(artifact_root),
            "mutations": (
                []
                if not bool(apply_result.get("amend_succeeded"))
                else [{"kind": "amend_head_commit", "branch": context.get("branch")}]
            ),
        },
        "skill_specific": {
            "schema_name": "reword-head-commit",
            "schema_version": "1.0",
            "data": {
                "head_commit": context.get("head_commit"),
                "new_head": apply_result.get("new_head"),
                "rules_reliability": validation.get("rules_reliability"),
                "force_push_likely": bool(apply_result.get("force_push_likely")),
                "stop_reasons": list(apply_result.get("stop_reasons", [])),
            },
        },
    }


def summary_payload(
    *,
    artifact_root: Path,
    validation_path: Path,
    apply_result_path: Path,
    eval_log_path: Path,
    validation: dict[str, Any],
    apply_result: dict[str, Any],
) -> dict[str, Any]:
    status = "invalid" if not bool(validation.get("valid")) else str(apply_result.get("status") or "failed")
    next_action = "fix_message"
    if status == "dry-run":
        next_action = "apply"
    elif status == "ok":
        next_action = "done"
    elif status == "blocked":
        next_action = "inspect_blockers"
    return {
        "status": status,
        "next_action": next_action,
        "artifact_root": str(artifact_root),
        "validation_path": str(validation_path),
        "apply_result_path": str(apply_result_path),
        "evaluation_log_path": str(eval_log_path),
        "force_push_likely": bool(apply_result.get("force_push_likely")),
        "new_head": apply_result.get("new_head"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="Full replacement commit message.")
    group.add_argument(
        "--message-file",
        type=Path,
        help="Path to a UTF-8 text file containing the full replacement commit message. Repo-local temp inputs must live under .codex/tmp/.",
    )
    apply_group = parser.add_mutually_exclusive_group()
    apply_group.add_argument("--apply", action="store_true", help="Apply the amend after validation succeeds.")
    apply_group.add_argument("--dry-run", action="store_true", help="Validate only and emit a dry-run apply summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    artifact_root = create_artifact_root(repo_root)
    run_id = artifact_root.name
    validation_path = artifact_root / VALIDATION_FILE
    apply_result_path = artifact_root / APPLY_RESULT_FILE
    eval_log_path = artifact_root / EVAL_LOG_FILE

    try:
        message = load_message(args, repo_root)
        rules, context, repo_state, validation = validation_result(repo_root, message)
        write_json(artifact_root / RULES_FILE, rules)
        write_json(artifact_root / CONTEXT_FILE, context)
        write_json(validation_path, validation)
        if not bool(validation.get("valid")):
            apply_result = invalid_result(
                context=context,
                validation=validation,
                repo_state=repo_state,
                dry_run=not bool(args.apply),
            )
        elif bool(args.apply):
            apply_result = apply_message(repo_root, artifact_root, context, validation)
        else:
            apply_result = dry_run_result(repo_root, context, validation)
        write_json(apply_result_path, apply_result)
        eval_log = evaluation_log(
            run_id=run_id,
            context=context,
            validation=validation,
            apply_result=apply_result,
            artifact_root=artifact_root,
        )
        write_json(eval_log_path, eval_log)
        print(
            json.dumps(
                summary_payload(
                    artifact_root=artifact_root,
                    validation_path=validation_path,
                    apply_result_path=apply_result_path,
                    eval_log_path=eval_log_path,
                    validation=validation,
                    apply_result=apply_result,
                ),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0 if str(apply_result.get("status")) in {"dry-run", "ok"} else 1
    except Exception as exc:
        payload = {
            "status": "failed",
            "next_action": "inspect_error",
            "artifact_root": str(artifact_root),
            "validation_path": str(validation_path),
            "apply_result_path": str(apply_result_path),
            "evaluation_log_path": str(eval_log_path),
            "error_message": str(exc),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
