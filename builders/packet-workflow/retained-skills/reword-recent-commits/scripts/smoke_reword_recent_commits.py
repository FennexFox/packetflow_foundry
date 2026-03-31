#!/usr/bin/env python3
"""Smoke-test reword-recent-commits and print a compact JSON summary with status, packet_metrics, common_path_sufficient, and evaluation_log_path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_python(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-B", *args],
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
                "- `parser`",
            ]
        )
        + "\n",
    )
    write_text(repo_root / "src" / "parser.py", "print('seed')\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "--no-gpg-sign", "-m", "docs(repo): add commit rules"])

    write_text(repo_root / "src" / "parser.py", "print('seed')\nprint('next')\n")
    run_git(repo_root, ["add", "src/parser.py"])
    run_git(repo_root, ["commit", "--no-gpg-sign", "-m", "fix(core): seed"])

    write_text(repo_root / "docs" / "notes.md", "# Notes\n")
    run_git(repo_root, ["add", "docs/notes.md"])
    run_git(repo_root, ["commit", "--no-gpg-sign", "-m", "fix(parser): follow-up"])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        repo_root = root / "repo"
        repo_root.mkdir()
        create_repo(repo_root)

        rules_path = root / "rules.json"
        plan_path = root / "plan.json"
        raw_plan_path = root / "raw-plan.json"
        packet_dir = root / "packets"
        build_result_path = root / "build-result.json"
        validated_path = root / "validated.json"
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
                str(SCRIPT_DIR / "collect_recent_commits.py"),
                "--count",
                "2",
                "--repo",
                str(repo_root),
                "--rules",
                str(rules_path),
                "--output",
                str(plan_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "build_reword_packets.py"),
                "--rules",
                str(rules_path),
                "--plan",
                str(plan_path),
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
                str(plan_path),
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

        plan = load_json(plan_path)
        plan["commits"][0]["new_message"] = "fix(core): rewrite seed"
        plan["commits"][1]["new_message"] = "fix(parser): rewrite follow-up"
        raw_plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        run_python(
            [
                str(SCRIPT_DIR / "validate_reword_plan.py"),
                "--rules",
                str(rules_path),
                "--context",
                str(plan_path),
                "--plan",
                str(raw_plan_path),
                "--output",
                str(validated_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "apply_reword_plan.py"),
                "--context",
                str(plan_path),
                "--plan",
                str(validated_path),
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
        packet_metrics = load_json(packet_dir / "packet_metrics.json")
        if build_result.get("packet_metrics") != packet_metrics:
            raise RuntimeError("Smoke build result and packet_metrics.json disagree.")
        persisted_fd, persisted_path = tempfile.mkstemp(
            prefix="reword-recent-commits-smoke-",
            suffix="-eval-log.json",
        )
        os.close(persisted_fd)
        persisted_eval_log = Path(persisted_path)
        persisted_eval_log.write_text(eval_log_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        summary = {
            "status": "ok",
            "packet_metrics": packet_metrics,
            "common_path_sufficient": bool(build_result.get("common_path_sufficient")),
            "evaluation_log_path": str(persisted_eval_log),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
