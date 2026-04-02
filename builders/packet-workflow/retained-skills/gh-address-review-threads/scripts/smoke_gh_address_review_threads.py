#!/usr/bin/env python3
"""Run an operator-facing or synthetic dry-run smoke for gh-address-review-threads.

Output schema always includes:
- status
- reason
- thread_counts
- next_action
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import review_thread_run as run_support
from thread_action_contract import build_context_fingerprint


SCRIPT_DIR = Path(__file__).resolve().parent


class GhCliMissing(RuntimeError):
    """Raised when the gh CLI is unavailable in the current environment."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root to inspect. Defaults to the current working directory.")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run a self-contained synthetic dry-run smoke without requiring a live PR or gh auth.",
    )
    return parser.parse_args()


def script_path(name: str) -> Path:
    return SCRIPT_DIR / name


def repo_root_path(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def run_process(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", *args] if args and args[0].endswith(".py") else args
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        executable = command[0] if command else "command"
        raise GhCliMissing(f"{executable} is not installed or not on PATH") from exc


def run_script(args: list[str], *, cwd: Path) -> str:
    result = run_process(args, cwd=cwd)
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip() or f"{' '.join(args)} failed"
        raise RuntimeError(detail)
    return result.stdout


def run_json(args: list[str], *, cwd: Path) -> dict[str, Any]:
    output = run_script(args, cwd=cwd)
    return json.loads(output)


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def synthetic_pr_body() -> str:
    return "\n".join(
        [
            "## Why",
            "Keep review-thread dry-run smoke self-contained.",
            "## What changed",
            "Added a synthetic smoke path that uses packet-first fixtures.",
            "## Testing",
            "Run the standalone smoke with --synthetic.",
        ]
    )


def synthetic_background_text(title: str) -> str:
    return "\n".join(
        [
            title,
            "The maintainer notes here are intentionally longer than the packet-facing excerpts.",
            "They exist to make the synthetic smoke representative of a real PR discussion with extra narrative context.",
            "The packet builder should still compress the actionable review-thread surface into the focused packets and global summary.",
            "If the smoke needs to reread this text to make a dry-run-safe defer decision, packet quality has regressed.",
        ]
    )


def synthetic_reply_candidate(*, mode: str, reason: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "comment_id": None,
        "reason": reason,
        "managed": False,
        "adopted_unmarked_reply": False,
    }


def synthetic_thread(*, thread_id: str, path: str, line: int, reviewer_login: str, reviewer_body: str) -> dict[str, Any]:
    reviewer_comment = {
        "id": f"review-{thread_id}",
        "author_login": reviewer_login,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
        "url": f"https://example.invalid/thread/{thread_id}",
        "body": reviewer_body,
    }
    return {
        "thread_id": thread_id,
        "is_resolved": False,
        "is_outdated": False,
        "path": path,
        "line": line,
        "start_line": line,
        "diff_side": "RIGHT",
        "start_diff_side": "RIGHT",
        "original_line": line,
        "original_start_line": line,
        "resolved_by": None,
        "reviewer_login": reviewer_login,
        "reviewer_comment": reviewer_comment,
        "latest_reviewer_comment_at": reviewer_comment["updated_at"],
        "latest_self_reply": None,
        "reply_candidates": {
            "ack": synthetic_reply_candidate(mode="add", reason="no_existing_ack_reply"),
            "complete": synthetic_reply_candidate(mode="add", reason="complete_never_adopts_unmarked_reply"),
        },
        "marker_conflicts": [],
        "comments": [],
    }


def build_synthetic_context(temp_dir: Path) -> tuple[Path, Path, Path, list[str], list[str]]:
    repo_root = temp_dir / "synthetic-repo"
    previous_context_path = temp_dir / "previous-context.json"
    context_path = temp_dir / "context.json"
    (repo_root / ".github").mkdir(parents=True, exist_ok=True)
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "pull_request_template.md").write_text(
        "\n".join(["## Why", "## What changed", "## Testing"]),
        encoding="utf-8",
    )
    run_git(repo_root, "init", "-b", "main")
    run_git(repo_root, "config", "user.name", "Codex")
    run_git(repo_root, "config", "user.email", "codex@example.com")
    (repo_root / "src" / "app.py").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
    (repo_root / "src" / "helper.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (repo_root / "docs" / "guide.md").write_text("# Guide\nOriginal wording\n", encoding="utf-8")
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "--no-gpg-sign", "-m", "fix(repo): seed synthetic review context")
    run_git(repo_root, "checkout", "-b", "feature/packets")
    (repo_root / "src" / "helper.py").write_text("alpha\nbeta updated\ngamma\n", encoding="utf-8")
    (repo_root / "docs" / "guide.md").write_text("# Guide\nCurrent wording\n", encoding="utf-8")
    run_git(repo_root, "add", "src/helper.py", "docs/guide.md")
    run_git(repo_root, "commit", "--no-gpg-sign", "-m", "fix(app): apply accepted review changes")

    base_context = {
        "repo_root": str(repo_root),
        "repo_slug": "example/repo",
        "viewer_login": "codex",
        "pr": {
            "id": "PR_SYNTHETIC",
            "number": 11,
            "title": "Synthetic review-thread smoke",
            "url": "https://example.invalid/pr/11",
            "state": "OPEN",
            "headRefName": "feature/packets",
            "baseRefName": "main",
            "body": synthetic_pr_body(),
            "closingIssuesReferences": [{"number": 55}],
        },
        "changed_files": ["docs/guide.md", "src/helper.py"],
        "changed_file_groups": {
            "runtime": {"count": 1, "sample_files": ["src/helper.py"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 1, "sample_files": ["docs/guide.md"]},
            "tests": {"count": 0, "sample_files": []},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
        "diff_stat": " 2 files changed, 24 insertions(+), 2 deletions(-)",
        "rule_files": {},
        "expected_template_sections": [],
        "conversation_comments": [
            {
                "id": "conversation-1",
                "author_login": "maintainer-a",
                "created_at": "2026-03-01T00:00:00Z",
                "updated_at": "2026-03-01T00:00:00Z",
                "url": "https://example.invalid/comment/conversation-1",
                "body": synthetic_background_text("Top-level maintainer context for the synthetic smoke."),
            },
            {
                "id": "conversation-2",
                "author_login": "maintainer-b",
                "created_at": "2026-03-01T00:05:00Z",
                "updated_at": "2026-03-01T00:05:00Z",
                "url": "https://example.invalid/comment/conversation-2",
                "body": synthetic_background_text("Additional rollout and validation notes that should stay out of the common path."),
            },
        ],
        "reviews": [
            {
                "id": "review-1",
                "author_login": "reviewer-a",
                "state": "COMMENTED",
                "submitted_at": "2026-03-01T00:10:00Z",
                "body": synthetic_background_text("Review summary that should raise local-only token cost more than packet cost."),
            }
        ],
        "threads": [
            synthetic_thread(
                thread_id="t-1",
                path="docs/guide.md",
                line=2,
                reviewer_login="reviewer-a",
                reviewer_body="Please use the current wording in the guide.",
            ),
            synthetic_thread(
                thread_id="t-2",
                path="src/helper.py",
                line=2,
                reviewer_login="reviewer-b",
                reviewer_body="Please cover the helper behavior with a note.",
            ),
        ],
    }
    previous_context = json.loads(json.dumps(base_context))
    context = json.loads(json.dumps(base_context))
    context["threads"][0]["is_outdated"] = True
    previous_context["context_fingerprint"] = build_context_fingerprint(previous_context)
    context["context_fingerprint"] = build_context_fingerprint(context)
    write_json(previous_context_path, previous_context)
    write_json(context_path, context)
    return (
        repo_root,
        previous_context_path,
        context_path,
        ["t-1"],
        ["python -m pytest tests/test_docs.py"],
    )


def ensure_gh_auth(repo_root: Path) -> bool:
    result = run_process(["gh", "auth", "status"], cwd=repo_root)
    return result.returncode == 0


def current_branch_pr(repo_root: Path) -> dict[str, Any] | None:
    result = run_process(
        ["gh", "pr", "view", "--json", "number,url,title,state,headRefName,baseRefName"],
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) and payload.get("number") else None


def thread_counts_from_context(context: dict[str, Any]) -> dict[str, int]:
    threads = [thread for thread in context.get("threads", []) if not thread.get("is_resolved")]
    outdated = [thread for thread in threads if thread.get("is_outdated")]
    return {
        "unresolved": len(threads),
        "unresolved_non_outdated": len(threads) - len(outdated),
        "unresolved_outdated": len(outdated),
    }


def summary(status: str, reason: str | None, thread_counts: dict[str, int], next_action: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "reason": reason,
        "thread_counts": thread_counts,
        "next_action": next_action,
    }
    payload.update(extra)
    return payload


def build_safe_plan(context: dict[str, Any], *, phase: str) -> dict[str, Any]:
    actions = []
    for thread in context.get("threads", []):
        if thread.get("is_resolved"):
            continue
        decision = "defer-outdated" if thread.get("is_outdated") else "defer"
        action = {
            "thread_id": thread.get("thread_id"),
            "decision": decision,
        }
        if phase == "ack":
            action["ack_mode"] = "skip"
        else:
            action["complete_mode"] = "skip"
            action["resolve_after_complete"] = False
        actions.append(action)
    return {"thread_actions": actions}


def merge_eval_phase(log_path: Path, phase: str, result_path: Path, *, cwd: Path) -> None:
    run_script(
        [
            str(script_path("write_evaluation_log.py")),
            "phase",
            "--log",
            str(log_path),
            "--phase",
            phase,
            "--result",
            str(result_path),
        ],
        cwd=cwd,
    )


def run_smoke_workflow(
    *,
    repo_root: Path,
    context_path: Path,
    temp_dir: Path,
    previous_context_path: Path | None = None,
    accepted_thread_ids: list[str] | None = None,
    validation_commands: list[str] | None = None,
) -> dict[str, Any]:
    manifest = run_support.create_run(
        repo_root,
        previous_context_path or context_path,
        evaluation_log_path=temp_dir / "eval-log.json",
    )
    manifest_path = Path(manifest["paths"]["manifest"])
    if validation_commands:
        run_support.set_validation_commands(manifest, validation_commands)
    if accepted_thread_ids:
        run_support.set_accepted_threads(manifest, accepted_thread_ids)

    if previous_context_path is not None:
        run_support.copy_context_into_manifest(
            manifest,
            phase="post",
            source_path=context_path,
        )
        run_support.write_reconciliation_input(manifest)
        build_context_path = Path(manifest["paths"]["post"]["context"])
        packet_dir = Path(manifest["paths"]["post"]["packet_dir"])
        build_result_path = Path(manifest["paths"]["post"]["build_result"])
        reconciliation_input_path = Path(manifest["paths"]["post"]["reconciliation_input"])
        previous_context_path = Path(manifest["paths"]["pre"]["context"])
    else:
        build_context_path = Path(manifest["paths"]["pre"]["context"])
        packet_dir = Path(manifest["paths"]["pre"]["packet_dir"])
        build_result_path = Path(manifest["paths"]["pre"]["build_result"])
        reconciliation_input_path = None

    ack_plan_path = Path(manifest["paths"]["ack"]["raw_plan"])
    ack_validation_path = Path(manifest["paths"]["ack"]["validated_plan"])
    ack_result_path = Path(manifest["paths"]["ack"]["result"])
    complete_plan_path = Path(manifest["paths"]["complete"]["raw_plan"])
    complete_validation_path = Path(manifest["paths"]["complete"]["validated_plan"])
    complete_result_path = Path(manifest["paths"]["complete"]["result"])
    eval_log_path = Path(manifest["paths"]["evaluation_log"])

    run_support.write_manifest(manifest_path, manifest)
    run_support.write_latest_pointer(repo_root, manifest)

    context = read_json(build_context_path)
    counts = thread_counts_from_context(context)
    if counts["unresolved"] == 0:
        return summary(
            "noop",
            "no_unresolved_threads",
            counts,
            "nothing_to_do",
            pr_url=context.get("pr", {}).get("url"),
            run_id=manifest["run_id"],
            run_root=manifest["paths"]["run_root"],
            manifest_path=manifest["paths"]["manifest"],
        )

    build_args = [
        str(script_path("build_review_packets.py")),
        "--context",
        str(build_context_path),
        "--repo-root",
        str(repo_root),
        "--output-dir",
        str(packet_dir),
        "--result-output",
        str(build_result_path),
    ]
    if previous_context_path is not None:
        build_args.extend(["--previous-context", str(previous_context_path)])
    if reconciliation_input_path is not None:
        build_args.extend(["--reconciliation-input", str(reconciliation_input_path)])
    run_script(build_args, cwd=repo_root)
    build_result = read_json(build_result_path)

    run_script(
        [
            str(script_path("write_evaluation_log.py")),
            "init",
            "--context",
            str(context_path),
            "--orchestrator",
            str(packet_dir / "orchestrator.json"),
            "--output",
            str(eval_log_path),
        ],
        cwd=repo_root,
    )
    merge_eval_phase(eval_log_path, "build", build_result_path, cwd=repo_root)

    write_json(ack_plan_path, build_safe_plan(context, phase="ack"))
    run_script(
        [
            str(script_path("validate_thread_action_plan.py")),
            "--context",
            str(context_path),
            "--plan",
            str(ack_plan_path),
        "--phase",
        "ack",
        "--output",
        str(ack_validation_path),
        ],
        cwd=repo_root,
    )
    merge_eval_phase(eval_log_path, "validate", ack_validation_path, cwd=repo_root)
    run_support.copy_validated_plan_into_manifest(
        manifest,
        phase="ack",
        source_path=ack_validation_path,
    )
    run_support.write_manifest(manifest_path, manifest)
    run_support.write_latest_pointer(repo_root, manifest)
    run_script(
        [
            str(script_path("apply_thread_action_plan.py")),
            "--context",
            str(build_context_path),
            "--plan",
            str(ack_validation_path),
            "--phase",
            "ack",
            "--dry-run",
            "--result-output",
            str(ack_result_path),
        ],
        cwd=repo_root,
    )
    merge_eval_phase(eval_log_path, "apply", ack_result_path, cwd=repo_root)

    run_script(
        [
            str(script_path("reconcile_outdated_threads.py")),
            "--context",
            str(build_context_path),
            "--packet-dir",
            str(packet_dir),
            "--output",
            str(complete_plan_path),
        ],
        cwd=repo_root,
    )
    run_script(
        [
            str(script_path("validate_thread_action_plan.py")),
            "--context",
            str(build_context_path),
            "--plan",
            str(complete_plan_path),
            "--phase",
            "complete",
            "--output",
            str(complete_validation_path),
        ],
        cwd=repo_root,
    )
    merge_eval_phase(eval_log_path, "validate", complete_validation_path, cwd=repo_root)
    run_script(
        [
            str(script_path("apply_thread_action_plan.py")),
            "--context",
            str(build_context_path),
            "--plan",
            str(complete_validation_path),
            "--phase",
            "complete",
            "--dry-run",
            "--result-output",
            str(complete_result_path),
        ],
        cwd=repo_root,
    )
    merge_eval_phase(eval_log_path, "apply", complete_result_path, cwd=repo_root)

    packet_metrics = read_json(packet_dir / "packet_metrics.json")
    complete_result = read_json(complete_result_path)
    reconciliation_summary = complete_result.get("reconciliation_summary") or {}
    return summary(
        "ok",
        None,
        counts,
        "review_smoke_results",
        pr_url=context.get("pr", {}).get("url"),
        run_id=manifest["run_id"],
        run_root=manifest["paths"]["run_root"],
        manifest_path=manifest["paths"]["manifest"],
        review_mode=build_result.get("review_mode"),
        common_path_sufficient=build_result.get("common_path_sufficient"),
        estimated_packet_tokens=packet_metrics.get("estimated_packet_tokens"),
        estimated_delegation_savings=packet_metrics.get("estimated_delegation_savings"),
        outdated_transition_candidates=reconciliation_summary.get(
            "outdated_transition_candidates",
            build_result.get("outdated_transition_candidates"),
        ),
        outdated_auto_resolved=reconciliation_summary.get("outdated_auto_resolved", 0),
        outdated_recheck_ambiguous=reconciliation_summary.get(
            "outdated_recheck_ambiguous",
            build_result.get("outdated_recheck_ambiguous"),
        ),
    )


def main() -> int:
    args = parse_args()
    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "gh-address-review-threads"
    temp_root.mkdir(parents=True, exist_ok=True)
    if args.synthetic:
        with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-synthetic-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            (
                repo_root,
                previous_context_path,
                context_path,
                accepted_thread_ids,
                validation_commands,
            ) = build_synthetic_context(temp_dir)
            print(
                json.dumps(
                    run_smoke_workflow(
                        repo_root=repo_root,
                        context_path=context_path,
                        temp_dir=temp_dir,
                        previous_context_path=previous_context_path,
                        accepted_thread_ids=accepted_thread_ids,
                        validation_commands=validation_commands,
                    ),
                    indent=2,
                    ensure_ascii=True,
                )
            )
            return 0

    repo_root = repo_root_path(args.repo_root)

    try:
        gh_authed = ensure_gh_auth(repo_root)
    except GhCliMissing:
        print(
            json.dumps(
                summary("blocked", "gh_cli_missing", {"unresolved": 0, "unresolved_non_outdated": 0, "unresolved_outdated": 0}, "install_gh_cli"),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    if not gh_authed:
        print(
            json.dumps(
                summary("blocked", "gh_auth_missing", {"unresolved": 0, "unresolved_non_outdated": 0, "unresolved_outdated": 0}, "run_gh_auth_login"),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    try:
        pr = current_branch_pr(repo_root)
    except GhCliMissing:
        print(
            json.dumps(
                summary("blocked", "gh_cli_missing", {"unresolved": 0, "unresolved_non_outdated": 0, "unresolved_outdated": 0}, "install_gh_cli"),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0
    if not pr:
        print(
            json.dumps(
                summary("blocked", "no_open_pr", {"unresolved": 0, "unresolved_non_outdated": 0, "unresolved_outdated": 0}, "open_pr_for_current_branch"),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-live-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        context_path = temp_dir / "context.json"
        run_script(
            [
                str(script_path("collect_review_threads.py")),
                "--repo",
                str(repo_root),
                "--output",
                str(context_path),
            ],
            cwd=repo_root,
        )
        print(json.dumps(run_smoke_workflow(repo_root=repo_root, context_path=context_path, temp_dir=temp_dir), indent=2, ensure_ascii=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
