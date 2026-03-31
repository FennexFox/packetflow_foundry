from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Iterable


PR_TITLE_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"\([a-z0-9][a-z0-9-]*\): .+$"
)
GROUP_SAMPLE_LIMIT = 16
GH_STUB_STATE_ENV = "GH_FIX_PR_WRITEUP_GH_STUB_STATE"


def maybe_run_stubbed_gh(args: list[str]) -> str | None:
    if not args or args[0] != "gh":
        return None
    state_path = os.environ.get(GH_STUB_STATE_ENV)
    if not state_path:
        return None
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    command = args[1:]
    if command[:2] == ["auth", "status"]:
        return "Logged in to github.com\n"
    if command[:2] == ["pr", "view"]:
        return json.dumps(state["pr"])
    if command[:2] == ["pr", "diff"] and "--name-only" in command:
        return "\n".join(state.get("changed_files", []))
    if command[:2] == ["pr", "edit"]:
        title = command[command.index("--title") + 1]
        body_file = command[command.index("--body-file") + 1]
        state["pr"]["title"] = title
        state["pr"]["body"] = Path(body_file).read_text(encoding="utf-8")
        Path(state_path).write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return ""
    raise subprocess.CalledProcessError(returncode=1, cmd=args, output="", stderr="unsupported stubbed gh command")


def run_command(args: list[str], cwd: Path) -> str:
    stubbed = maybe_run_stubbed_gh(args)
    if stubbed is not None:
        return stubbed
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        command_name = args[0] if args else "command"
        raise RuntimeError(f"{command_name} executable not found") from exc
    return completed.stdout


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def infer_repo_slug(repo_root: Path) -> str | None:
    try:
        remote = run_command(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_root,
        ).strip()
    except subprocess.CalledProcessError:
        return None

    if not remote:
        return None

    match = re.search(r"github\.com[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group("slug") if match else None


def parse_markdown_headings(markdown_text: str | None) -> list[str]:
    if not markdown_text:
        return []
    headings: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            headings.append(line[3:].strip())
    return headings


def classify_changed_files(paths: Iterable[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "runtime": [],
        "automation": [],
        "docs": [],
        "tests": [],
        "config": [],
        "other": [],
    }
    for path in paths:
        normalized = path.replace("\\", "/")
        lower = normalized.lower()
        if (
            "/tests/" in lower
            or lower.endswith("_test.py")
            or lower.endswith(".tests.cs")
            or lower.startswith(".github/scripts/tests/")
        ):
            groups["tests"].append(normalized)
            continue
        if (
            lower.startswith(".github/workflows/")
            or lower.startswith(".github/scripts/")
            or lower.startswith(".github/issue_template/")
        ):
            groups["automation"].append(normalized)
        elif lower.endswith(".md"):
            groups["docs"].append(normalized)
        elif (
            lower.endswith(".yml")
            or lower.endswith(".yaml")
            or lower.endswith(".toml")
            or lower.endswith(".json")
            or lower.endswith(".csproj")
            or lower.endswith(".props")
            or lower.endswith(".targets")
        ):
            groups["config"].append(normalized)
        elif lower.endswith(".cs") or lower.endswith(".dll"):
            groups["runtime"].append(normalized)
        else:
            groups["other"].append(normalized)
    return groups


def sample_parent(path: str) -> str:
    normalized = path.replace("\\", "/")
    return normalized.rsplit("/", 1)[0] if "/" in normalized else "."


def select_representative_files(paths: Iterable[str], limit: int = GROUP_SAMPLE_LIMIT) -> list[str]:
    ordered_paths: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized not in ordered_paths:
            ordered_paths.append(normalized)

    if len(ordered_paths) <= limit:
        return ordered_paths

    bucket_order: list[str] = []
    buckets: dict[str, list[str]] = {}
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


def summarize_groups(groups: dict[str, list[str]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, paths in groups.items():
        sample_files = select_representative_files(paths)
        result[name] = {
            "count": len(paths),
            "sample_files": sample_files,
            "omitted_file_count": max(len(paths) - len(sample_files), 0),
            "sample_strategy": "directory_round_robin",
        }
    return result


def load_pr_metadata(pr_number: int, repo_root: Path, repo_slug: str | None) -> dict:
    args = [
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--json",
        "number,title,body,headRefName,headRefOid,baseRefName,url,closingIssuesReferences",
    ]
    if repo_slug:
        args.extend(["--repo", repo_slug])
    return json.loads(run_command(args, cwd=repo_root))


def parse_changed_files_output(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_diff_too_large_error(exc: subprocess.CalledProcessError) -> bool:
    detail = "\n".join(
        part
        for part in (
            str(exc),
            (exc.stderr or "").strip(),
            (exc.output or "").strip(),
        )
        if part
    )
    return "PullRequest.diff too_large" in detail or "maximum number of lines" in detail


def load_pr_changed_files_via_api(pr_number: int, repo_root: Path, repo_slug: str) -> list[str]:
    output = run_command(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/pulls/{pr_number}/files",
            "--paginate",
            "--jq",
            ".[].filename",
        ],
        cwd=repo_root,
    )
    return parse_changed_files_output(output)


def load_pr_changed_files(pr_number: int, repo_root: Path, repo_slug: str | None) -> list[str]:
    args = ["gh", "pr", "diff", str(pr_number), "--name-only"]
    if repo_slug:
        args.extend(["--repo", repo_slug])
    try:
        output = run_command(args, cwd=repo_root)
    except subprocess.CalledProcessError as exc:
        if not repo_slug or not is_diff_too_large_error(exc):
            raise
        return load_pr_changed_files_via_api(pr_number, repo_root, repo_slug)
    return parse_changed_files_output(output)


def load_local_diff_stat(repo_root: Path, base_ref: str | None, head_ref: str | None) -> str | None:
    if not base_ref or not head_ref:
        return None

    candidates = [
        f"{base_ref}..{head_ref}",
        f"origin/{base_ref}..{head_ref}",
        f"{base_ref}..origin/{head_ref}",
        f"origin/{base_ref}..origin/{head_ref}",
    ]
    for revision_range in candidates:
        try:
            output = run_command(
                ["git", "diff", "--stat", revision_range],
                cwd=repo_root,
            ).strip()
        except subprocess.CalledProcessError:
            continue
        if output:
            return output
    return None


def template_file_paths(repo_root: Path) -> dict[str, str]:
    files = {
        "pull_request_instructions": ".github/instructions/pull-request.instructions.md",
        "pull_request_template": ".github/pull_request_template.md",
        "commit_message_instructions": ".github/instructions/commit-message.instructions.md",
        "contributing": "CONTRIBUTING.md",
        "maintaining": "MAINTAINING.md",
    }
    result: dict[str, str] = {}
    for key, rel_path in files.items():
        path = repo_root / rel_path
        if path.exists():
            result[key] = str(path)
    return result


def build_context(pr_number: int, repo_root: Path, repo_slug: str | None = None) -> dict:
    resolved_repo_slug = repo_slug or infer_repo_slug(repo_root)
    metadata = load_pr_metadata(pr_number, repo_root, resolved_repo_slug)
    changed_files = load_pr_changed_files(pr_number, repo_root, resolved_repo_slug)
    groups = classify_changed_files(changed_files)
    rule_paths = template_file_paths(repo_root)
    diff_stat = load_local_diff_stat(
        repo_root,
        metadata.get("baseRefName"),
        metadata.get("headRefName"),
    )

    template_text = read_text_if_exists(repo_root / ".github/pull_request_template.md")
    instructions_text = read_text_if_exists(
        repo_root / ".github/instructions/pull-request.instructions.md"
    )
    commit_instructions_text = read_text_if_exists(
        repo_root / ".github/instructions/commit-message.instructions.md"
    )

    return {
        "repo_root": str(repo_root),
        "repo_slug": resolved_repo_slug,
        "pr": metadata,
        "changed_files": changed_files,
        "changed_file_groups": summarize_groups(groups),
        "diff_stat": diff_stat,
        "rule_files": rule_paths,
        "expected_template_sections": parse_markdown_headings(template_text),
        "current_body_sections": parse_markdown_headings(metadata.get("body") or ""),
        "checks": {
            "title_matches_conventional_commit": bool(
                PR_TITLE_RE.match((metadata.get("title") or "").strip())
            ),
            "title_length": len((metadata.get("title") or "").strip()),
            "body_has_template_sections": bool(parse_markdown_headings(metadata.get("body") or "")),
            "has_issue_refs": bool(metadata.get("closingIssuesReferences")),
        },
        "instruction_snippets": {
            "pull_request_title_rules_excerpt": first_heading_block(
                instructions_text,
                "## PR Title",
            ),
            "pull_request_template_sections": parse_markdown_headings(template_text),
            "commit_types_excerpt": first_heading_block(
                commit_instructions_text,
                "## Types",
            ),
        },
    }


def first_heading_block(markdown_text: str | None, heading: str) -> str | None:
    if not markdown_text:
        return None
    lines = markdown_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()
