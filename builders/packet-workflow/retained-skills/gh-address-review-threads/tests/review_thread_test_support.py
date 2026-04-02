from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def pr_body() -> str:
    return "\n".join(
        [
            "## Why",
            "Make review-thread packet routing predictable.",
            "## What changed",
            "Cluster related threads and keep outdated ones out of worker routing.",
            "## How",
            "Build thread-batch packets before singleton thread packets.",
            "## Risk / Rollback",
            "Low risk.",
            "## Testing",
            "Run the packet builder against temp fixtures.",
        ]
    )


def reply_candidate(
    *,
    mode: str,
    comment_id: str | None,
    reason: str,
    managed: bool,
    adopted_unmarked_reply: bool,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "comment_id": comment_id,
        "reason": reason,
        "managed": managed,
        "adopted_unmarked_reply": adopted_unmarked_reply,
    }


def marker_conflict(
    *,
    phase: str,
    severity: str,
    reason: str,
    comment_ids: list[str],
    blocks_adoption: bool,
    blocks_update: bool,
    blocks_apply: bool,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "severity": severity,
        "reason": reason,
        "comment_ids": comment_ids,
        "blocks_adoption": blocks_adoption,
        "blocks_update": blocks_update,
        "blocks_apply": blocks_apply,
    }


def comment(
    *,
    comment_id: str,
    author_login: str,
    body: str,
    created_at: str,
    updated_at: str | None = None,
    managed_phase: str | None = None,
    managed_thread_id: str | None = None,
    has_exact_managed_marker: bool = False,
    is_self: bool | None = None,
) -> dict[str, Any]:
    return {
        "id": comment_id,
        "author_login": author_login,
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
        "managed_phase": managed_phase,
        "managed_thread_id": managed_thread_id,
        "has_exact_managed_marker": has_exact_managed_marker,
        "is_self": author_login == "codex" if is_self is None else is_self,
        "url": f"https://example.invalid/comment/{comment_id}",
    }


def review_thread(
    *,
    thread_id: str,
    path: str,
    line: int,
    reviewer_login: str,
    reviewer_body: str,
    is_outdated: bool = False,
    reply_candidates: dict[str, Any] | None = None,
    marker_conflicts: list[dict[str, Any]] | None = None,
    comments: list[dict[str, Any]] | None = None,
    latest_self_reply: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reviewer_comment = {
        "id": f"review-{thread_id}",
        "author_login": reviewer_login,
        "created_at": "2026-03-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
        "url": f"https://example.invalid/thread/{thread_id}",
        "body": reviewer_body,
    }
    return {
        "thread_id": thread_id,
        "is_resolved": False,
        "is_outdated": is_outdated,
        "path": path,
        "line": line,
        "start_line": line,
        "diff_side": "RIGHT",
        "start_diff_side": "RIGHT",
        "original_line": line,
        "original_start_line": line,
        "resolved_by": None,
        "reviewer_login": reviewer_login,
        "reviewer_comment": reviewer_comment,
        "latest_reviewer_comment_at": reviewer_comment["updated_at"],
        "latest_self_reply": latest_self_reply,
        "reply_candidates": reply_candidates
        or {
            "ack": reply_candidate(
                mode="add",
                comment_id=None,
                reason="no_existing_ack_reply",
                managed=False,
                adopted_unmarked_reply=False,
            ),
            "complete": reply_candidate(
                mode="add",
                comment_id=None,
                reason="complete_never_adopts_unmarked_reply",
                managed=False,
                adopted_unmarked_reply=False,
            ),
        },
        "marker_conflicts": marker_conflicts or [],
        "comments": comments or [],
    }


def context_with_threads(tmp: Path, threads: list[dict[str, Any]]) -> dict[str, Any]:
    repo_root = tmp / "repo"
    (repo_root / ".github").mkdir(parents=True, exist_ok=True)
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "pull_request_template.md").write_text(
        "\n".join(["## Why", "## What changed", "## Testing"]),
        encoding="utf-8",
    )
    (repo_root / "src" / "app.py").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
    (repo_root / "src" / "helper.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (repo_root / "src" / "legacy.py").write_text("legacy\n", encoding="utf-8")

    return {
        "repo_root": str(repo_root),
        "repo_slug": "example/repo",
        "viewer_login": "codex",
        "pr": {
            "id": "PR_1",
            "number": 11,
            "title": "Fix packet routing",
            "url": "https://example.invalid/pr/11",
            "state": "OPEN",
            "headRefName": "feature/packets",
            "baseRefName": "main",
            "body": pr_body(),
            "closingIssuesReferences": [{"number": 55}],
        },
        "changed_files": ["src/app.py", "src/helper.py", "src/legacy.py"],
        "changed_file_groups": {
            "runtime": {"count": 3, "sample_files": ["src/app.py", "src/helper.py", "src/legacy.py"]},
            "automation": {"count": 0, "sample_files": []},
            "docs": {"count": 0, "sample_files": []},
            "tests": {"count": 0, "sample_files": []},
            "config": {"count": 0, "sample_files": []},
            "other": {"count": 0, "sample_files": []},
        },
        "diff_stat": " 3 files changed, 120 insertions(+), 25 deletions(-)",
        "rule_files": {},
        "expected_template_sections": [],
        "conversation_comments": [],
        "reviews": [],
        "threads": threads,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
