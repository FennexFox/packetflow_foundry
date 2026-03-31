#!/usr/bin/env python3
"""Smoke-test git-split-and-commit on a temp repository."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_python(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"python {' '.join(args)} failed")
    return result


def run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
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
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def create_repo(repo_root: Path) -> None:
    run_git(repo_root, ["init"])
    run_git(repo_root, ["config", "user.name", "Smoke Test"])
    run_git(repo_root, ["config", "user.email", "smoke@example.test"])

    write_text(
        repo_root / ".github" / "instructions" / "commit-message.instructions.md",
        "\n".join(
            [
                "## Format",
                "- Use `<type>(<scope>): <subject>`.",
                "",
                "## Types",
                "- `fix`",
                "- `docs`",
                "",
                "## Scopes",
                "- `core`",
            ]
        )
        + "\n",
    )
    write_text(repo_root / "src" / "app.py", "print('before')\n")
    write_text(repo_root / "docs" / "notes.md", "# Notes\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "fix(core): seed repo"])

    write_text(repo_root / "src" / "app.py", "print('after')\n")


def build_plan(worktree: dict) -> dict:
    return {
        "repo_root": worktree["repo_root"],
        "base_head": worktree["head_commit"],
        "worktree_fingerprint": worktree["worktree_fingerprint"],
        "input_scope": worktree["input_scope"],
        "overall_confidence": "high",
        "validation_commands": [],
        "omitted_paths": [],
        "stop_reasons": [],
        "commits": [
            {
                "commit_index": 1,
                "intent_summary": "Update app output.",
                "type": "fix",
                "scope": "core",
                "subject": "update app output",
                "body": ["- update the tracked runtime file"],
                "whole_file_paths": ["src/app.py"],
                "untracked_paths": [],
                "split_paths": [],
                "selected_hunk_ids": [],
                "supporting_paths": [],
                "targeted_checks": [],
                "confidence": "high",
            }
        ],
    }


def main() -> int:
    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "git-split-and-commit"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as tmp_dir:
        root = Path(tmp_dir)
        repo_root = root / "repo"
        repo_root.mkdir()
        create_repo(repo_root)

        rules_path = root / "rules.json"
        worktree_path = root / "worktree.json"
        packet_dir = root / "packets"
        build_result_path = root / "build-result.json"
        plan_path = root / "commit-plan.json"
        validation_path = root / "validation.json"
        apply_result_path = root / "apply-result.json"
        eval_log_path = root / "eval-log.json"

        run_python(
            [
                str(SCRIPT_DIR / "collect_commit_rules.py"),
                "--repo",
                str(repo_root),
                "--output",
                str(rules_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "collect_worktree_context.py"),
                "--repo",
                str(repo_root),
                "--output",
                str(worktree_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "build_commit_packets.py"),
                "--rules",
                str(rules_path),
                "--worktree",
                str(worktree_path),
                "--output-dir",
                str(packet_dir),
                "--result-output",
                str(build_result_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "init",
                "--context",
                str(worktree_path),
                "--orchestrator",
                str(packet_dir / "orchestrator.json"),
                "--output",
                str(eval_log_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "build",
                "--result",
                str(build_result_path),
            ]
        )

        worktree = load_json(worktree_path)
        plan_path.write_text(json.dumps(build_plan(worktree), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        run_python(
            [
                str(SCRIPT_DIR / "validate_commit_plan.py"),
                "--worktree",
                str(worktree_path),
                "--plan",
                str(plan_path),
                "--output",
                str(validation_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "validate",
                "--result",
                str(validation_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "apply_commit_plan.py"),
                "--worktree",
                str(worktree_path),
                "--validation",
                str(validation_path),
                "--dry-run",
                "--result-output",
                str(apply_result_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "apply",
                "--result",
                str(apply_result_path),
            ]
        )

        build_result = load_json(build_result_path)
        eval_log = load_json(eval_log_path)
        packet_metrics = load_json(packet_dir / "packet_metrics.json")
        if not build_result.get("common_path_sufficient"):
            raise RuntimeError("Smoke fixture should be common-path sufficient.")
        if build_result.get("raw_reread_count") != 0:
            raise RuntimeError("Smoke fixture unexpectedly requires raw rereads.")
        if packet_metrics.get("estimated_packet_tokens", 0) >= packet_metrics.get("estimated_local_only_tokens", 0):
            raise RuntimeError("Packet tokens should remain below local-only tokens for the smoke fixture.")

        summary = {
            "common_path_sufficient": build_result.get("common_path_sufficient"),
            "raw_reread_count": build_result.get("raw_reread_count"),
            "raw_reread_reasons": build_result.get("raw_reread_reasons"),
            "packet_metrics": packet_metrics,
            "evaluation_log": {
                "result_status": (eval_log.get("quality") or {}).get("result_status"),
                "common_path_sufficient": ((eval_log.get("skill_specific") or {}).get("data") or {}).get("common_path_sufficient"),
                "estimated_delegation_savings": (eval_log.get("baseline") or {}).get("estimated_delegation_savings"),
            },
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
