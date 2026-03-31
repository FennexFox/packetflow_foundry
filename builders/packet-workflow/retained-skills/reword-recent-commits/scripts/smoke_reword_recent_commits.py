#!/usr/bin/env python3
"""Smoke-test reword-recent-commits through the single driver."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from reword_runtime_paths import resolve_smoke_root


SCRIPT_DIR = Path(__file__).resolve().parent
DRIVER_PATH = SCRIPT_DIR / "reword_recent_commits.py"


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
    smoke_root = resolve_smoke_root(Path.cwd()) / "latest"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=smoke_root, prefix="workspace-") as tmp_dir:
        root = Path(tmp_dir)
        repo_root = root / "repo"
        repo_root.mkdir()
        create_repo(repo_root)

        prepare_result = run_python(
            [
                str(DRIVER_PATH),
                "--repo",
                str(repo_root),
                "--count",
                "2",
                "--prepare-only",
            ]
        )
        prepare_summary = json.loads(prepare_result.stdout)
        artifact_root = Path(str(prepare_summary["artifact_root"]))
        message_template_path = Path(str(prepare_summary["message_template_path"]))

        template = load_json(message_template_path)
        template["commits"][0]["new_message"] = "fix(core): rewrite seed"
        template["commits"][1]["new_message"] = "fix(parser): rewrite follow-up"
        message_template_path.write_text(
            json.dumps(template, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        apply_result = run_python(
            [
                str(DRIVER_PATH),
                "--repo",
                str(repo_root),
                "--count",
                "2",
                "--messages-file",
                str(message_template_path),
                "--apply",
            ]
        )
        apply_summary = json.loads(apply_result.stdout)

        build_result = load_json(artifact_root / "build-result.json")
        packet_dir = artifact_root / "packets"
        packet_metrics = load_json(packet_dir / "packet_metrics.json")
        if build_result.get("packet_metrics") != packet_metrics:
            raise RuntimeError("Smoke build result and packet_metrics.json disagree.")
        persisted_eval_log = smoke_root / "eval-log.json"
        eval_log_path = Path(str(apply_summary["evaluation_log_path"]))
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
