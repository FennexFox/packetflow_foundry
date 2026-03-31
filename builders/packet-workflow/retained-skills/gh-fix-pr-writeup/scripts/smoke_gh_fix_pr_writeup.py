#!/usr/bin/env python3
"""Smoke-test gh-fix-pr-writeup with a temp repository and mocked gh."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


CURRENT_PR_BODY = "\n".join(
    [
        "## Why",
        "The current writeup is too vague.",
        "## What changed",
        "- Reworked the PR body structure.",
        "## How",
        "Note any important defaults, thresholds, reload/restart requirements, or",
        "## Risk / Rollback",
        "Minimal risk.",
        "## Testing",
        "Not run.",
    ]
)


REPLACEMENT_BODY = "\n".join(
    [
        "## Why",
        "Clarify the shipped behavior and tighten the PR guardrails.",
        "## What changed",
        "- Added a guarded validate/apply flow for PR text updates.",
        "- Kept the final writeup aligned with the inspected diff and local rules gate.",
        "## How",
        "- Re-fetched the live PR snapshot before the guarded mutation.",
        "## Risk / Rollback",
        "- Revert the PR text if the replacement proves inaccurate.",
        "## Testing",
        "- Ran `python -m unittest discover tests`.",
        "Refs: #42",
    ]
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run_python(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stderr.strip(), result.stdout.strip()) if part)
        raise RuntimeError(details or f"python {' '.join(args)} failed")
    return result


def run_git(repo_root: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_repo(repo_root: Path) -> None:
    run_git(repo_root, ["init"])
    run_git(repo_root, ["config", "user.name", "Smoke Test"])
    run_git(repo_root, ["config", "user.email", "smoke@example.invalid"])

    write_text(
        repo_root / ".github" / "pull_request_template.md",
        "\n".join(
            [
                "## Why",
                "",
                "## What changed",
                "",
                "## How",
                "",
                "## Risk / Rollback",
                "",
                "## Testing",
                "",
            ]
        )
        + "\n",
    )
    write_text(
        repo_root / ".github" / "instructions" / "pull-request.instructions.md",
        "\n".join(
            [
                "# PR Rules",
                "",
                "## PR Title",
                "Use Conventional Commit style.",
                "",
                "## PR Body",
                "Keep the PR body concise and evidence-backed.",
            ]
        )
        + "\n",
    )
    write_text(
        repo_root / ".github" / "instructions" / "commit-message.instructions.md",
        "\n".join(
            [
                "# Commit Message Rules",
                "",
                "## Types",
                "- feat",
                "- fix",
                "- docs",
            ]
        )
        + "\n",
    )
    write_text(repo_root / "README.md", "# README\n",)
    write_text(repo_root / "ExampleProduct" / "Systems" / "OfficeDemandDiagnosticsSystem.cs", "namespace Smoke;\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "Initial smoke fixture"])


def install_gh_stub(target_dir: Path, repo_slug: str) -> Path:
    state_path = target_dir / "gh_state.json"
    write_json(
        state_path,
        {
            "repo_slug": repo_slug,
            "pr": {
                "number": 7,
                "title": "docs(pr-writeup): polish guard rails",
                "body": CURRENT_PR_BODY,
                "headRefName": "codex/writeup-guard",
                "headRefOid": "abc123def456",
                "baseRefName": "main",
                "url": "https://example.invalid/pr/7",
                "closingIssuesReferences": [{"number": 42}],
            },
            "changed_files": [
                "README.md",
                "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs",
            ],
        },
    )
    return state_path


def main() -> int:
    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "gh-fix-pr-writeup"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        repo_root = tmp_dir / "repo"
        repo_root.mkdir()
        init_repo(repo_root)

        state_path = install_gh_stub(repo_root, "owner/repo")

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["GH_FIX_PR_WRITEUP_GH_STUB_STATE"] = str(state_path)

        context_path = tmp_dir / "context.json"
        lint_path = tmp_dir / "lint.json"
        build_result_path = tmp_dir / "build-result.json"
        validation_path = tmp_dir / "validation.json"
        apply_result_path = tmp_dir / "apply.json"
        eval_log_path = tmp_dir / "evaluation.json"
        body_path = tmp_dir / "replacement.md"
        packet_dir = tmp_dir / "packets"

        body_path.write_text(REPLACEMENT_BODY + "\n", encoding="utf-8")

        run_python(
            [
                str(SCRIPT_DIR / "collect_pr_context.py"),
                "7",
                "--repo-root",
                str(repo_root),
                "--repo",
                "owner/repo",
                "--output",
                str(context_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "lint_pr_writeup.py"),
                "--context",
                str(context_path),
                "--output",
                str(lint_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "build_pr_review_packets.py"),
                "--context",
                str(context_path),
                "--lint",
                str(lint_path),
                "--output-dir",
                str(packet_dir),
                "--result-output",
                str(build_result_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "validate_pr_writeup_edit.py"),
                "--context",
                str(context_path),
                "--title",
                "docs(pr-writeup): tighten guard rails",
                "--body-file",
                str(body_path),
                "--output",
                str(validation_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "apply_pr_writeup.py"),
                "--validation",
                str(validation_path),
                "--dry-run",
                "--result-output",
                str(apply_result_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "init",
                "--context",
                str(context_path),
                "--orchestrator",
                str(packet_dir / "orchestrator.json"),
                "--lint",
                str(lint_path),
                "--output",
                str(eval_log_path),
            ],
            cwd=repo_root,
            env=env,
        )
        for phase, result_path in (
            ("build", build_result_path),
            ("validate", validation_path),
            ("apply", apply_result_path),
        ):
            run_python(
                [
                    str(SCRIPT_DIR / "write_evaluation_log.py"),
                    "phase",
                    "--log",
                    str(eval_log_path),
                    "--phase",
                    phase,
                    "--result",
                    str(result_path),
                ],
                cwd=repo_root,
                env=env,
            )

        build_result = read_json(build_result_path)
        validation = read_json(validation_path)
        apply_result = read_json(apply_result_path)
        packet_metrics = read_json(packet_dir / "packet_metrics.json")
        eval_log = read_json(eval_log_path)
        orchestrator = read_json(packet_dir / "orchestrator.json")

        assert build_result["qa_required"] is False
        assert build_result["raw_reread_count"] == 0
        assert build_result["common_path_sufficient"] is True
        assert validation["qa_required"] is False
        assert apply_result["apply_succeeded"] is True
        assert packet_metrics["estimated_packet_tokens"] < packet_metrics["estimated_local_only_tokens"]
        assert packet_metrics["estimated_delegation_savings"] > 0
        assert "estimated_packet_tokens" not in orchestrator
        assert eval_log["skill_specific"]["data"]["common_path_sufficient"] is True
        assert eval_log["skill_specific"]["data"]["raw_reread_count"] == 0

        print(
            json.dumps(
                {
                    "smoke": "passed",
                    "qa_required": build_result["qa_required"],
                    "raw_reread_count": build_result["raw_reread_count"],
                    "common_path_sufficient": build_result["common_path_sufficient"],
                    "estimated_local_only_tokens": packet_metrics["estimated_local_only_tokens"],
                    "estimated_packet_tokens": packet_metrics["estimated_packet_tokens"],
                    "estimated_delegation_savings": packet_metrics["estimated_delegation_savings"],
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
