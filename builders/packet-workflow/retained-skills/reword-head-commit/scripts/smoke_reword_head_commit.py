#!/usr/bin/env python3
"""Smoke-test reword-head-commit through the express driver."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DRIVER_PATH = SCRIPT_DIR / "reword_head_commit.py"


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def main() -> int:
    smoke_root = Path(tempfile.gettempdir()) / "reword-head-commit-smoke"
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=smoke_root, prefix="workspace-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        run_git(repo, "init")
        run_git(repo, "config", "user.name", "Codex")
        run_git(repo, "config", "user.email", "codex@example.com")

        rules_path = repo / ".github" / "instructions" / "commit-message.instructions.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(
            "\n".join(
                [
                    "## Format",
                    "`<type>(<scope>): <subject>`",
                    "## Types",
                    "- `fix`",
                    "## Scopes",
                    "scope is required",
                    "## Subject Rules",
                    "50 characters or fewer",
                ]
            ),
            encoding="utf-8",
        )
        run_git(repo, "add", ".")
        run_git(repo, "commit", "--no-gpg-sign", "-m", "fix(repo): add commit rules")

        app_path = repo / "src" / "app.py"
        app_path.parent.mkdir(parents=True, exist_ok=True)
        app_path.write_text("print('hi')\n", encoding="utf-8")
        run_git(repo, "add", "src/app.py")
        run_git(repo, "commit", "--no-gpg-sign", "-m", "fix(app): seed")

        message_path = repo / ".codex" / "tmp" / "packet-workflow" / "reword-head-commit" / "message.txt"
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text("fix(app): rename seed\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(DRIVER_PATH), "--repo", str(repo), "--message-file", str(message_path), "--apply"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "smoke failed")
        payload = json.loads(result.stdout)
        persisted_eval_log = smoke_root / "eval-log.json"
        eval_log_path = Path(str(payload["evaluation_log_path"]))
        persisted_eval_log.write_text(eval_log_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "force_push_likely": payload["force_push_likely"],
                    "new_head": payload["new_head"],
                    "evaluation_log_path": str(persisted_eval_log),
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
