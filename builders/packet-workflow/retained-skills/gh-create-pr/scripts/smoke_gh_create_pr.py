#!/usr/bin/env python3
"""Smoke-test gh-create-pr with a temp repository and mocked gh."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent

PR_BODY = "\n".join(
    [
        "## Why",
        "Open a guarded PR from a pushed branch.",
        "## What changed",
        "- Added a validator-normalized `gh pr create` path.",
        "- Re-check duplicate PR and template state before create.",
        "## How",
        "- Kept creation fail-closed on stale head/template snapshots.",
        "## Risk / Rollback",
        "- Re-run validation after refreshing the branch state.",
        "## Testing",
        "- Not run (synthetic smoke).",
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


def init_repo(repo_root: Path, origin_root: Path) -> None:
    origin_root.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "init", "--bare", str(origin_root)],
        cwd=str(origin_root.parent),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git init --bare failed")
    run_git(repo_root, ["init", "-b", "main"])
    run_git(repo_root, ["config", "user.name", "Smoke Test"])
    run_git(repo_root, ["config", "user.email", "smoke@example.invalid"])
    run_git(repo_root, ["remote", "add", "origin", str(origin_root)])

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
    write_text(repo_root / "README.md", "# README\n")
    write_text(repo_root / "src" / "creator.py", "VALUE = 1\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "Initial smoke fixture"])
    run_git(repo_root, ["push", "-u", "origin", "main"])

    run_git(repo_root, ["checkout", "-b", "feature/pr-create-guard"])
    run_git(repo_root, ["config", "branch.feature/pr-create-guard.gh-merge-base", "main"])
    write_text(repo_root / "src" / "creator.py", "VALUE = 2\n")
    write_text(repo_root / "tests" / "test_creator.py", "def test_smoke_fixture():\n    assert True\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "feat(pr-create): add guarded creator #42"])
    run_git(repo_root, ["push", "-u", "origin", "feature/pr-create-guard"])


def install_gh_stub(target_dir: Path, repo_slug: str) -> Path:
    state_path = target_dir / "gh_state.json"
    write_json(
        state_path,
        {
            "repo_slug": repo_slug,
            "default_branch": "main",
            "existing_prs": [],
            "next_pr_number": 7,
        },
    )
    return state_path


def main() -> int:
    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "gh-create-pr"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        repo_root = tmp_dir / "repo"
        origin_root = tmp_dir / "origin.git"
        repo_root.mkdir()
        init_repo(repo_root, origin_root)

        state_path = install_gh_stub(repo_root, "owner/repo")

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["GH_CREATE_PR_GH_STUB_STATE"] = str(state_path)

        context_path = tmp_dir / "context.json"
        lint_path = tmp_dir / "lint.json"
        build_result_path = tmp_dir / "build-result.json"
        validation_path = tmp_dir / "validation.json"
        dry_run_path = tmp_dir / "dry-run.json"
        apply_result_path = tmp_dir / "apply.json"
        body_path = tmp_dir / "body.md"
        packet_dir = tmp_dir / "packets"

        body_path.write_text(PR_BODY + "\n", encoding="utf-8")

        run_python(
            [
                str(SCRIPT_DIR / "collect_pr_create_context.py"),
                "--repo-root",
                str(repo_root),
                "--repo",
                "owner/repo",
                "--draft",
                "--reviewer",
                "alice",
                "--assignee",
                "bob",
                "--label",
                "automation",
                "--output",
                str(context_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "lint_pr_create.py"),
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
                str(SCRIPT_DIR / "build_pr_create_packets.py"),
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
                str(SCRIPT_DIR / "validate_pr_create.py"),
                "--context",
                str(context_path),
                "--title",
                "feat(pr-create): create guarded PRs",
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
                str(SCRIPT_DIR / "apply_pr_create.py"),
                "--validation",
                str(validation_path),
                "--dry-run",
                "--result-output",
                str(dry_run_path),
            ],
            cwd=repo_root,
            env=env,
        )
        run_python(
            [
                str(SCRIPT_DIR / "apply_pr_create.py"),
                "--validation",
                str(validation_path),
                "--result-output",
                str(apply_result_path),
            ],
            cwd=repo_root,
            env=env,
        )

        validation = read_json(validation_path)
        dry_run = read_json(dry_run_path)
        apply_result = read_json(apply_result_path)
        state = read_json(state_path)
        created = state["existing_prs"][0]
        summary = {
            "validation_valid": validation["valid"],
            "dry_run_apply_succeeded": dry_run["apply_succeeded"],
            "apply_succeeded": apply_result["apply_succeeded"],
            "created_pr_url": created["url"],
            "created_pr_number": created["number"],
            "packet_metrics_path": str(packet_dir / "packet_metrics.json"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
