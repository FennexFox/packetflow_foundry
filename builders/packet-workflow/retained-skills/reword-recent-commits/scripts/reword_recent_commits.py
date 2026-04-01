#!/usr/bin/env python3
"""High-level driver for the reword-recent-commits workflow."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from reword_runtime_paths import (
    build_run_id,
    enforce_repo_local_codex_tmp_path,
    ensure_repo_codex_tmp_excluded,
    resolve_artifact_root,
    resolve_existing_artifact_root,
    resolve_repo_root,
)


SCRIPT_DIR = Path(__file__).resolve().parent
RULES_FILE = "rules.json"
PLAN_FILE = "plan.json"
RAW_PLAN_FILE = "raw-plan.json"
VALIDATED_FILE = "validated.json"
BUILD_RESULT_FILE = "build-result.json"
APPLY_RESULT_FILE = "apply-result.json"
EVAL_LOG_FILE = "eval-log.json"
MESSAGE_TEMPLATE_FILE = "message-template.json"
FINAL_FILE = "final-observations.json"


class DriverFailure(RuntimeError):
    def __init__(self, payload: dict[str, Any], exit_code: int = 1) -> None:
        super().__init__(str(payload.get("error_message") or payload.get("status") or "driver failed"))
        self.payload = payload
        self.exit_code = exit_code


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def script_path(name: str) -> Path:
    return SCRIPT_DIR / name


def run_python(
    script_name: str,
    args: list[str],
    *,
    repo_root: Path,
    allowed_exit_codes: set[int] | None = None,
) -> subprocess.CompletedProcess[str]:
    allowed = allowed_exit_codes if allowed_exit_codes is not None else {0}
    result = subprocess.run(
        [sys.executable, "-B", str(script_path(script_name)), *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode not in allowed:
        message = (result.stderr or result.stdout or "").strip() or f"{script_name} failed"
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": f"{script_name}: {message}",
                "step": script_name,
            }
        )
    return result


def message_template_from_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_fingerprint": context.get("context_fingerprint"),
        "branch": context.get("branch"),
        "head_commit": context.get("head_commit"),
        "commits": [
            {
                "index": int(commit.get("index") or 0),
                "hash": str(commit.get("hash") or ""),
                "current_subject": str(commit.get("subject") or ""),
                "new_message": "",
            }
            for commit in context.get("commits", [])
            if isinstance(commit, dict)
        ],
    }


def build_raw_plan(context: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    if str(template.get("context_fingerprint") or "") != str(context.get("context_fingerprint") or ""):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "messages-file context_fingerprint does not match the prepared context",
                "step": "messages-file",
            }
        )
    if str(template.get("branch") or "") != str(context.get("branch") or ""):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "messages-file branch does not match the prepared context",
                "step": "messages-file",
            }
        )
    if str(template.get("head_commit") or "") != str(context.get("head_commit") or ""):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "messages-file head_commit does not match the prepared context",
                "step": "messages-file",
            }
        )

    template_commits = template.get("commits")
    if not isinstance(template_commits, list):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "messages-file must contain a commits list",
                "step": "messages-file",
            }
        )

    by_hash: dict[str, dict[str, Any]] = {}
    by_index: dict[int, dict[str, Any]] = {}
    for item in template_commits:
        if not isinstance(item, dict):
            continue
        commit_hash = str(item.get("hash") or "").strip()
        commit_index = int(item.get("index") or 0)
        if commit_hash:
            by_hash[commit_hash] = item
        if commit_index:
            by_index[commit_index] = item

    raw_plan = copy.deepcopy(context)
    context_commits = raw_plan.get("commits")
    if not isinstance(context_commits, list):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "prepared context is missing commits",
                "step": "raw-plan",
            }
        )

    missing: list[str] = []
    for commit in context_commits:
        if not isinstance(commit, dict):
            continue
        commit_hash = str(commit.get("hash") or "").strip()
        commit_index = int(commit.get("index") or 0)
        template_commit = by_hash.get(commit_hash) or by_index.get(commit_index)
        if template_commit is None:
            missing.append(commit_hash or str(commit_index))
            continue
        commit["new_message"] = str(template_commit.get("new_message") or "")

    if missing:
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "messages-file is missing entries for commits: " + ", ".join(missing),
                "step": "raw-plan",
            }
        )
    return raw_plan


def merge_dicts(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_dicts(base[key], value)
        else:
            base[key] = value
    return base


def minimal_final_payload(validated: dict[str, Any], apply_result: dict[str, Any] | None) -> dict[str, Any]:
    if not bool(validated.get("valid")):
        return {
            "quality": {
                "result_status": "stopped",
                "first_pass_usable": False,
                "human_post_edit_required": True,
                "human_post_edit_severity": "medium",
                "final_output_changed_after_review": False,
            }
        }
    if apply_result is None:
        return {
            "quality": {
                "result_status": "stopped",
                "first_pass_usable": False,
                "human_post_edit_required": True,
                "human_post_edit_severity": "medium",
                "final_output_changed_after_review": False,
            }
        }
    dry_run = bool(apply_result.get("dry_run"))
    applied = apply_result.get("apply_succeeded")
    if dry_run:
        status = "dry-run"
        usable = True
        human_edit_required = False
        severity = "none"
    elif applied is True:
        status = "completed"
        usable = True
        human_edit_required = False
        severity = "none"
    elif apply_result.get("stop_reasons"):
        status = "stopped"
        usable = False
        human_edit_required = True
        severity = "high"
    else:
        status = "failed"
        usable = False
        human_edit_required = True
        severity = "high"
    return {
        "quality": {
            "result_status": status,
            "first_pass_usable": usable,
            "human_post_edit_required": human_edit_required,
            "human_post_edit_severity": severity,
            "final_output_changed_after_review": False,
        }
    }


def prepare(repo_root: Path, count: int, artifact_root: Path) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    rules_path = artifact_root / RULES_FILE
    plan_path = artifact_root / PLAN_FILE
    packet_dir = artifact_root / "packets"
    build_result_path = artifact_root / BUILD_RESULT_FILE
    eval_log_path = artifact_root / EVAL_LOG_FILE
    message_template_path = artifact_root / MESSAGE_TEMPLATE_FILE

    run_python(
        "collect_commit_rules.py",
        ["--repo", str(repo_root), "--output", str(rules_path)],
        repo_root=repo_root,
    )
    run_python(
        "collect_recent_commits.py",
        ["--count", str(count), "--repo", str(repo_root), "--rules", str(rules_path), "--output", str(plan_path)],
        repo_root=repo_root,
    )
    run_python(
        "build_reword_packets.py",
        ["--rules", str(rules_path), "--plan", str(plan_path), "--output-dir", str(packet_dir), "--result-output", str(build_result_path)],
        repo_root=repo_root,
    )
    run_python(
        "write_evaluation_log.py",
        ["init", "--context", str(plan_path), "--orchestrator", str(packet_dir / "orchestrator.json"), "--output", str(eval_log_path)],
        repo_root=repo_root,
    )
    run_python(
        "write_evaluation_log.py",
        ["phase", "--log", str(eval_log_path), "--phase", "build", "--result", str(build_result_path)],
        repo_root=repo_root,
    )

    context = load_json(plan_path)
    build_result = load_json(build_result_path)
    write_json(message_template_path, message_template_from_context(context))

    return {
        "status": "prepared",
        "next_action": "fill_message_template",
        "artifact_root": str(artifact_root),
        "message_template_path": str(message_template_path),
        "evaluation_log_path": str(eval_log_path),
        "review_mode": build_result.get("review_mode"),
        "common_path_sufficient": bool(build_result.get("common_path_sufficient")),
    }


def execute_messages_flow(
    repo_root: Path,
    artifact_root: Path,
    messages_file: Path,
    *,
    apply_changes: bool,
    dry_run_requested: bool,
    temp_root: Path | None,
    final_observations: Path | None,
) -> dict[str, Any]:
    rules_path = artifact_root / RULES_FILE
    plan_path = artifact_root / PLAN_FILE
    raw_plan_path = artifact_root / RAW_PLAN_FILE
    validated_path = artifact_root / VALIDATED_FILE
    apply_result_path = artifact_root / APPLY_RESULT_FILE
    eval_log_path = artifact_root / EVAL_LOG_FILE
    final_path = artifact_root / FINAL_FILE

    for required in (rules_path, plan_path, eval_log_path):
        if not required.is_file():
            raise DriverFailure(
                {
                    "status": "failed",
                    "error_message": f"missing prepared artifact: {required}",
                    "step": "artifact-load",
                }
            )

    context = load_json(plan_path)
    raw_plan = build_raw_plan(context, load_json(messages_file))
    write_json(raw_plan_path, raw_plan)

    run_python(
        "validate_reword_plan.py",
        ["--rules", str(rules_path), "--context", str(plan_path), "--plan", str(raw_plan_path), "--output", str(validated_path)],
        repo_root=repo_root,
        allowed_exit_codes={0, 1},
    )
    if not validated_path.is_file():
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": f"validate_reword_plan.py did not produce {validated_path}",
                "step": "validate_reword_plan.py",
            }
        )
    run_python(
        "write_evaluation_log.py",
        ["phase", "--log", str(eval_log_path), "--phase", "validate", "--result", str(validated_path)],
        repo_root=repo_root,
    )

    validated = load_json(validated_path)
    apply_result: dict[str, Any] | None = None

    if bool(validated.get("valid")):
        apply_args = ["--context", str(plan_path), "--plan", str(validated_path), "--result-output", str(apply_result_path)]
        if temp_root is not None:
            apply_args.extend(["--temp-root", str(temp_root)])
        if dry_run_requested or not apply_changes:
            apply_args.append("--dry-run")
        run_python(
            "apply_reword_plan.py",
            apply_args,
            repo_root=repo_root,
            allowed_exit_codes={0, 1},
        )
        if not apply_result_path.is_file():
            raise DriverFailure(
                {
                    "status": "failed",
                    "error_message": f"apply_reword_plan.py did not produce {apply_result_path}",
                    "step": "apply_reword_plan.py",
                }
            )
        run_python(
            "write_evaluation_log.py",
            ["phase", "--log", str(eval_log_path), "--phase", "apply", "--result", str(apply_result_path)],
            repo_root=repo_root,
        )
        apply_result = load_json(apply_result_path)

    final_payload = minimal_final_payload(validated, apply_result)
    if final_observations is not None:
        merge_dicts(final_payload, load_json(final_observations))
    write_json(final_path, final_payload)
    run_python(
        "write_evaluation_log.py",
        ["finalize", "--log", str(eval_log_path), "--final", str(final_path)],
        repo_root=repo_root,
    )

    if not bool(validated.get("valid")):
        return {
            "status": "invalid",
            "next_action": "fix_messages",
            "validated_path": str(validated_path),
            "apply_result_path": None,
            "evaluation_log_path": str(eval_log_path),
            "new_head": None,
        }

    if apply_result is None:
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "apply result is missing after a valid validation step",
                "step": "apply",
            }
        )

    status = str(apply_result.get("status") or "failed")
    next_action = "apply" if status == "dry-run" else ("done" if status == "ok" else "inspect_apply_result")
    return {
        "status": status,
        "next_action": next_action,
        "validated_path": str(validated_path),
        "apply_result_path": str(apply_result_path),
        "evaluation_log_path": str(eval_log_path),
        "new_head": apply_result.get("new_head"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository path. Defaults to the current directory.")
    parser.add_argument("--count", type=int, help="Number of recent commits to reword.")
    parser.add_argument("--prepare-only", action="store_true", help="Collect artifacts and write message-template.json.")
    parser.add_argument(
        "--messages-file",
        type=Path,
        help="Path to a filled message-template JSON payload. Repo-local temp inputs must live under .codex/tmp/.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and run apply_reword_plan.py in dry-run mode.")
    parser.add_argument("--apply", action="store_true", help="Apply the validated rewrite plan.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Optional artifact directory override. Repo-local overrides must live under .codex/tmp/.",
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        help="Optional temp worktree parent directory override. Repo-local overrides must live under .codex/tmp/.",
    )
    parser.add_argument(
        "--final-observations",
        type=Path,
        help="Optional JSON payload merged before evaluation finalize. Repo-local ad hoc inputs must live under .codex/tmp/.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if bool(args.prepare_only) == bool(args.messages_file):
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "choose exactly one of --prepare-only or --messages-file",
                "step": "argument-parse",
            },
            exit_code=2,
        )
    if args.prepare_only:
        if args.count is None or args.count <= 0:
            raise DriverFailure(
                {
                    "status": "failed",
                    "error_message": "--count must be a positive integer with --prepare-only",
                    "step": "argument-parse",
                },
                exit_code=2,
            )
        if args.dry_run or args.apply or args.temp_root or args.final_observations:
            raise DriverFailure(
                {
                    "status": "failed",
                    "error_message": "--prepare-only does not accept --dry-run, --apply, --temp-root, or --final-observations",
                    "step": "argument-parse",
                },
                exit_code=2,
            )
        return
    if args.apply and args.dry_run:
        raise DriverFailure(
            {
                "status": "failed",
                "error_message": "--apply and --dry-run are mutually exclusive",
                "step": "argument-parse",
            },
            exit_code=2,
        )


def main() -> int:
    args = parse_args()

    try:
        validate_args(args)
        repo_root = resolve_repo_root(Path(args.repo).resolve())
        ensure_repo_codex_tmp_excluded(repo_root)
        artifacts_dir = (
            enforce_repo_local_codex_tmp_path(repo_root, args.artifacts_dir, label="artifacts-dir")
            if args.artifacts_dir
            else None
        )
        temp_root = (
            enforce_repo_local_codex_tmp_path(repo_root, args.temp_root, label="temp-root")
            if args.temp_root
            else None
        )
        final_observations = (
            enforce_repo_local_codex_tmp_path(repo_root, args.final_observations, label="final-observations")
            if args.final_observations
            else None
        )
        if args.prepare_only:
            artifact_root = resolve_artifact_root(
                repo_root,
                run_id=build_run_id(),
                artifacts_dir=artifacts_dir,
            )
            emit(prepare(repo_root, int(args.count), artifact_root))
            return 0

        assert args.messages_file is not None
        messages_file = enforce_repo_local_codex_tmp_path(repo_root, args.messages_file, label="messages-file")
        artifact_root = resolve_existing_artifact_root(
            repo_root,
            messages_file=messages_file,
            artifacts_dir=artifacts_dir,
        )
        summary = execute_messages_flow(
            repo_root,
            artifact_root,
            messages_file,
            apply_changes=bool(args.apply),
            dry_run_requested=bool(args.dry_run),
            temp_root=temp_root,
            final_observations=final_observations,
        )
        emit(summary)
        return 0 if summary["status"] in {"ok", "dry-run"} else 1
    except DriverFailure as exc:
        emit(exc.payload)
        return exc.exit_code
    except Exception as exc:
        emit({"status": "failed", "error_message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
