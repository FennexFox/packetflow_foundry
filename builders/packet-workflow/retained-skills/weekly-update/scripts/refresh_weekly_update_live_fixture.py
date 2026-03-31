#!/usr/bin/env python3
"""Maintainer-only helper to refresh weekly-update test fixtures from live repo evidence."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from weekly_update_lib import (
    empty_plan_sections,
    default_repo_profile_path,
    extract_release_tag,
    fetch_pr_detail,
    fetch_review_comments,
    get_repo_metadata,
    isoformat_utc,
    label_names,
    link_releases_to_issues,
    list_issues,
    list_merged_pr_summaries,
    list_releases,
    list_workflow_runs,
    load_repo_profile,
    load_state_marker,
    parse_iso8601,
    resolve_repo_root,
    resolve_profile_path,
    select_reporting_window,
    short_markdown_summary,
    title_prefix,
    utc_now,
    verify_gh_auth,
    weekly_update_runtime_settings,
    window_contains,
    write_json,
    build_pr_lineage,
    build_issue_linkage_set,
    classify_issue,
)


def default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def parse_args() -> argparse.Namespace:
    fixture_dir = default_fixture_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, help="Repository root to inspect.")
    parser.add_argument("--sample-output", default=str(fixture_dir / "weekly_update_sample.json"), help="Output path for the refreshed live sample fixture.")
    parser.add_argument("--plan-dir", default=str(fixture_dir), help="Directory for paired plan fixtures.")
    parser.add_argument("--skip-plan-fixtures", action="store_true", help="Refresh only the live sample fixture.")
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
    parser.add_argument("--state-file", help="Optional state marker path override.")
    parser.add_argument("--window-days", type=int, default=7, help="Window size to use when no state marker is reused.")
    parser.add_argument("--now-utc", help="Optional deterministic ISO8601 UTC timestamp override.")
    parser.add_argument("--dry-run", action="store_true", help="Print the refresh summary without writing fixture files.")
    return parser.parse_args()


def trim_fixture_text(text: str | None, *, limit: int = 4000) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 15].rstrip() + "\n[truncated]"


def fixture_state_marker(state_marker: dict[str, Any] | None, reporting_window: dict[str, Any]) -> dict[str, Any] | None:
    if reporting_window.get("source") != "state_marker":
        return None
    marker = dict(state_marker or {})
    window_end = str(marker.get("window_end_utc") or marker.get("completed_at_utc") or reporting_window.get("start_utc") or "").strip()
    return {"window_end_utc": window_end} if window_end else None


def normalize_release_fixture(release: dict[str, Any], release_issue_linkage: dict[str, list[int]]) -> dict[str, Any]:
    issue_numbers = release_issue_linkage.get(str(release.get("tag_name") or ""), [])
    payload = {
        "tag_name": str(release.get("tag_name") or ""),
        "published_at": str(release.get("published_at") or ""),
    }
    if issue_numbers:
        payload["release_issue_number"] = int(issue_numbers[0])
    return payload


def normalize_pr_fixture(pr: dict[str, Any], pr_lineage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "number": int(pr["number"]),
        "title": str(pr.get("title") or ""),
        "base_ref_name": str(pr.get("base_ref_name") or pr.get("baseRefName") or ""),
        "merged_at": str(pr.get("merged_at") or pr.get("mergedAt") or ""),
        "linked_issue_numbers": list(pr.get("linked_issue_numbers") or []),
        "shipped_change_bullets": list(pr.get("shipped_change_bullets") or []),
        "review_followups": list(pr.get("risk_bullets") or []),
    }
    root = (pr_lineage.get(str(pr["number"])) or {}).get("root_top_level_pr")
    if root is not None:
        payload["absorbed_into"] = int(root)
    return payload


def normalize_issue_fixture(issue: dict[str, Any], linked_from_pr_numbers: list[int]) -> dict[str, Any]:
    payload = {
        "number": int(issue["number"]),
        "title": str(issue.get("title") or ""),
        "body": trim_fixture_text(issue.get("body")),
        "labels": label_names(issue),
        "state": str(issue.get("state") or "").upper(),
        "created_at": str(issue.get("createdAt") or ""),
        "updated_at": str(issue.get("updatedAt") or ""),
    }
    if linked_from_pr_numbers:
        payload["linked_from_pr_numbers"] = linked_from_pr_numbers
    return payload


def serialize_review_comment(comment: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "id": int(comment["id"]),
        "body": trim_fixture_text(comment.get("body"), limit=1200),
        "author": str((comment.get("user") or {}).get("login") or comment.get("author") or ""),
        "created_at": str(comment.get("created_at") or ""),
        "in_reply_to_id": comment.get("in_reply_to_id"),
        "path": comment.get("path"),
    }
    return payload


def build_review_threads(pr_number: int, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots = [comment for comment in comments if comment.get("in_reply_to_id") is None]
    replies_by_root: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        if comment.get("in_reply_to_id") is not None:
            replies_by_root[int(comment["in_reply_to_id"])].append(comment)
    threads: list[dict[str, Any]] = []
    for root in sorted(roots, key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0))):
        thread_comments = [serialize_review_comment(root)]
        thread_comments.extend(
            serialize_review_comment(reply)
            for reply in sorted(replies_by_root.get(int(root["id"]), []), key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)))
        )
        threads.append({"pr_number": pr_number, "comments": thread_comments})
    return threads


def normalize_workflow_run_fixture(run: dict[str, Any]) -> dict[str, Any]:
    run_id = int(run.get("databaseId") or 0)
    return {
        "databaseId": run_id,
        "workflowName": str(run.get("workflowName") or ""),
        "conclusion": str(run.get("conclusion") or ""),
        "status": str(run.get("status") or ""),
        "event": str(run.get("event") or ""),
        "headBranch": str(run.get("headBranch") or ""),
        "headSha": str(run.get("headSha") or ""),
        "createdAt": str(run.get("createdAt") or ""),
        "updatedAt": str(run.get("updatedAt") or ""),
        "url": f"https://example.invalid/run/{run_id}",
    }


def build_plan_fixtures(*, context_id: str, context_fingerprint: str, reporting_window: dict[str, Any]) -> dict[str, dict[str, Any]]:
    base = {
        "context_id": context_id,
        "context_fingerprint": context_fingerprint,
        "reporting_window": reporting_window,
        "selected_packets": ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"],
        "sections": empty_plan_sections(),
    }
    return {
        "weekly_update_plan_ready.json": {
            **base,
            "overall_confidence": "medium",
            "stop_reasons": [],
            "allow_marker_update": True,
        },
        "weekly_update_plan_low.json": {
            **base,
            "overall_confidence": "low",
            "stop_reasons": [],
            "allow_marker_update": False,
        },
        "weekly_update_plan_reread.json": {
            **base,
            "overall_confidence": "medium",
            "stop_reasons": ["raw reread exception unresolved"],
            "allow_marker_update": False,
            "unresolved_raw_reread_candidate_ids": ["fixture-reread-candidate"],
        },
    }


def collect_live_fixture_payload(
    *,
    repo_root: Path,
    profile: str | None,
    state_file: str | None,
    window_days: int,
    now_utc: str | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    profile_path = resolve_profile_path(profile, repo_root=repo_root)
    repo_profile = load_repo_profile(profile_path)
    runtime_settings = weekly_update_runtime_settings(repo_profile)
    verify_gh_auth(repo_root)
    repo_meta = get_repo_metadata(repo_root)
    marker, marker_warnings = load_state_marker(Path(state_file).resolve()) if state_file else (None, [])
    current_now = parse_iso8601(now_utc) or utc_now()
    reporting_window = select_reporting_window(now_utc=current_now, window_days=window_days, state_marker=marker)
    window_start = parse_iso8601(reporting_window["start_utc"])
    window_end = parse_iso8601(reporting_window["end_utc"])
    assert window_start is not None and window_end is not None

    releases, release_warnings = list_releases(repo_root, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)
    issues, issue_warnings = list_issues(repo_root, repo_meta["repo_slug"])
    pr_summaries, pr_summary_warnings = list_merged_pr_summaries(repo_root, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)
    merged_prs: list[dict[str, Any]] = []
    pr_warnings: list[str] = []
    for summary in pr_summaries:
        detail, detail_warnings = fetch_pr_detail(repo_root, repo_meta["repo_slug"], int(summary["number"]))
        merged_prs.append(detail)
        pr_warnings.extend(detail_warnings)
    top_level_prs, nested_prs, pr_lineage = build_pr_lineage(merged_prs, repo_meta["default_branch"])
    release_issue_linkage = link_releases_to_issues(
        releases,
        issues,
        release_title_re=runtime_settings["release_title_re"],
    )
    linked_issue_numbers = build_issue_linkage_set(top_level_prs)
    active_release_tags = {release["tag_name"] for release in releases}

    classified_issues = [
        item
        for item in (
            classify_issue(
                issue,
                window_start=window_start,
                window_end=window_end,
                linked_issue_numbers=linked_issue_numbers,
                active_release_tags=active_release_tags,
                release_title_re=runtime_settings["release_title_re"],
            )
            for issue in issues
        )
        if item["classification"] != "ignore"
    ]
    top_level_links: dict[int, list[int]] = defaultdict(list)
    for pr in top_level_prs:
        for issue_number in pr.get("linked_issue_numbers") or []:
            top_level_links[int(issue_number)].append(int(pr["number"]))

    selected_issue_numbers = {
        int(item["number"])
        for item in classified_issues
        if title_prefix(str(item.get("title") or "")) != "release"
        and not extract_release_tag(
            str(item.get("title") or ""),
            release_title_re=runtime_settings["release_title_re"],
        )
    }
    selected_issues = [issue for issue in issues if int(issue["number"]) in selected_issue_numbers]

    review_threads: list[dict[str, Any]] = []
    review_warnings: list[str] = []
    for pr in top_level_prs:
        comments, warnings = fetch_review_comments(repo_root, repo_meta["repo_slug"], int(pr["number"]))
        review_warnings.extend(warnings)
        review_threads.extend(build_review_threads(int(pr["number"]), comments))

    workflow_runs, workflow_warnings = list_workflow_runs(repo_root, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)

    sample_payload = {
        "now_utc": isoformat_utc(current_now),
        "window_days": window_days,
        "profile_name": repo_profile.get("name"),
        "state_marker": fixture_state_marker(marker, reporting_window),
        "default_branch": repo_meta["default_branch"],
        "releases": [normalize_release_fixture(release, release_issue_linkage) for release in releases],
        "prs": [normalize_pr_fixture(pr, pr_lineage) for pr in [*nested_prs, *top_level_prs]],
        "issues": [normalize_issue_fixture(issue, sorted(top_level_links.get(int(issue["number"]), []))) for issue in selected_issues],
        "review_threads": review_threads,
        "workflow_runs": [normalize_workflow_run_fixture(run) for run in workflow_runs],
    }
    sample_payload["prs"].sort(key=lambda item: str(item.get("merged_at") or ""))
    sample_payload["issues"].sort(key=lambda item: int(item.get("number") or 0))
    sample_payload["review_threads"].sort(key=lambda item: (int(item.get("pr_number") or 0), int((item.get("comments") or [{}])[0].get("id") or 0)))
    sample_payload["workflow_runs"].sort(key=lambda item: str(item.get("createdAt") or ""))

    context_id = f"weekly-update:{current_now.strftime('%Y%m%dT%H%M%SZ')}"
    context_fingerprint = f"fixture-refresh:{current_now.strftime('%Y%m%dT%H%M%SZ')}"
    plan_payloads = build_plan_fixtures(context_id=context_id, context_fingerprint=context_fingerprint, reporting_window=reporting_window)
    summary = {
        "repo_root": str(repo_root),
        "repo_slug": repo_meta["repo_slug"],
        "reporting_window": reporting_window,
        "counts": {
            "releases": len(sample_payload["releases"]),
            "prs": len(sample_payload["prs"]),
            "issues": len(sample_payload["issues"]),
            "review_threads": len(sample_payload["review_threads"]),
            "workflow_runs": len(sample_payload["workflow_runs"]),
        },
        "warnings": marker_warnings + release_warnings + issue_warnings + pr_summary_warnings + pr_warnings + review_warnings + workflow_warnings,
    }
    return sample_payload, plan_payloads, summary


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    sample_output = Path(args.sample_output).resolve()
    plan_dir = Path(args.plan_dir).resolve()
    sample_payload, plan_payloads, summary = collect_live_fixture_payload(
        repo_root=repo_root,
        profile=args.profile,
        state_file=args.state_file,
        window_days=args.window_days,
        now_utc=args.now_utc,
    )
    if not args.dry_run:
        write_json(sample_output, sample_payload)
        if not args.skip_plan_fixtures:
            plan_dir.mkdir(parents=True, exist_ok=True)
            for file_name, payload in plan_payloads.items():
                write_json(plan_dir / file_name, payload)
    result = {
        "ok": True,
        "dry_run": args.dry_run,
        "sample_output": str(sample_output),
        "plan_dir": None if args.skip_plan_fixtures else str(plan_dir),
        "counts": summary["counts"],
        "warnings": summary["warnings"],
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
