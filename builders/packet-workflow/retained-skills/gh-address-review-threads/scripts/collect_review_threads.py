#!/usr/bin/env python3
"""Collect open PR review-thread context for packet-based review handling."""

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
from thread_action_contract import build_context_fingerprint, comment_sort_key


MARKER_RE = re.compile(
    r"\A<!--\s*codex:review-thread v1 phase=(ack|complete) thread=([A-Za-z0-9_:-]+)\s*-->\s*(?:\n|$)"
)
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

QUERY = """\
query(
  $owner: String!,
  $repo: String!,
  $number: Int!,
  $commentsCursor: String,
  $reviewsCursor: String,
  $threadsCursor: String
) {
  viewer {
    login
  }
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      id
      number
      title
      body
      url
      state
      headRefName
      baseRefName
      comments(first: 100, after: $commentsCursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          body
          createdAt
          updatedAt
          url
          author {
            login
          }
        }
      }
      reviews(first: 100, after: $reviewsCursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          state
          body
          submittedAt
          url
          author {
            login
          }
        }
      }
      reviewThreads(first: 100, after: $threadsCursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          diffSide
          startLine
          startDiffSide
          originalLine
          originalStartLine
          resolvedBy {
            login
          }
          comments(first: 100) {
            nodes {
              id
              body
              createdAt
              updatedAt
              url
              author {
                login
              }
            }
          }
        }
      }
    }
  }
}
"""


def decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def run_command(args: list[str], cwd: Path, stdin_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{args[0]} not found") from exc
    if result.returncode != 0:
        stderr = decode_text(result.stderr).strip()
        stdout = decode_text(result.stdout).strip()
        detail = stderr or stdout or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return decode_text(result.stdout)


def run_json(args: list[str], cwd: Path, stdin_text: str | None = None) -> dict[str, Any]:
    output = run_command(args, cwd=cwd, stdin_text=stdin_text)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse JSON from {' '.join(args)}: {exc}") from exc


def ensure_gh_auth(repo_root: Path) -> None:
    try:
        run_command(["gh", "auth", "status"], cwd=repo_root)
    except RuntimeError as exc:
        raise RuntimeError("gh auth status failed; run `gh auth login` first") from exc


def infer_repo_slug(repo_root: Path) -> str | None:
    try:
        remote = run_command(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_root,
        ).strip()
    except RuntimeError:
        remote = ""

    if remote:
        match = re.search(r"github\.com[:/](?P<slug>[^/]+/[^/.]+)(?:\.git)?$", remote)
        if match:
            return match.group("slug")

    try:
        payload = run_json(["gh", "repo", "view", "--json", "nameWithOwner"], cwd=repo_root)
    except RuntimeError:
        return None
    return str(payload.get("nameWithOwner") or "").strip() or None


def parse_markdown_headings(markdown_text: str | None) -> list[str]:
    if not markdown_text:
        return []
    return [line[3:].strip() for line in markdown_text.splitlines() if line.startswith("## ")]


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def classify_changed_files(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "runtime": [],
        "automation": [],
        "docs": [],
        "tests": [],
        "config": [],
        "other": [],
    }
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        lower = path.lower()
        if (
            "/tests/" in lower
            or lower.endswith("_test.py")
            or lower.endswith(".tests.cs")
            or lower.endswith(".spec.ts")
            or lower.startswith(".github/scripts/tests/")
        ):
            groups["tests"].append(path)
            continue
        if (
            lower.startswith(".github/workflows/")
            or lower.startswith(".github/scripts/")
            or lower.startswith(".github/issue_template/")
            or lower.startswith(".github/instructions/")
        ):
            groups["automation"].append(path)
            continue
        if lower.endswith(".md") or lower.startswith("docs/"):
            groups["docs"].append(path)
            continue
        if lower.endswith((".yml", ".yaml", ".toml", ".json", ".csproj", ".props", ".targets")):
            groups["config"].append(path)
            continue
        if lower.endswith((".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
            groups["runtime"].append(path)
            continue
        groups["other"].append(path)
    return groups


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


def summarize_groups(groups: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for name, paths in groups.items():
        sample_files = select_representative_files(paths)
        summary[name] = {
            "count": len(paths),
            "sample_files": sample_files,
            "omitted_file_count": max(len(paths) - len(sample_files), 0),
            "sample_strategy": "directory_round_robin",
        }
    return summary


def rule_file_paths(repo_root: Path) -> dict[str, str]:
    candidates = {
        "pull_request_instructions": ".github/instructions/pull-request.instructions.md",
        "pull_request_template": ".github/pull_request_template.md",
        "commit_message_instructions": ".github/instructions/commit-message.instructions.md",
        "copilot_instructions": ".github/copilot-instructions.md",
        "contributing": "CONTRIBUTING.md",
        "maintaining": "MAINTAINING.md",
    }
    result: dict[str, str] = {}
    for key, relative_path in candidates.items():
        path = repo_root / relative_path
        if path.exists():
            result[key] = str(path)
    return result


def load_pr_metadata(repo_root: Path, repo_slug: str | None) -> dict[str, Any]:
    fields = (
        "id,number,title,body,url,state,headRefName,baseRefName,"
        "author,changedFiles,closingIssuesReferences"
    )
    args = ["gh", "pr", "view", "--json", fields]
    return run_json(args, cwd=repo_root)


def parse_changed_files_output(output: str) -> list[str]:
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def is_diff_too_large_error(exc: RuntimeError) -> bool:
    detail = str(exc)
    return "PullRequest.diff too_large" in detail or "maximum number of lines" in detail


def load_changed_files_via_api(repo_root: Path, repo_slug: str, pr_number: int) -> list[str]:
    args = [
        "gh",
        "api",
        f"repos/{repo_slug}/pulls/{pr_number}/files",
        "--paginate",
        "--jq",
        ".[].filename",
    ]
    output = run_command(args, cwd=repo_root)
    return parse_changed_files_output(output)


def load_changed_files(repo_root: Path, repo_slug: str | None, pr_number: int) -> list[str]:
    args = ["gh", "pr", "diff", str(pr_number), "--name-only"]
    if repo_slug:
        args.extend(["--repo", repo_slug])
    try:
        output = run_command(args, cwd=repo_root)
    except RuntimeError as exc:
        if not repo_slug or not is_diff_too_large_error(exc):
            raise
        return load_changed_files_via_api(repo_root, repo_slug, pr_number)
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
            output = run_command(["git", "diff", "--stat", revision_range], cwd=repo_root).strip()
        except RuntimeError:
            continue
        if output:
            return output
    return None


def graphql_payload(
    repo_root: Path,
    repo_slug: str,
    pr_number: int,
    comments_cursor: str | None,
    reviews_cursor: str | None,
    threads_cursor: str | None,
) -> dict[str, Any]:
    owner, repo = repo_slug.split("/", 1)
    args = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={pr_number}",
    ]
    if comments_cursor:
        args.extend(["-F", f"commentsCursor={comments_cursor}"])
    if reviews_cursor:
        args.extend(["-F", f"reviewsCursor={reviews_cursor}"])
    if threads_cursor:
        args.extend(["-F", f"threadsCursor={threads_cursor}"])
    payload = run_json(args, cwd=repo_root, stdin_text=QUERY)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2, ensure_ascii=True))
    return payload


def parse_marker(body: str) -> tuple[str | None, str | None]:
    match = MARKER_RE.match(body.lstrip("\ufeff"))
    if not match:
        return None, None
    return match.group(1), match.group(2)


def comment_timestamp(comment: dict[str, Any]) -> str:
    return str(comment.get("updated_at") or comment.get("created_at") or "")


def exact_managed_comments(comments: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    selected = [
        comment
        for comment in comments
        if comment.get("is_self")
        and comment.get("managed_phase") == phase
        and comment.get("has_exact_managed_marker")
    ]
    selected.sort(key=comment_sort_key)
    return selected


def wrong_thread_managed_comments(comments: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    selected = [
        comment
        for comment in comments
        if comment.get("is_self")
        and comment.get("managed_phase") == phase
        and not comment.get("has_exact_managed_marker")
    ]
    selected.sort(key=comment_sort_key)
    return selected


def normalize_comment(raw_comment: dict[str, Any], viewer_login: str, thread_id: str) -> dict[str, Any]:
    body = str(raw_comment.get("body") or "")
    author = (raw_comment.get("author") or {}).get("login")
    phase, marker_thread = parse_marker(body)
    exact_managed = bool(phase and marker_thread == thread_id)
    return {
        "id": raw_comment.get("id"),
        "body": body,
        "created_at": raw_comment.get("createdAt"),
        "updated_at": raw_comment.get("updatedAt"),
        "url": raw_comment.get("url"),
        "author_login": author,
        "is_self": author == viewer_login,
        "managed_phase": phase,
        "managed_thread_id": marker_thread,
        "has_exact_managed_marker": exact_managed,
    }


def build_reply_candidates(
    comments: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, str | None]:
    reviewer_comments = [comment for comment in comments if not comment.get("is_self")]
    latest_reviewer_at = max((comment_timestamp(comment) for comment in reviewer_comments), default=None)

    managed_ack = exact_managed_comments(comments, "ack")
    managed_complete = exact_managed_comments(comments, "complete")
    wrong_thread_ack = wrong_thread_managed_comments(comments, "ack")
    wrong_thread_complete = wrong_thread_managed_comments(comments, "complete")

    self_comments = [comment for comment in comments if comment.get("is_self")]
    latest_self_reply = max(self_comments, key=comment_sort_key) if self_comments else None

    adoptable_ack = [
        comment
        for comment in self_comments
        if not comment.get("managed_phase")
        and (latest_reviewer_at is None or comment_timestamp(comment) > latest_reviewer_at)
    ]
    adoptable_ack.sort(key=comment_sort_key)

    marker_conflicts: list[dict[str, Any]] = []
    if len(managed_ack) > 1:
        marker_conflicts.append(
            {
                "phase": "ack",
                "severity": "warning",
                "reason": "duplicate_exact_managed_replies",
                "comment_ids": [str(comment["id"]) for comment in managed_ack[:-1]],
                "blocks_adoption": False,
                "blocks_update": False,
                "blocks_apply": False,
            }
        )
    if len(managed_complete) > 1:
        marker_conflicts.append(
            {
                "phase": "complete",
                "severity": "warning",
                "reason": "duplicate_exact_managed_replies",
                "comment_ids": [str(comment["id"]) for comment in managed_complete[:-1]],
                "blocks_adoption": False,
                "blocks_update": False,
                "blocks_apply": False,
            }
        )
    if len(adoptable_ack) > 1 and not managed_ack:
        marker_conflicts.append(
            {
                "phase": "ack",
                "severity": "adoption-blocking",
                "reason": "multiple_unmarked_replies_after_latest_reviewer",
                "comment_ids": [str(comment["id"]) for comment in adoptable_ack],
                "blocks_adoption": True,
                "blocks_update": False,
                "blocks_apply": False,
            }
        )
    if wrong_thread_ack:
        marker_conflicts.append(
            {
                "phase": "ack",
                "severity": "hard-stop",
                "reason": "wrong_thread_managed_marker",
                "comment_ids": [str(comment["id"]) for comment in wrong_thread_ack],
                "blocks_adoption": True,
                "blocks_update": True,
                "blocks_apply": True,
            }
        )
    if wrong_thread_complete:
        marker_conflicts.append(
            {
                "phase": "complete",
                "severity": "hard-stop",
                "reason": "wrong_thread_managed_marker",
                "comment_ids": [str(comment["id"]) for comment in wrong_thread_complete],
                "blocks_adoption": True,
                "blocks_update": True,
                "blocks_apply": True,
            }
        )
    marker_conflicts.sort(
        key=lambda item: (
            str(item.get("phase") or ""),
            str(item.get("severity") or ""),
            str(item.get("reason") or ""),
            list(item.get("comment_ids", [])),
        )
    )

    if managed_ack:
        ack_candidate = {
            "mode": "update",
            "comment_id": managed_ack[-1]["id"],
            "reason": "exact_managed_reply",
            "managed": True,
            "adopted_unmarked_reply": False,
        }
    elif adoptable_ack:
        ack_candidate = {
            "mode": "update",
            "comment_id": adoptable_ack[-1]["id"],
            "reason": "adopt_latest_unmarked_reply_after_reviewer",
            "managed": False,
            "adopted_unmarked_reply": True,
        }
    else:
        ack_candidate = {
            "mode": "add",
            "comment_id": None,
            "reason": "no_existing_ack_reply",
            "managed": False,
            "adopted_unmarked_reply": False,
        }

    if managed_complete:
        complete_candidate = {
            "mode": "update",
            "comment_id": managed_complete[-1]["id"],
            "reason": "exact_managed_reply",
            "managed": True,
            "adopted_unmarked_reply": False,
        }
    else:
        complete_candidate = {
            "mode": "add",
            "comment_id": None,
            "reason": "complete_never_adopts_unmarked_reply",
            "managed": False,
            "adopted_unmarked_reply": False,
        }

    return {
        "ack": ack_candidate,
        "complete": complete_candidate,
    }, marker_conflicts, latest_self_reply, latest_reviewer_at


def summarize_thread(thread: dict[str, Any], viewer_login: str) -> dict[str, Any]:
    thread_id = str(thread.get("id"))
    comments = [
        normalize_comment(raw_comment, viewer_login=viewer_login, thread_id=thread_id)
        for raw_comment in (thread.get("comments", {}) or {}).get("nodes", [])
    ]
    comments.sort(key=comment_timestamp)
    reviewer_comments = [comment for comment in comments if not comment.get("is_self")]
    reviewer_comment = reviewer_comments[0] if reviewer_comments else (comments[0] if comments else None)
    reply_candidates, marker_conflicts, latest_self_reply, latest_reviewer_at = build_reply_candidates(comments)

    return {
        "thread_id": thread_id,
        "is_resolved": bool(thread.get("isResolved")),
        "is_outdated": bool(thread.get("isOutdated")),
        "path": str(thread.get("path") or ""),
        "line": thread.get("line"),
        "start_line": thread.get("startLine"),
        "diff_side": thread.get("diffSide"),
        "start_diff_side": thread.get("startDiffSide"),
        "original_line": thread.get("originalLine"),
        "original_start_line": thread.get("originalStartLine"),
        "resolved_by": (thread.get("resolvedBy") or {}).get("login"),
        "reviewer_login": reviewer_comment.get("author_login") if reviewer_comment else None,
        "reviewer_comment": reviewer_comment,
        "latest_reviewer_comment_at": latest_reviewer_at,
        "latest_self_reply": latest_self_reply,
        "reply_candidates": reply_candidates,
        "marker_conflicts": marker_conflicts,
        "comments": comments,
    }


def fetch_review_context(repo_root: Path) -> dict[str, Any]:
    ensure_gh_auth(repo_root)
    repo_slug = infer_repo_slug(repo_root)
    pr = load_pr_metadata(repo_root, repo_slug)
    if not pr.get("number"):
        raise RuntimeError("no open pull request is associated with the current branch")
    if repo_slug is None:
        raise RuntimeError("could not infer the GitHub repository slug for the current repo")

    changed_files = load_changed_files(repo_root, repo_slug, int(pr["number"]))
    group_summary = summarize_groups(classify_changed_files(changed_files))
    diff_stat = load_local_diff_stat(
        repo_root,
        str(pr.get("baseRefName") or ""),
        str(pr.get("headRefName") or ""),
    )

    comments_cursor = None
    reviews_cursor = None
    threads_cursor = None
    conversation_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    threads: list[dict[str, Any]] = []
    viewer_login = ""

    while True:
        payload = graphql_payload(
            repo_root=repo_root,
            repo_slug=repo_slug,
            pr_number=int(pr["number"]),
            comments_cursor=comments_cursor,
            reviews_cursor=reviews_cursor,
            threads_cursor=threads_cursor,
        )
        data = payload["data"]
        viewer_login = str((data.get("viewer") or {}).get("login") or viewer_login)
        pr_payload = (data.get("repository") or {}).get("pullRequest") or {}
        comments_conn = pr_payload.get("comments") or {}
        reviews_conn = pr_payload.get("reviews") or {}
        threads_conn = pr_payload.get("reviewThreads") or {}

        conversation_comments.extend(comments_conn.get("nodes") or [])
        reviews.extend(reviews_conn.get("nodes") or [])
        threads.extend(threads_conn.get("nodes") or [])

        comments_cursor = comments_conn.get("pageInfo", {}).get("endCursor") if comments_conn.get("pageInfo", {}).get("hasNextPage") else None
        reviews_cursor = reviews_conn.get("pageInfo", {}).get("endCursor") if reviews_conn.get("pageInfo", {}).get("hasNextPage") else None
        threads_cursor = threads_conn.get("pageInfo", {}).get("endCursor") if threads_conn.get("pageInfo", {}).get("hasNextPage") else None
        if not (comments_cursor or reviews_cursor or threads_cursor):
            break

    normalized_comments = [
        {
            "id": comment.get("id"),
            "body": comment.get("body"),
            "created_at": comment.get("createdAt"),
            "updated_at": comment.get("updatedAt"),
            "url": comment.get("url"),
            "author_login": (comment.get("author") or {}).get("login"),
        }
        for comment in conversation_comments
    ]
    normalized_reviews = [
        {
            "id": review.get("id"),
            "state": review.get("state"),
            "body": review.get("body"),
            "submitted_at": review.get("submittedAt"),
            "url": review.get("url"),
            "author_login": (review.get("author") or {}).get("login"),
        }
        for review in reviews
    ]
    normalized_threads = [summarize_thread(thread, viewer_login=viewer_login) for thread in threads]

    template_text = read_text_if_exists(repo_root / ".github/pull_request_template.md")
    context = {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "viewer_login": viewer_login,
        "pr": pr,
        "changed_files": changed_files,
        "changed_file_groups": group_summary,
        "diff_stat": diff_stat,
        "rule_files": rule_file_paths(repo_root),
        "expected_template_sections": parse_markdown_headings(template_text),
        "conversation_comments": normalized_comments,
        "reviews": normalized_reviews,
        "threads": normalized_threads,
    }
    context["context_fingerprint"] = build_context_fingerprint(context)
    return context


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect open PR review-thread context for token-efficient packet analysis."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root that contains the open pull request branch.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Prints JSON to stdout when omitted.",
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
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    try:
        profile_path = resolve_profile_path(args.profile, repo_root)
        repo_profile = load_repo_profile(profile_path)
        context = fetch_review_context(repo_root)
    except RuntimeError as exc:
        print(f"collect_review_threads.py: {exc}", file=sys.stderr)
        return 1
    context["repo_profile_name"] = repo_profile.get("name")
    context["repo_profile_path"] = profile_path.as_posix()
    context["repo_profile_summary"] = repo_profile.get("summary")
    context["repo_profile"] = repo_profile
    context["builder_compatibility"] = build_builder_compatibility(repo_profile)
    if context["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(context["builder_compatibility"]), file=sys.stderr)

    payload = json.dumps(context, indent=2, ensure_ascii=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


