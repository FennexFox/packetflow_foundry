from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
SHARED_REWORD_SCRIPTS_DIR = SKILL_ROOT.parent / "reword-recent-commits" / "scripts"
AMBIGUOUS_MODULES = (
    "apply_reword_plan",
    "collect_commit_rules",
    "collect_recent_commits",
    "reword_head_commit",
    "reword_plan_contract",
)
for module_name in AMBIGUOUS_MODULES:
    sys.modules.pop(module_name, None)
for candidate in (str(TEST_DIR), str(SCRIPTS_DIR), str(SHARED_REWORD_SCRIPTS_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)
for candidate in (str(TEST_DIR), str(SCRIPTS_DIR), str(SHARED_REWORD_SCRIPTS_DIR)):
    sys.path.insert(0, candidate)
importlib.invalidate_caches()


def run_git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def make_repo() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp_dir = tempfile.TemporaryDirectory()
    repo = Path(temp_dir.name)
    run_git(repo, "init")
    run_git(repo, "config", "user.name", "Codex")
    run_git(repo, "config", "user.email", "codex@example.com")
    return temp_dir, repo


def commit_file(
    repo: Path,
    rel_path: str,
    content: str,
    message: str,
    *,
    author_name: str = "Codex",
    author_email: str = "codex@example.com",
    author_date: str = "2026-03-27T00:00:00Z",
    committer_name: str | None = None,
    committer_email: str | None = None,
    committer_date: str | None = None,
) -> str:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run_git(repo, "add", rel_path)
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = author_name
    env["GIT_AUTHOR_EMAIL"] = author_email
    env["GIT_AUTHOR_DATE"] = author_date
    env["GIT_COMMITTER_NAME"] = committer_name or author_name
    env["GIT_COMMITTER_EMAIL"] = committer_email or author_email
    env["GIT_COMMITTER_DATE"] = committer_date or author_date
    run_git(repo, "commit", "--no-gpg-sign", "-m", message, env=env)
    return run_git(repo, "rev-parse", "HEAD")


def write_rules_file(repo: Path, body: str) -> Path:
    path = repo / ".github" / "instructions" / "commit-message.instructions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
