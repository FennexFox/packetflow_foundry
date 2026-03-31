#!/usr/bin/env python3
"""Apply a PR create request only from validator output."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import pr_create_contract as contract
import pr_create_tools as tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True, help="Validator output JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Report the planned gh command without mutating.")
    parser.add_argument("--result-output", help="Optional machine-readable apply result JSON.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return contract.load_json(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    contract.write_json(path, payload)


def fail(payload: dict[str, Any], result_output: Path | None, reason: str, message: str, **extra: Any) -> int:
    payload.update(extra)
    payload["apply_succeeded"] = False
    payload["stop_reason"] = reason
    payload["stop_reasons"] = [reason]
    if result_output is not None:
        write_json(result_output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 1


def load_validated_request(validation: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = validation.get("normalized_create_request")
    if not isinstance(normalized, dict):
        raise RuntimeError("validator output is missing `normalized_create_request`")
    fingerprint = str(validation.get("normalized_create_request_fingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("validator output is missing `normalized_create_request_fingerprint`")
    if contract.json_fingerprint(normalized) != fingerprint:
        raise RuntimeError("validator fingerprint mismatch for normalized_create_request")
    if not validation.get("valid") or not validation.get("can_apply"):
        raise RuntimeError("validator output is not apply-safe")
    apply_gate_status = validation.get("apply_gate_status") or {}
    if apply_gate_status.get("uncovered_stop_categories"):
        raise RuntimeError("validator output still reports uncovered stop categories")
    return normalized, fingerprint


def live_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(str(request.get("repo_root") or ".")).resolve()
    repo_slug = str(request.get("repo_slug") or "").strip() or None
    head = str(request.get("head") or "").strip()
    base = str(request.get("base") or "").strip()
    context_like = {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "resolved_head": head,
        "resolved_base": base,
        "local_head_oid": tools.local_head_oid(repo_root, head),
        "remote_head_oid": tools.remote_head_oid(repo_root, head),
        "changed_files_fingerprint": contract.json_fingerprint(tools.load_changed_files_between(repo_root, base, head)),
        "template_selection": tools.select_pr_template(repo_root),
    }
    duplicate_summary = tools.duplicate_check_summary(repo_root, repo_slug, head) if repo_slug and head else {}
    return contract.build_validated_snapshot(context_like, duplicate_summary)


def normalized_pr_result(pr_payload: dict[str, Any]) -> dict[str, Any]:
    labels = sorted(
        str(item.get("name") or "").strip()
        for item in pr_payload.get("labels", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    )
    assignees = sorted(
        str(item.get("login") or "").strip().lower()
        for item in pr_payload.get("assignees", [])
        if isinstance(item, dict) and str(item.get("login") or "").strip()
    )
    reviewers = sorted(
        str((item.get("requestedReviewer") or {}).get("login") or "").strip().lower()
        for item in pr_payload.get("reviewRequests", [])
        if isinstance(item, dict) and str((item.get("requestedReviewer") or {}).get("login") or "").strip()
    )
    milestone = pr_payload.get("milestone") or {}
    return {
        "number": pr_payload.get("number"),
        "url": str(pr_payload.get("url") or "").strip() or None,
        "title": str(pr_payload.get("title") or "").strip(),
        "body": str(pr_payload.get("body") or "").rstrip(),
        "head": str(pr_payload.get("headRefName") or "").strip(),
        "base": str(pr_payload.get("baseRefName") or "").strip(),
        "draft": bool(pr_payload.get("isDraft")),
        "labels": labels,
        "assignees": assignees,
        "reviewers": reviewers,
        "milestone": str(milestone.get("title") or "").strip() or None,
        "maintainer_can_modify": bool(pr_payload.get("maintainerCanModify")),
    }


def compare_request_to_pr(request: dict[str, Any], pr_payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalized_pr_result(pr_payload)
    expected = {
        "title": str(request.get("title") or "").strip(),
        "body": str(request.get("body") or "").rstrip(),
        "head": str(request.get("head") or "").strip(),
        "base": str(request.get("base") or "").strip(),
        "draft": bool(request.get("draft")),
        "labels": list(request.get("labels") or []),
        "assignees": [str(item).lower() for item in request.get("assignees", [])],
        "reviewers": [str(item).lower() for item in request.get("reviewers", [])],
        "milestone": request.get("milestone"),
        "maintainer_can_modify": bool(request.get("maintainer_can_modify")),
    }
    mismatches: list[dict[str, Any]] = []
    for field, expected_value in expected.items():
        actual_value = normalized.get(field)
        if actual_value != expected_value:
            mismatches.append({"field": field, "expected": expected_value, "actual": actual_value})
    return mismatches


def build_command(request: dict[str, Any], body_path: Path) -> list[str]:
    command = [
        "gh",
        "pr",
        "create",
        "--head",
        str(request["head"]),
        "--base",
        str(request["base"]),
        "--title",
        str(request["title"]),
        "--body-file",
        str(body_path),
    ]
    repo_slug = str(request.get("repo_slug") or "").strip()
    if repo_slug:
        command.extend(["--repo", repo_slug])
    if request.get("draft"):
        command.append("--draft")
    if not request.get("maintainer_can_modify", True):
        command.append("--no-maintainer-edit")
    if request.get("milestone"):
        command.extend(["--milestone", str(request["milestone"])])
    for item in request.get("reviewers", []):
        command.extend(["--reviewer", str(item)])
    for item in request.get("assignees", []):
        command.extend(["--assignee", str(item)])
    for item in request.get("labels", []):
        command.extend(["--label", str(item)])
    return command


def main() -> int:
    args = parse_args()
    validation = load_json(Path(args.validation).resolve())
    result_output = Path(args.result_output).resolve() if args.result_output else None
    payload: dict[str, Any] = {
        "dry_run": args.dry_run,
        "validation_source": "validator_normalized_create_request",
        "mutation_type": "gh_pr_create",
        "command": None,
    }

    try:
        request, fingerprint = load_validated_request(validation)
    except Exception as exc:
        return fail(payload, result_output, "fingerprint_mismatch", str(exc))

    repo_root = Path(str(request.get("repo_root") or ".")).resolve()
    payload.update(
        {
            "repo_slug": request.get("repo_slug"),
            "head": request.get("head"),
            "base": request.get("base"),
            "normalized_create_request_fingerprint": fingerprint,
            "validation_commands": list(request.get("validation_commands") or []),
        }
    )

    try:
        tools.run_command(["gh", "auth", "status"], cwd=repo_root)
    except Exception as exc:
        return fail(payload, result_output, "missing_auth", str(exc))

    try:
        fresh_snapshot = live_snapshot(request)
    except Exception as exc:
        return fail(payload, result_output, "live_snapshot_unavailable", str(exc))

    validated_snapshot = request.get("validated_snapshot") or {}
    stale_fields = contract.snapshot_mismatches(validated_snapshot, fresh_snapshot)
    if stale_fields:
        return fail(
            payload,
            result_output,
            "stale_snapshot",
            "The live branch/template/duplicate snapshot changed after validation.",
            stale_fields=stale_fields,
            current_duplicate_check_summary=fresh_snapshot.get("duplicate_check_summary"),
        )

    temp_root = repo_root / ".codex" / "tmp" / "packet-workflow" / "gh-create-pr"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".md",
        dir=temp_root,
        delete=False,
    ) as temp_file:
        temp_file.write(str(request.get("body") or "").rstrip() + "\n")
        temp_path = Path(temp_file.name)
    try:
        command = build_command(request, temp_path)
        payload["command"] = command

        if args.dry_run:
            payload["apply_succeeded"] = True
            if result_output is not None:
                write_json(result_output, payload)
            print(json.dumps(payload, indent=2, ensure_ascii=True))
            return 0

        try:
            create_stdout = tools.run_command(command, cwd=repo_root).strip()
        except Exception as exc:
            return fail(payload, result_output, "apply_verification_failed", str(exc))

        try:
            matches = tools.load_open_prs_for_head(
                repo_root,
                str(request.get("repo_slug") or "").strip() or None,
                str(request.get("head") or "").strip(),
            )
        except Exception as exc:
            return fail(payload, result_output, "apply_verification_failed", str(exc))

        if len(matches) != 1:
            return fail(
                payload,
                result_output,
                "apply_verification_failed",
                "PR creation did not result in exactly one same-head open PR.",
                create_stdout=create_stdout,
                matched_pr_count=len(matches),
            )

        pr_payload = matches[0]
        mismatches = compare_request_to_pr(request, pr_payload)
        if mismatches:
            return fail(
                payload,
                result_output,
                "apply_verification_failed",
                "Created PR does not match the validated create request.",
                verification_mismatches=mismatches,
                current_pr_url=normalized_pr_result(pr_payload).get("url"),
            )

        payload["current_pr_url"] = normalized_pr_result(pr_payload).get("url")
        payload["created_pr_number"] = pr_payload.get("number")
        payload["apply_succeeded"] = True
        if result_output is not None:
            write_json(result_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
