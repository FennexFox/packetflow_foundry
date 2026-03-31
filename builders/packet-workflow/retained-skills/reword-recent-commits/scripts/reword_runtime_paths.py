#!/usr/bin/env python3
"""Runtime path helpers for reword-recent-commits."""

from __future__ import annotations

import os
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


ARTIFACT_NAMESPACE = Path(".codex") / "tmp" / "packet-workflow" / "reword-recent-commits"
SMOKE_ROOT_RELATIVE = ARTIFACT_NAMESPACE / "smoke"
EXCLUDE_PATTERN = ".codex/tmp/"
TEMP_ROOT_ENV_VAR = "REWORD_RECENT_COMMITS_TEMP_ROOT"


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout.strip()


def resolve_repo_root(repo: Path) -> Path:
    return Path(run_git(repo, ["rev-parse", "--show-toplevel"])).resolve()


def resolve_git_metadata_path(repo_root: Path, relative_path: str) -> Path:
    resolved = Path(run_git(repo_root, ["rev-parse", "--git-path", relative_path]))
    if not resolved.is_absolute():
        resolved = resolve_repo_root(repo_root) / resolved
    return resolved.resolve()


def resolve_repo_path(repo_root: Path, relative_path: Path | str) -> Path:
    return (resolve_repo_root(repo_root) / Path(relative_path)).resolve()


def resolve_runtime_namespace_root(repo_root: Path) -> Path:
    return resolve_repo_path(repo_root, ARTIFACT_NAMESPACE)


def resolve_smoke_root(workspace_root: Path | None = None) -> Path:
    base_root = workspace_root.resolve() if workspace_root is not None else Path.cwd().resolve()
    smoke_root = (base_root / SMOKE_ROOT_RELATIVE).resolve()
    smoke_root.mkdir(parents=True, exist_ok=True)
    return smoke_root


def ensure_repo_codex_tmp_excluded(repo_root: Path) -> None:
    exclude_path = resolve_git_metadata_path(repo_root, "info/exclude")
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    existing_patterns = {line.strip() for line in existing.splitlines()}
    if EXCLUDE_PATTERN in existing_patterns:
        return
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    exclude_path.write_text(existing + prefix + EXCLUDE_PATTERN + "\n", encoding="utf-8")


def resolve_artifact_root(
    repo_root: Path,
    *,
    run_id: str,
    artifacts_dir: Path | None = None,
) -> Path:
    if artifacts_dir is not None:
        return artifacts_dir.expanduser().resolve()
    return (resolve_runtime_namespace_root(repo_root) / run_id).resolve()


def resolve_existing_artifact_root(
    repo_root: Path,
    *,
    messages_file: Path,
    artifacts_dir: Path | None = None,
) -> Path:
    if artifacts_dir is not None:
        return resolve_artifact_root(repo_root, run_id="unused", artifacts_dir=artifacts_dir)
    return messages_file.resolve().parent


def build_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def resolve_temp_root(
    repo_root: Path | None = None,
    *,
    cli_temp_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[Path, str]:
    if cli_temp_root is not None:
        return cli_temp_root.expanduser().resolve(), "cli"
    environment = env if env is not None else os.environ
    env_value = str(environment.get(TEMP_ROOT_ENV_VAR) or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve(), "env"
    base_root = resolve_repo_root(repo_root) if repo_root is not None else Path.cwd().resolve()
    return (
        Path.home()
        / ".codex"
        / "tmp"
        / "packet-workflow"
        / "reword-recent-commits"
        / "temp"
        / base_root.name
    ).resolve(), "home_codex_tmp"


def ensure_directory_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    file_descriptor, probe_name = tempfile.mkstemp(prefix="write-check-", dir=path)
    os.close(file_descriptor)
    Path(probe_name).unlink(missing_ok=True)


def create_temp_runtime_dir(temp_root_parent: Path) -> Path:
    ensure_directory_writable(temp_root_parent)
    return Path(tempfile.mkdtemp(prefix="reword-recent-commits-", dir=temp_root_parent)).resolve()
