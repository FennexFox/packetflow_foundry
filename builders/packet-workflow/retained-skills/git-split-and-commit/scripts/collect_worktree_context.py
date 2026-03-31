#!/usr/bin/env python3
"""Collect the current working-tree state for packet-based commit planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)
HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<context>.*)$"
)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
TOKEN_STOPWORDS = {
    "github",
    "issue",
    "template",
    "maintaining",
    "readme",
    "docs",
    "doc",
    "tests",
    "test",
    "scripts",
    "script",
    "workflow",
    "workflows",
    "automation",
    "file",
    "files",
    "update",
    "updated",
    "changes",
    "change",
    "report",
    "reporting",
}
TOKEN_NORMALIZATION = {
    "performance": "perf",
    "perf": "perf",
    "telemetry": "telemetry",
    "comparison": "compare",
    "comparable": "compare",
    "comparisons": "compare",
    "reporting": "report",
    "reports": "report",
}
GROUP_SAMPLE_LIMIT = 16


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


def load_repo_profile(path: Path) -> dict[str, Any]:
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
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return result.stdout


def resolve_repo_root(repo: Path) -> Path:
    return Path(run_git(repo, ["rev-parse", "--show-toplevel"]).strip())


def normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_dir(repo_root: Path) -> Path:
    raw = Path(run_git(repo_root, ["rev-parse", "--git-dir"]).strip())
    return raw if raw.is_absolute() else (repo_root / raw)


def detect_operation(repo_root: Path) -> str | None:
    current_git_dir = git_dir(repo_root)
    markers = {
        "rebase": [current_git_dir / "rebase-merge", current_git_dir / "rebase-apply"],
        "cherry-pick": [current_git_dir / "CHERRY_PICK_HEAD"],
        "merge": [current_git_dir / "MERGE_HEAD"],
        "bisect": [current_git_dir / "BISECT_LOG"],
    }
    for name, paths in markers.items():
        if any(path.exists() for path in paths):
            return name
    return None


def branch_state(repo_root: Path) -> dict[str, Any]:
    branch = run_git(repo_root, ["branch", "--show-current"], check=False).strip()
    status_branch = run_git(repo_root, ["status", "--short", "--branch"], check=False)
    upstream = run_git(
        repo_root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    ).strip()
    ahead = 0
    behind = 0
    if upstream:
        counts = run_git(repo_root, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], check=False).strip()
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])
    return {
        "branch": branch,
        "detached_head": branch == "",
        "upstream_branch": upstream or None,
        "ahead_count": ahead,
        "behind_count": behind,
        "status_branch_line": status_branch.splitlines()[0] if status_branch.splitlines() else "",
    }


def parse_status(repo_root: Path, pathspecs: list[str]) -> tuple[list[dict[str, Any]], str]:
    args = ["status", "--porcelain=v1", "--untracked-files=all", "--ignored=no", "--branch"]
    if pathspecs:
        args.extend(["--", *pathspecs])
    output = run_git(repo_root, args, check=False)
    records: list[dict[str, Any]] = []
    branch_line = ""
    for line in output.splitlines():
        if line.startswith("## "):
            branch_line = line
            continue
        if len(line) < 4:
            continue
        xy = line[:2]
        raw_path = line[3:]
        path = raw_path
        original_path = None
        if " -> " in raw_path and any(marker in xy for marker in ("R", "C")):
            original_path, path = raw_path.split(" -> ", 1)
        records.append(
            {
                "xy": xy,
                "staged_status": xy[0],
                "unstaged_status": xy[1],
                "path": normalize_path(path.strip()),
                "original_path": normalize_path(original_path.strip()) if original_path else None,
            }
        )
    return records, branch_line


def classify_path(path: str) -> str:
    lower = normalize_path(path).lower()
    if (
        "/tests/" in lower
        or lower.endswith("_test.py")
        or lower.endswith(".tests.cs")
        or lower.endswith(".spec.ts")
        or lower.startswith(".github/scripts/tests/")
    ):
        return "tests"
    if (
        lower.startswith(".github/workflows/")
        or lower.startswith(".github/scripts/")
        or lower.startswith(".github/issue_template/")
        or lower.startswith(".github/instructions/")
    ):
        return "automation"
    if lower.endswith(".md") or lower.startswith("docs/"):
        return "docs"
    if lower.endswith((".yml", ".yaml", ".toml", ".json", ".csproj", ".props", ".targets", ".xml")):
        return "config"
    if lower.endswith((".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
        return "runtime"
    return "other"


def is_generated_file(path: str) -> bool:
    lowered = normalize_path(path).lower()
    return any(pattern.search(lowered) for pattern in GENERATED_FILE_PATTERNS)


def sample_parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def select_representative_files(paths: list[str], limit: int = GROUP_SAMPLE_LIMIT) -> list[str]:
    ordered_paths: list[str] = []
    for path in paths:
        if path not in ordered_paths:
            ordered_paths.append(path)
    if len(ordered_paths) <= limit:
        return ordered_paths

    buckets: dict[str, list[str]] = {}
    bucket_order: list[str] = []
    for path in ordered_paths:
        parent = sample_parent(path)
        if parent not in buckets:
            buckets[parent] = []
            bucket_order.append(parent)
        buckets[parent].append(path)

    selected: list[str] = []
    while len(selected) < limit:
        progressed = False
        for parent in bucket_order:
            bucket = buckets[parent]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    original_index = {path: index for index, path in enumerate(ordered_paths)}
    return sorted(selected, key=original_index.__getitem__)


def summarize_groups(paths: list[str]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[str]] = {
        "runtime": [],
        "automation": [],
        "docs": [],
        "tests": [],
        "config": [],
        "other": [],
    }
    for path in paths:
        grouped[classify_path(path)].append(path)

    summary: dict[str, dict[str, Any]] = {}
    for name, items in grouped.items():
        sample_files = select_representative_files(items)
        summary[name] = {
            "count": len(items),
            "sample_files": sample_files,
            "omitted_file_count": max(len(items) - len(sample_files), 0),
        }
    return summary


def classify_change_kind(record: dict[str, Any]) -> str:
    xy = str(record["xy"])
    if xy == "??":
        return "untracked"
    if "U" in xy:
        return "unmerged"
    if "R" in xy:
        return "renamed"
    if "C" in xy:
        return "copied"
    if "A" in xy:
        return "added"
    if "D" in xy:
        return "deleted"
    if "T" in xy:
        return "typechange"
    return "modified"


def raw_diff_against_head(repo_root: Path, path: str) -> str:
    return run_git(
        repo_root,
        [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--no-renames",
            "--binary",
            "--full-index",
            "--unified=0",
            "HEAD",
            "--",
            path,
        ],
        check=False,
    )


def numstat_against_head(repo_root: Path, path: str) -> tuple[int | None, int | None, bool]:
    output = run_git(
        repo_root,
        ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--numstat", "HEAD", "--", path],
        check=False,
    )
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return 0, 0, False
    parts = lines[-1].split("\t")
    if len(parts) < 3:
        return None, None, False
    if parts[0] == "-" and parts[1] == "-":
        return None, None, True
    return int(parts[0]), int(parts[1]), False


def is_probably_binary(path: Path) -> bool:
    if not path.is_file():
        return False
    sample = path.read_bytes()[:8192]
    return b"\x00" in sample


def normalize_token(token: str) -> str | None:
    lowered = token.lower()
    lowered = TOKEN_NORMALIZATION.get(lowered, lowered)
    if lowered in TOKEN_STOPWORDS:
        return None
    if len(lowered) < 3:
        return None
    return lowered


def identifier_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text):
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).replace("_", " ")
        for piece in expanded.split():
            normalized = normalize_token(piece)
            if normalized and normalized not in tokens:
                tokens.append(normalized)
    return tokens


def path_tokens(path: str) -> list[str]:
    return identifier_tokens(path.replace("/", " "))


def parse_patch_hunks(path: str, patch_text: str) -> list[dict[str, Any]]:
    lines = patch_text.splitlines()
    hunks: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        header = lines[index]
        if not header.startswith("@@ "):
            index += 1
            continue
        match = HUNK_HEADER_RE.match(header)
        if not match:
            index += 1
            continue

        body_lines: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            if lines[index].startswith("diff --git "):
                break
            body_lines.append(lines[index])
            index += 1

        removed_lines = [line[1:] for line in body_lines if line.startswith("-")]
        added_lines = [line[1:] for line in body_lines if line.startswith("+")]
        removed_digest = sha256_text("\n".join(removed_lines))
        added_digest = sha256_text("\n".join(added_lines))
        match_digest = sha256_text("\n".join(["removed", removed_digest, "added", added_digest]))
        hunk_id = "hunk-" + sha256_text(
            "\n".join(
                [
                    normalize_path(path),
                    header,
                    removed_digest,
                    added_digest,
                ]
            )
        )[:16]
        tokens = identifier_tokens(match.group("context") or "")
        for line in body_lines:
            if line.startswith(("+", "-")):
                for token in identifier_tokens(line[1:]):
                    if token not in tokens:
                        tokens.append(token)

        hunks.append(
            {
                "hunk_id": hunk_id,
                "match_digest": match_digest,
                "header": header,
                "old_start": int(match.group("old_start")),
                "old_count": int(match.group("old_count") or "1"),
                "new_start": int(match.group("new_start")),
                "new_count": int(match.group("new_count") or "1"),
                "context": (match.group("context") or "").strip(),
                "removed_digest": removed_digest,
                "added_digest": added_digest,
                "raw_body_lines": body_lines,
                "raw_patch": "\n".join([header, *body_lines]) + "\n",
                "tokens": tokens[:12],
            }
        )
    return hunks


def diff_header_text(patch_text: str) -> str:
    header_lines: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("@@ "):
            break
        header_lines.append(line)
    return ("\n".join(header_lines) + "\n") if header_lines else ""


def tracked_test_for_script(repo_root: Path, path: str) -> str | None:
    normalized = normalize_path(path)
    if not normalized.startswith(".github/scripts/") or normalized.startswith(".github/scripts/tests/"):
        return None
    stem = Path(normalized).stem
    candidate = repo_root / ".github/scripts/tests" / f"test_{stem}.py"
    return normalize_path(str(candidate.relative_to(repo_root))) if candidate.is_file() else None


def targeted_validation_candidates(repo_root: Path, changed_paths: list[str]) -> list[dict[str, Any]]:
    normalized_paths = [normalize_path(path) for path in changed_paths]
    changed_tests = sorted(
        {
            path
            for path in normalized_paths
            if path.startswith(".github/scripts/tests/test_") and path.endswith(".py")
        }
    )
    changed_scripts = sorted(
        {
            path
            for path in normalized_paths
            if path.startswith(".github/scripts/")
            and path.endswith(".py")
            and not path.startswith(".github/scripts/tests/")
        }
    )
    docs_only = all(
        classify_path(path) in {"docs", "config", "other"}
        and not path.startswith(".github/scripts/")
        and not path.startswith(".github/workflows/")
        for path in normalized_paths
    )
    if docs_only:
        return []

    candidates: list[dict[str, Any]] = []
    seen_commands: set[str] = set()
    for test_path in changed_tests:
        command = (
            f'python -m unittest discover -s .github/scripts/tests -p "{Path(test_path).name}"'
        )
        if command not in seen_commands:
            candidates.append(
                {
                    "command": command,
                    "reason": f"Changed test file {test_path}.",
                    "paths": [test_path],
                }
            )
            seen_commands.add(command)

    if not changed_tests and changed_scripts:
        mapped_tests = [tracked_test_for_script(repo_root, path) for path in changed_scripts]
        if all(mapped_tests):
            for script_path, test_path in zip(changed_scripts, mapped_tests):
                command = (
                    f'python -m unittest discover -s .github/scripts/tests -p "{Path(str(test_path)).name}"'
                )
                if command in seen_commands:
                    continue
                candidates.append(
                    {
                        "command": command,
                        "reason": f"Changed script {script_path} with matching test {test_path}.",
                        "paths": [script_path, str(test_path)],
                    }
                )
                seen_commands.add(command)
        else:
            command = 'python -m unittest discover -s .github/scripts/tests -p "test_*.py"'
            candidates.append(
                {
                    "command": command,
                    "reason": "Changed .github/scripts Python code without a complete one-to-one test mapping.",
                    "paths": changed_scripts,
                }
            )
            seen_commands.add(command)

    if not candidates and any(path.startswith(".github/workflows/") for path in normalized_paths):
        command = 'python -m unittest discover -s .github/scripts/tests -p "test_*.py"'
        candidates.append(
            {
                "command": command,
                "reason": "Changed GitHub workflow files that orchestrate automation tests.",
                "paths": [path for path in normalized_paths if path.startswith(".github/workflows/")],
            }
        )

    return candidates


def build_file_entry(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    path = normalize_path(str(record["path"]))
    absolute_path = repo_root / Path(path)
    change_kind = classify_change_kind(record)
    tracked = change_kind != "untracked"
    diff_text = raw_diff_against_head(repo_root, path) if tracked else ""
    insertions, deletions, binary_from_numstat = numstat_against_head(repo_root, path) if tracked else (None, None, False)
    binary = binary_from_numstat or (change_kind == "untracked" and is_probably_binary(absolute_path))

    entry: dict[str, Any] = {
        "path": path,
        "original_path": record.get("original_path"),
        "xy": record["xy"],
        "staged_status": record["staged_status"],
        "unstaged_status": record["unstaged_status"],
        "change_kind": change_kind,
        "tracked": tracked,
        "area": classify_path(path),
        "generated": is_generated_file(path),
        "binary": binary,
        "path_tokens": path_tokens(path),
        "file_fingerprint": "",
        "split_eligible": False,
        "hunks": [],
    }

    if tracked:
        entry["insertions"] = insertions
        entry["deletions"] = deletions
        entry["file_fingerprint"] = "sha256:" + sha256_text("\n".join([path, record["xy"], diff_text]))
    else:
        payload = absolute_path.read_bytes() if absolute_path.is_file() else b""
        entry["file_fingerprint"] = "sha256:" + sha256_bytes(payload)
        entry["size_bytes"] = len(payload)

    if tracked and change_kind == "modified" and not binary and diff_text.strip():
        hunks = parse_patch_hunks(path, diff_text)
        entry["hunks"] = hunks
        entry["split_eligible"] = bool(hunks)
        entry["diff_header_text"] = diff_header_text(diff_text)
    else:
        entry["diff_header_text"] = ""
    return entry


def parse_shortstat(shortstat: str | None) -> dict[str, int]:
    if not shortstat:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "churn": 0}
    files = re.search(r"(\d+)\s+files?\s+changed", shortstat)
    insertions = re.search(r"(\d+)\s+insertions?\(\+\)", shortstat)
    deletions = re.search(r"(\d+)\s+deletions?\(-\)", shortstat)
    changed = int(files.group(1)) if files else 0
    added = int(insertions.group(1)) if insertions else 0
    removed = int(deletions.group(1)) if deletions else 0
    return {
        "files_changed": changed,
        "insertions": added,
        "deletions": removed,
        "churn": added + removed,
    }


def build_worktree_fingerprint(head_commit: str, files: list[dict[str, Any]]) -> str:
    parts = [head_commit]
    for entry in sorted(files, key=lambda item: str(item["path"])):
        parts.append(str(entry["path"]))
        parts.append(str(entry["xy"]))
        parts.append(str(entry["file_fingerprint"]))
    return "sha256:" + sha256_text("\n".join(parts))


def build_worktree_context(repo: Path, pathspecs: list[str] | None = None) -> dict[str, Any]:
    repo_root = resolve_repo_root(repo)
    selected_pathspecs = [normalize_path(path) for path in (pathspecs or [])]
    branch_info = branch_state(repo_root)
    records, branch_line = parse_status(repo_root, selected_pathspecs)
    files = [build_file_entry(repo_root, record) for record in records]
    files.sort(key=lambda item: str(item["path"]))

    changed_paths = [str(item["path"]) for item in files]
    head_commit = run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    diff_shortstat = run_git(
        repo_root,
        ["diff", "--shortstat", "HEAD", "--", *selected_pathspecs] if selected_pathspecs else ["diff", "--shortstat", "HEAD"],
        check=False,
    ).strip()
    diff_stat = run_git(
        repo_root,
        ["diff", "--stat", "HEAD", "--", *selected_pathspecs] if selected_pathspecs else ["diff", "--stat", "HEAD"],
        check=False,
    ).strip()

    worktree_fingerprint = build_worktree_fingerprint(head_commit, files)
    validation_candidates = targeted_validation_candidates(repo_root, changed_paths)

    validation_commands = [
        {
            "command": item["command"],
            "reason": item["reason"],
            "paths": item.get("paths", []),
            "confidence": "high",
        }
        for item in validation_candidates
    ]

    return {
        "repo_root": str(repo_root),
        "input_scope": "all-local-changes",
        "pathspecs": selected_pathspecs,
        "head_commit": head_commit,
        "head": head_commit,
        "branch": branch_info["branch"],
        "detached_head": branch_info["detached_head"],
        "upstream_branch": branch_info["upstream_branch"],
        "ahead_count": branch_info["ahead_count"],
        "behind_count": branch_info["behind_count"],
        "status_branch_line": branch_line or branch_info["status_branch_line"],
        "branch_state": branch_info,
        "active_operation": detect_operation(repo_root),
        "worktree_fingerprint": worktree_fingerprint,
        "changed_paths": changed_paths,
        "changed_file_groups": summarize_groups(changed_paths),
        "diff_shortstat": diff_shortstat or None,
        "diff_stat": diff_stat or None,
        "validation_candidates": validation_candidates,
        "validation_commands": validation_commands,
        "shortstat": parse_shortstat(diff_shortstat),
        "files": files,
    }


def build_context(repo: Path, pathspecs: list[str] | None = None) -> dict[str, Any]:
    return build_worktree_context(repo, pathspecs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect the current working-tree state into a JSON artifact."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository path. Defaults to the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON artifact. Prints JSON to stdout when omitted.",
    )
    parser.add_argument(
        "--pathspec",
        action="append",
        default=[],
        help="Optional Git pathspec to limit the collected worktree surface. May be repeated.",
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
    try:
        repo_root = Path(args.repo).resolve()
        profile_path = resolve_profile_path(args.profile, repo_root)
        repo_profile = load_repo_profile(profile_path)
        payload = build_worktree_context(args.repo, args.pathspec)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"collect_worktree_context.py: {exc}", file=sys.stderr)
        return 1
    payload["repo_profile_name"] = repo_profile.get("name")
    payload["repo_profile_path"] = profile_path.as_posix()
    payload["repo_profile_summary"] = repo_profile.get("summary")
    payload["repo_profile"] = repo_profile
    payload["builder_compatibility"] = build_builder_compatibility(repo_profile)
    if payload["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(payload["builder_compatibility"]), file=sys.stderr)

    serialized = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
        print(f"Wrote worktree context to {args.output}")
    else:
        sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


