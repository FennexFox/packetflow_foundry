from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from pr_create_contract import json_fingerprint, normalize_duplicate_summary


PR_TITLE_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"\([a-z0-9][a-z0-9-]*\): .+$"
)
GROUP_SAMPLE_LIMIT = 16
GH_STUB_STATE_ENV = "GH_CREATE_PR_GH_STUB_STATE"
DEFAULT_TEMPLATE_PATHS = [
    ".github/pull_request_template.md",
    "pull_request_template.md",
    "docs/pull_request_template.md",
]
NAMED_TEMPLATE_GLOBS = [
    ".github/PULL_REQUEST_TEMPLATE/*.md",
    "PULL_REQUEST_TEMPLATE/*.md",
    "docs/PULL_REQUEST_TEMPLATE/*.md",
]
ISSUE_REF_PATTERN = re.compile(r"#(?P<number>\d+)")


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
    if command[:2] == ["repo", "view"]:
        default_branch = str(state.get("default_branch") or "main")
        return json.dumps({"defaultBranchRef": {"name": default_branch}})
    if command[:2] == ["pr", "list"]:
        head = command[command.index("--head") + 1] if "--head" in command else ""
        prs = [
            dict(item)
            for item in state.get("existing_prs", [])
            if str(item.get("headRefName") or "") == head
        ]
        return json.dumps(prs)
    if command[:2] == ["pr", "view"]:
        target = None
        if len(command) >= 3 and not command[2].startswith("-"):
            target = command[2]
        pool = [dict(item) for item in state.get("existing_prs", [])]
        if target:
            for item in pool:
                if str(item.get("number")) == target or str(item.get("headRefName") or "") == target:
                    return json.dumps(item)
            raise subprocess.CalledProcessError(returncode=1, cmd=args, output="", stderr="PR not found")
        if len(pool) == 1:
            return json.dumps(pool[0])
        raise subprocess.CalledProcessError(returncode=1, cmd=args, output="", stderr="PR not found")
    if command[:2] == ["pr", "create"]:
        title = command[command.index("--title") + 1]
        body_file = Path(command[command.index("--body-file") + 1])
        base = command[command.index("--base") + 1]
        head = command[command.index("--head") + 1]
        repo_slug = state.get("repo_slug") or "owner/repo"
        number = int(state.get("next_pr_number") or 101)
        reviewers = []
        assignees = []
        labels = []
        milestone = None
        maintainer_can_modify = "--no-maintainer-edit" not in command
        draft = "--draft" in command
        index = 0
        while index < len(command):
            token = command[index]
            if token == "--reviewer":
                reviewers.append(command[index + 1])
                index += 2
                continue
            if token == "--assignee":
                assignees.append(command[index + 1])
                index += 2
                continue
            if token == "--label":
                labels.append(command[index + 1])
                index += 2
                continue
            if token == "--milestone":
                milestone = command[index + 1]
                index += 2
                continue
            index += 1
        created = {
            "number": number,
            "title": title,
            "body": body_file.read_text(encoding="utf-8").rstrip(),
            "headRefName": head,
            "baseRefName": base,
            "url": f"https://example.invalid/{repo_slug}/pull/{number}",
            "isDraft": draft,
            "labels": [{"name": value} for value in sorted(dict.fromkeys(labels))],
            "assignees": [{"login": value} for value in sorted({item.lower(): item.lower() for item in assignees}.values())],
            "reviewRequests": [{"requestedReviewer": {"login": value}} for value in sorted({item.lower(): item.lower() for item in reviewers}.values())],
            "milestone": ({"title": milestone} if milestone else None),
            "maintainerCanModify": maintainer_can_modify,
        }
        state.setdefault("existing_prs", []).append(created)
        state["next_pr_number"] = number + 1
        Path(state_path).write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return created["url"] + "\n"
    raise subprocess.CalledProcessError(returncode=1, cmd=args, output="", stderr="unsupported stubbed gh command")


def run_command(args: list[str], cwd: Path) -> str:
    stubbed = maybe_run_stubbed_gh(args)
    if stubbed is not None:
        return stubbed
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def run_git(args: list[str], cwd: Path) -> str:
    return run_command(["git", *args], cwd=cwd)


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def infer_repo_slug(repo_root: Path) -> str | None:
    try:
        remote = run_git(["config", "--get", "remote.origin.url"], cwd=repo_root).strip()
    except subprocess.CalledProcessError:
        return None
    if not remote:
        return None
    match = re.search(r"github\.com[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group("slug") if match else None


def git_rev_parse(repo_root: Path, ref: str) -> str | None:
    try:
        return run_git(["rev-parse", ref], cwd=repo_root).strip()
    except subprocess.CalledProcessError:
        return None


def current_branch(repo_root: Path) -> str | None:
    try:
        branch = run_git(["branch", "--show-current"], cwd=repo_root).strip()
    except subprocess.CalledProcessError:
        return None
    return branch or None


def branch_merge_base(repo_root: Path, branch: str | None) -> str | None:
    if not branch:
        return None
    try:
        value = run_git(["config", "--get", f"branch.{branch}.gh-merge-base"], cwd=repo_root).strip()
    except subprocess.CalledProcessError:
        return None
    return value or None


def default_branch_from_git(repo_root: Path) -> str | None:
    candidates = [
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        ["rev-parse", "--abbrev-ref", "origin/HEAD"],
    ]
    for args in candidates:
        try:
            value = run_git(args, cwd=repo_root).strip()
        except subprocess.CalledProcessError:
            continue
        if "/" in value:
            return value.split("/")[-1]
        if value:
            return value
    return None


def default_branch_from_gh(repo_root: Path, repo_slug: str | None) -> str | None:
    args = ["gh", "repo", "view", "--json", "defaultBranchRef"]
    if repo_slug:
        args.extend(["--repo", repo_slug])
    try:
        payload = json.loads(run_command(args, cwd=repo_root))
    except Exception:
        return None
    branch = payload.get("defaultBranchRef") or {}
    return str(branch.get("name") or "").strip() or None


def resolve_base_ref(repo_root: Path, repo_slug: str | None, branch: str | None, explicit_base: str | None) -> str | None:
    if explicit_base and explicit_base.strip():
        return explicit_base.strip()
    merge_base = branch_merge_base(repo_root, branch)
    if merge_base:
        return merge_base
    git_default = default_branch_from_git(repo_root)
    if git_default:
        return git_default
    return default_branch_from_gh(repo_root, repo_slug)


def local_head_oid(repo_root: Path, head_ref: str | None) -> str | None:
    if not head_ref:
        return None
    return git_rev_parse(repo_root, head_ref)


def remote_head_oid(repo_root: Path, head_ref: str | None) -> str | None:
    if not head_ref:
        return None
    for ref in (f"refs/remotes/origin/{head_ref}", f"origin/{head_ref}"):
        value = git_rev_parse(repo_root, ref)
        if value:
            return value
    return None


def git_revision_candidates(base_ref: str | None, head_ref: str | None) -> list[str]:
    if not base_ref or not head_ref:
        return []
    return [
        f"origin/{base_ref}..origin/{head_ref}",
        f"origin/{base_ref}..{head_ref}",
        f"{base_ref}..origin/{head_ref}",
        f"{base_ref}..{head_ref}",
    ]


def load_changed_files_between(repo_root: Path, base_ref: str | None, head_ref: str | None) -> list[str]:
    for revision_range in git_revision_candidates(base_ref, head_ref):
        try:
            output = run_git(["diff", "--name-only", revision_range], cwd=repo_root)
        except subprocess.CalledProcessError:
            continue
        return [normalize_path(line.strip()) for line in output.splitlines() if line.strip()]
    return []


def load_diff_stat_between(repo_root: Path, base_ref: str | None, head_ref: str | None) -> str | None:
    for revision_range in git_revision_candidates(base_ref, head_ref):
        try:
            output = run_git(["diff", "--stat", revision_range], cwd=repo_root).strip()
        except subprocess.CalledProcessError:
            continue
        if output:
            return output
    return None


def load_commit_subjects(repo_root: Path, base_ref: str | None, head_ref: str | None, *, limit: int = 12) -> list[str]:
    for revision_range in git_revision_candidates(base_ref, head_ref):
        try:
            output = run_git(["log", "--format=%s", f"-n{limit}", revision_range], cwd=repo_root)
        except subprocess.CalledProcessError:
            continue
        subjects = [line.strip() for line in output.splitlines() if line.strip()]
        if subjects:
            return subjects
    return []


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
        normalized = normalize_path(path)
        lower = normalized.lower()
        if (
            "/tests/" in lower
            or lower.startswith("tests/")
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
            or lower.startswith(".github/instructions/")
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
        elif lower.endswith(".cs") or lower.endswith(".dll") or lower.endswith(".py") or lower.endswith(".ts"):
            groups["runtime"].append(normalized)
        else:
            groups["other"].append(normalized)
    return groups


def sample_parent(path: str) -> str:
    normalized = normalize_path(path)
    return normalized.rsplit("/", 1)[0] if "/" in normalized else "."


def select_representative_files(paths: Iterable[str], limit: int = GROUP_SAMPLE_LIMIT) -> list[str]:
    ordered_paths: list[str] = []
    for path in paths:
        normalized = normalize_path(path)
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


def extract_issue_numbers(text: str | None) -> list[str]:
    if not text:
        return []
    seen: list[str] = []
    for match in ISSUE_REF_PATTERN.finditer(text):
        number = match.group("number")
        if number not in seen:
            seen.append(number)
    return seen


def select_pr_template(repo_root: Path) -> dict[str, Any]:
    default_candidates = [normalize_path(str(repo_root / path)) for path in DEFAULT_TEMPLATE_PATHS if (repo_root / path).is_file()]
    named_candidates: list[str] = []
    for pattern in NAMED_TEMPLATE_GLOBS:
        named_candidates.extend(
            normalize_path(str(path))
            for path in sorted(repo_root.glob(pattern))
            if path.is_file()
        )
    all_candidates = sorted(dict.fromkeys(default_candidates + named_candidates))
    selected_path: str | None = None
    status = "not_found"
    if len(default_candidates) == 1 and not named_candidates:
        selected_path = default_candidates[0]
        status = "selected"
    elif all_candidates:
        status = "ambiguous"
    sections = parse_markdown_headings(read_text_if_exists(Path(selected_path)) if selected_path else None)
    fingerprint = json_fingerprint(read_text_if_exists(Path(selected_path)) or "") if selected_path else ""
    return {
        "status": status,
        "selected_path": selected_path,
        "default_candidates": default_candidates,
        "named_template_candidates": named_candidates,
        "all_candidates": all_candidates,
        "sections": sections,
        "fingerprint": fingerprint,
    }


def template_file_paths(repo_root: Path, template_selection: dict[str, Any]) -> dict[str, str]:
    files = {
        "pull_request_instructions": ".github/instructions/pull-request.instructions.md",
        "commit_message_instructions": ".github/instructions/commit-message.instructions.md",
        "contributing": "CONTRIBUTING.md",
        "maintaining": "MAINTAINING.md",
    }
    result: dict[str, str] = {}
    selected_template = template_selection.get("selected_path")
    if selected_template:
        result["pull_request_template"] = normalize_path(selected_template)
    for key, rel_path in files.items():
        path = repo_root / rel_path
        if path.exists():
            result[key] = normalize_path(str(path))
    return result


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


def load_open_prs_for_head(repo_root: Path, repo_slug: str | None, head_ref: str) -> list[dict[str, Any]]:
    args = [
        "gh",
        "pr",
        "list",
        "--head",
        head_ref,
        "--state",
        "open",
        "--json",
        "number,url,headRefName,baseRefName,title,body,isDraft,labels,assignees,reviewRequests,milestone,maintainerCanModify",
    ]
    if repo_slug:
        args.extend(["--repo", repo_slug])
    payload = json.loads(run_command(args, cwd=repo_root))
    if not isinstance(payload, list):
        raise RuntimeError("gh pr list did not return a JSON array")
    return [dict(item) for item in payload if isinstance(item, dict)]


def duplicate_check_summary(repo_root: Path, repo_slug: str | None, head_ref: str) -> dict[str, Any]:
    matches = load_open_prs_for_head(repo_root, repo_slug, head_ref)
    if not matches:
        return normalize_duplicate_summary(
            {
                "status": "clear",
                "matched_repo_slug": repo_slug,
                "matched_head": head_ref,
                "existing_pr_count": 0,
            }
        )
    first = matches[0]
    return normalize_duplicate_summary(
        {
            "status": "existing-open-pr",
            "matched_repo_slug": repo_slug,
            "matched_head": head_ref,
            "existing_pr_number": first.get("number"),
            "existing_pr_url": first.get("url"),
            "existing_pr_count": len(matches),
        }
    )


def build_context(
    *,
    repo_root: Path,
    repo_slug: str | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
    reviewers: list[str] | None = None,
    assignees: list[str] | None = None,
    labels: list[str] | None = None,
    milestone: str | None = None,
    draft: bool = False,
    no_maintainer_edit: bool = False,
) -> dict[str, Any]:
    resolved_repo_slug = repo_slug or infer_repo_slug(repo_root)
    branch = current_branch(repo_root)
    resolved_head = (head_ref or branch or "").strip() or None
    resolved_base = resolve_base_ref(repo_root, resolved_repo_slug, branch, base_ref)
    local_oid = local_head_oid(repo_root, resolved_head)
    remote_oid = remote_head_oid(repo_root, resolved_head)
    changed_files = load_changed_files_between(repo_root, resolved_base, resolved_head)
    groups = classify_changed_files(changed_files)
    diff_stat = load_diff_stat_between(repo_root, resolved_base, resolved_head)
    commit_subjects = load_commit_subjects(repo_root, resolved_base, resolved_head)
    template_selection = select_pr_template(repo_root)
    rule_paths = template_file_paths(repo_root, template_selection)

    template_text = read_text_if_exists(Path(template_selection["selected_path"])) if template_selection.get("selected_path") else None
    instructions_text = read_text_if_exists(repo_root / ".github/instructions/pull-request.instructions.md")
    commit_instructions_text = read_text_if_exists(repo_root / ".github/instructions/commit-message.instructions.md")
    issue_hints = sorted(
        {
            *extract_issue_numbers(resolved_head),
            *extract_issue_numbers(" ".join(commit_subjects)),
        }
    )

    try:
        duplicate_hint = (
            duplicate_check_summary(repo_root, resolved_repo_slug, resolved_head)
            if resolved_repo_slug and resolved_head
            else normalize_duplicate_summary({"status": "repo-or-head-missing", "matched_repo_slug": resolved_repo_slug, "matched_head": resolved_head})
        )
    except Exception as exc:
        duplicate_hint = normalize_duplicate_summary(
            {
                "status": "unavailable",
                "matched_repo_slug": resolved_repo_slug,
                "matched_head": resolved_head,
                "existing_pr_count": 0,
                "error": str(exc),
            }
        )

    return {
        "skill_name": "gh-create-pr",
        "repo_root": str(repo_root),
        "repo_slug": resolved_repo_slug,
        "current_branch": branch,
        "resolved_head": resolved_head,
        "resolved_base": resolved_base,
        "local_head_oid": local_oid,
        "remote_head_oid": remote_oid,
        "changed_files": changed_files,
        "changed_files_fingerprint": json_fingerprint(changed_files),
        "changed_file_groups": summarize_groups(groups),
        "diff_stat": diff_stat,
        "recent_commit_subjects": commit_subjects,
        "rule_files": rule_paths,
        "template_selection": template_selection,
        "expected_template_sections": list(template_selection.get("sections") or []),
        "instruction_snippets": {
            "pull_request_title_rules_excerpt": first_heading_block(instructions_text, "## PR Title"),
            "pull_request_template_sections": parse_markdown_headings(template_text),
            "commit_types_excerpt": first_heading_block(commit_instructions_text, "## Types"),
        },
        "issue_reference_hints": {
            "numbers": issue_hints,
            "branch": resolved_head,
            "commit_subjects": commit_subjects,
        },
        "testing_signal_candidates": {
            "exact_commands": [],
            "supports_positive_testing_claims": False,
            "test_files_changed": int((summarize_groups(groups).get("tests") or {}).get("count", 0)) > 0,
        },
        "duplicate_check_hint": duplicate_hint,
        "create_options": {
            "reviewers": list(reviewers or []),
            "assignees": list(assignees or []),
            "labels": list(labels or []),
            "milestone": milestone,
            "draft": bool(draft),
            "no_maintainer_edit": bool(no_maintainer_edit),
        },
        "checks": {
            "repo_slug_resolved": bool(resolved_repo_slug),
            "base_resolved": bool(resolved_base),
            "remote_head_exists": bool(remote_oid),
            "local_remote_match": bool(local_oid and remote_oid and local_oid == remote_oid),
            "template_selected": template_selection.get("status") == "selected",
            "duplicate_hint_status": duplicate_hint.get("status"),
        },
        "counts": {
            "changed_files": len(changed_files),
            "task_packet_count": 4,
            "active_areas": sum(1 for value in summarize_groups(groups).values() if value.get("count", 0)),
        },
    }
