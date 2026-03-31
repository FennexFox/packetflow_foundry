#!/usr/bin/env python3
"""Collect the latest n commits into a JSON plan for message rewording."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_builder_scripts_dir() -> Path:
    script_path = Path(__file__).resolve()
    searched: list[Path] = []
    seen: set[Path] = set()
    for base in script_path.parents:
        for candidate in (
            base / "builders" / "packet-workflow" / "scripts",
            base
            / ".codex"
            / "vendor"
            / "packetflow_foundry"
            / "builders"
            / "packet-workflow"
            / "scripts",
        ):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            searched.append(resolved)
            if resolved.is_dir():
                return resolved
    search_list = ", ".join(path.as_posix() for path in searched)
    raise SystemExit(
        "[ERROR] Missing packet-workflow builder scripts. "
        f"Searched: {search_list}"
    )


BUILDER_SCRIPTS_DIR = resolve_builder_scripts_dir()
if str(BUILDER_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(BUILDER_SCRIPTS_DIR))

from packet_workflow_versioning import (  # type: ignore  # noqa: E402
    classify_builder_compatibility,
    extract_profile_versioning,
    extract_skill_builder_versioning,
    format_runtime_warning,
    load_builder_versioning,
    load_json_document,
)
from reword_plan_contract import build_context_fingerprint, load_json, rules_reliability


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def retained_default_repo_profile_path() -> Path:
    return skill_root() / "profiles" / "default" / "profile.json"


def project_local_profile_candidates(repo_root: Path) -> list[Path]:
    repo_root = repo_root.resolve()
    return [
        repo_root / ".codex" / "project" / "profiles" / skill_root().name / "profile.json",
        repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json",
    ]


def default_repo_profile_path(repo_root: Path | None = None) -> Path:
    if repo_root is not None:
        for candidate in project_local_profile_candidates(repo_root):
            if candidate.is_file():
                return candidate.resolve()
    return retained_default_repo_profile_path()


def resolve_profile_path(profile_path: str | None, repo_root: Path | None = None) -> Path:
    if not profile_path:
        return default_repo_profile_path(repo_root)

    candidate = Path(profile_path)
    if candidate.is_absolute():
        resolved_candidates = [candidate.resolve()]
    else:
        resolved_candidates: list[Path] = []
        if repo_root is not None:
            resolved_candidates.append((repo_root / candidate).resolve())
        resolved_candidates.append((skill_root() / candidate).resolve())
    for resolved in resolved_candidates:
        if resolved.is_file():
            return resolved
    searched = ", ".join(path.as_posix() for path in resolved_candidates)
    raise RuntimeError(f"missing repo profile: {searched}")


def load_repo_profile_document(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError("repo profile must be a JSON object")
    return payload


def build_builder_compatibility(repo_profile: dict[str, Any]) -> dict[str, Any]:
    return classify_builder_compatibility(
        current_builder=load_builder_versioning(),
        skill_versioning=extract_skill_builder_versioning(
            load_json_document(skill_root() / "builder-spec.json")
        ),
        profile_versioning=extract_profile_versioning(repo_profile),
    )


def run_git(repo: Path, args: list[str], check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout


def detect_operation(git_dir: Path) -> str | None:
    markers = {
        "rebase": [git_dir / "rebase-merge", git_dir / "rebase-apply"],
        "cherry-pick": [git_dir / "CHERRY_PICK_HEAD"],
        "merge": [git_dir / "MERGE_HEAD"],
        "bisect": [git_dir / "BISECT_LOG"],
    }
    for name, paths in markers.items():
        if any(path.exists() for path in paths):
            return name
    return None


def shortstat_for_commit(repo: Path, commit: str) -> str:
    output = run_git(repo, ["show", "--shortstat", "--format=", commit]).strip().splitlines()
    return output[-1].strip() if output else ""


def files_for_commit(repo: Path, commit: str) -> list[str]:
    output = run_git(repo, ["show", "--format=", "--name-only", "--no-renames", commit])
    return [line.strip() for line in output.splitlines() if line.strip()]


def build_plan(repo: Path, count: int, rules: dict[str, object] | None = None) -> dict[str, object]:
    repo_root = Path(run_git(repo, ["rev-parse", "--show-toplevel"]).strip())
    git_dir = Path(run_git(repo_root, ["rev-parse", "--git-dir"]).strip())
    if not git_dir.is_absolute():
        git_dir = repo_root / git_dir

    branch = run_git(repo_root, ["branch", "--show-current"]).strip()
    head_commit = run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    commits_output = run_git(
        repo_root,
        ["rev-list", "--max-count", str(count), "--reverse", "HEAD"],
    ).strip()
    commit_hashes = [line.strip() for line in commits_output.splitlines() if line.strip()]
    if not commit_hashes:
        raise RuntimeError("no commits found")

    oldest_commit = commit_hashes[0]
    base_candidate = run_git(repo_root, ["rev-parse", f"{oldest_commit}^"], check=False).strip()
    base_commit = base_candidate if re.fullmatch(r"[0-9a-fA-F]{40}", base_candidate) else None

    commits: list[dict[str, object]] = []
    for index, commit in enumerate(commit_hashes, start=1):
        parents = run_git(repo_root, ["show", "-s", "--format=%P", commit]).strip().split()
        full_message = run_git(repo_root, ["show", "-s", "--format=%B", commit]).rstrip("\n")
        commits.append(
            {
                "index": index,
                "hash": commit,
                "short_hash": commit[:12],
                "parent_hashes": parents,
                "subject": run_git(repo_root, ["show", "-s", "--format=%s", commit]).strip(),
                "body": run_git(repo_root, ["show", "-s", "--format=%b", commit]).rstrip("\n"),
                "full_message": full_message,
                "author_name": run_git(repo_root, ["show", "-s", "--format=%an", commit]).strip(),
                "author_email": run_git(repo_root, ["show", "-s", "--format=%ae", commit]).strip(),
                "author_date": run_git(repo_root, ["show", "-s", "--format=%aI", commit]).strip(),
                "files": files_for_commit(repo_root, commit),
                "shortstat": shortstat_for_commit(repo_root, commit),
                "new_message": "",
            }
        )

    payload = {
        "repo_root": str(repo_root),
        "branch": branch,
        "detached_head": branch == "",
        "count": len(commit_hashes),
        "head_commit": head_commit,
        "base_commit": base_commit,
        "active_operation": detect_operation(git_dir),
        "commits": commits,
    }
    if isinstance(rules, dict):
        payload["rules_reliability"] = rules_reliability(rules)
        payload["context_fingerprint"] = build_context_fingerprint(payload, rules)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect the latest n commits into a JSON plan for rewording."
    )
    parser.add_argument("--count", type=int, required=True, help="Number of recent commits to collect.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON plan. Prints JSON to stdout when omitted.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository path. Defaults to the current directory.",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        help="Optional rules JSON from collect_commit_rules.py to attach rules_reliability and context_fingerprint.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Optional path to the active repo profile JSON. Relative paths resolve from the "
            "repo root first, then the skill root. When omitted, the collector prefers "
            "`.codex/project/profiles/<skill-name>/profile.json`, then "
            "`.codex/project/profiles/default/profile.json`, then the retained default scaffold."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        print("--count must be positive", file=sys.stderr)
        return 2

    try:
        repo_root = Path(args.repo).resolve()
        profile_path = resolve_profile_path(args.profile, repo_root)
        repo_profile = load_repo_profile_document(profile_path)
        rules = load_json(args.rules) if args.rules else None
        plan = build_plan(args.repo, args.count, rules)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"collect_recent_commits.py: {exc}", file=sys.stderr)
        return 1
    plan["repo_profile_name"] = repo_profile.get("name")
    plan["repo_profile_path"] = profile_path.as_posix()
    plan["repo_profile_summary"] = repo_profile.get("summary")
    plan["repo_profile"] = repo_profile
    plan["builder_compatibility"] = build_builder_compatibility(repo_profile)
    if plan["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(plan["builder_compatibility"]), file=sys.stderr)

    payload = json.dumps(plan, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        print(
            f"Wrote reword plan for {plan['count']} commits to {args.output}",
            file=sys.stdout,
        )
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


