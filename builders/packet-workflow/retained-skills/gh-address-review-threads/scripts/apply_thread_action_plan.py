#!/usr/bin/env python3
"""Apply acknowledgement and completion actions for PR review threads."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from thread_action_contract import load_normalized_plan_envelope


PHASES = {"ack", "complete"}
DECISIONS = {"accept", "reject", "defer", "defer-outdated"}
MARKER_PREFIX = "<!-- codex:review-thread v1 phase={phase} thread={thread_id} -->"
MANAGED_MARKER_START = "<!-- codex:review-thread v1 "

ADD_REPLY_MUTATION = """\
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(
    input: {
      pullRequestReviewThreadId: $threadId
      body: $body
    }
  ) {
    comment {
      id
      url
    }
  }
}
"""

UPDATE_REPLY_MUTATION = """\
mutation($commentId: ID!, $body: String!) {
  updatePullRequestReviewComment(
    input: {
      pullRequestReviewCommentId: $commentId
      body: $body
    }
  ) {
    pullRequestReviewComment {
      id
      url
    }
  }
}
"""

RESOLVE_THREAD_MUTATION = """\
mutation($threadId: ID!) {
  resolveReviewThread(
    input: {
      threadId: $threadId
    }
  ) {
    thread {
      id
      isResolved
    }
  }
}
"""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def run_json(args: list[str], cwd: Path, stdin_text: str | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        command_name = args[0] if args else "command"
        raise RuntimeError(f"{command_name} executable not found") from exc
    if result.returncode != 0:
        stderr = decode_text(result.stderr).strip()
        stdout = decode_text(result.stdout).strip()
        detail = stderr or stdout or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    try:
        return json.loads(decode_text(result.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse JSON from {' '.join(args)}: {exc}") from exc


def ensure_marker(body: str, phase: str, thread_id: str) -> str:
    body = body.strip()
    marker = MARKER_PREFIX.format(phase=phase, thread_id=thread_id)
    if body.startswith(marker):
        return body
    if body.startswith(MANAGED_MARKER_START):
        _first_line, _sep, rest = body.partition("\n")
        return marker if not rest else marker + "\n" + rest.lstrip("\n")
    return marker if not body else marker + "\n" + body


def thread_lookup(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(thread["thread_id"]): thread for thread in context.get("threads", [])}


def phase_fields(phase: str) -> tuple[str, str, str]:
    if phase == "ack":
        return "ack_mode", "ack_body", "ack_comment_id"
    return "complete_mode", "complete_body", "complete_comment_id"


def fallback_comment_id(thread: dict[str, Any], phase: str) -> str | None:
    candidates = (thread.get("reply_candidates") or {}).get(phase) or {}
    comment_id = candidates.get("comment_id")
    return str(comment_id) if comment_id else None


def graphql(repo_root: Path, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    args = ["gh", "api", "graphql", "-F", "query=@-"]
    for key, value in variables.items():
        args.extend(["-F", f"{key}={value}"])
    payload = run_json(args, cwd=repo_root, stdin_text=query)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2, ensure_ascii=True))
    return payload


def write_json_output(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply acknowledgement and completion actions for PR review threads."
    )
    parser.add_argument("--context", type=Path, required=True, help="Path to JSON from collect_review_threads.py")
    parser.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Path to normalized validation JSON from validate_thread_action_plan.py",
    )
    parser.add_argument("--phase", choices=sorted(PHASES), required=True, help="Action phase to apply")
    parser.add_argument("--dry-run", action="store_true", help="Print planned mutations without calling GitHub")
    parser.add_argument(
        "--result-output",
        type=Path,
        help="Optional path to write the JSON result payload.",
    )
    args = parser.parse_args()

    context = load_json(args.context)
    plan = load_json(args.plan)
    repo_root = Path(str(context.get("repo_root") or ".")).resolve()
    validated = load_normalized_plan_envelope(context, plan, args.phase)
    entries = list(validated["normalized_thread_actions"])
    threads_by_id = thread_lookup(context)
    mode_field, body_field, comment_id_field = phase_fields(args.phase)

    operations: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for entry in entries:
        thread_id = str(entry.get("thread_id") or "")
        if not thread_id:
            raise RuntimeError("each plan entry must include thread_id")
        if thread_id not in threads_by_id:
            raise RuntimeError(f"thread_id {thread_id} is not present in the context")
        decision = str(entry.get("decision") or "")
        if decision not in DECISIONS:
            raise RuntimeError(f"thread {thread_id}: invalid decision `{decision}`")

        thread = threads_by_id[thread_id]
        mode = str(entry.get(mode_field) or "skip")
        if mode not in {"add", "update", "skip"}:
            raise RuntimeError(f"thread {thread_id}: invalid {mode_field} `{mode}`")
        if args.phase == "complete" and decision != "accept" and mode != "skip":
            raise RuntimeError(f"thread {thread_id}: complete actions are only valid for accepted threads")

        body = str(entry.get(body_field) or "")
        if mode != "skip" and not body.strip():
            raise RuntimeError(f"thread {thread_id}: {body_field} is required when {mode_field} is {mode}")

        target_comment_id = entry.get(comment_id_field) or fallback_comment_id(thread, args.phase)
        if mode == "update" and not target_comment_id:
            raise RuntimeError(f"thread {thread_id}: update requested but no comment id was supplied or inferred")

        if mode != "skip":
            managed_body = ensure_marker(body, args.phase, thread_id)
            if mode == "add":
                operations.append(
                    {
                        "thread_id": thread_id,
                        "phase": args.phase,
                        "operation": "add_reply",
                        "variables": {
                            "threadId": thread_id,
                            "body": managed_body,
                        },
                    }
                )
            else:
                operations.append(
                    {
                        "thread_id": thread_id,
                        "phase": args.phase,
                        "operation": "update_reply",
                        "variables": {
                            "commentId": str(target_comment_id),
                            "body": managed_body,
                        },
                    }
                )

        if args.phase == "complete" and decision == "accept" and bool(entry.get("resolve_after_complete")):
            operations.append(
                {
                    "thread_id": thread_id,
                    "phase": args.phase,
                    "operation": "resolve_thread",
                    "variables": {
                        "threadId": thread_id,
                    },
                }
            )

    if args.dry_run:
        payload = {
            "dry_run": True,
            "apply_succeeded": True,
            "fingerprint_match": bool(validated.get("fingerprint_match")),
            "context_fingerprint": validated.get("context_fingerprint"),
            "phase": args.phase,
            "counters": validated.get("counters", {}),
            "warnings": validated.get("warnings", []),
            "normalized_thread_actions": entries,
            "operations": operations,
            "mutations": [
                {
                    "kind": operation["operation"],
                    "thread_id": operation["thread_id"],
                    "phase": operation["phase"],
                }
                for operation in operations
            ],
            "mutation_type": operations[0]["operation"] if operations else None,
        }
        if isinstance(validated.get("reconciliation_summary"), dict):
            payload["reconciliation_summary"] = validated["reconciliation_summary"]
        write_json_output(args.result_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    for operation in operations:
        op_type = operation["operation"]
        variables = dict(operation["variables"])
        if op_type == "add_reply":
            payload = graphql(repo_root, ADD_REPLY_MUTATION, variables)
            response = payload["data"]["addPullRequestReviewThreadReply"]["comment"]
        elif op_type == "update_reply":
            payload = graphql(repo_root, UPDATE_REPLY_MUTATION, variables)
            response = payload["data"]["updatePullRequestReviewComment"]["pullRequestReviewComment"]
        elif op_type == "resolve_thread":
            payload = graphql(repo_root, RESOLVE_THREAD_MUTATION, variables)
            response = payload["data"]["resolveReviewThread"]["thread"]
        else:
            raise RuntimeError(f"unknown operation type {op_type}")
        results.append(
            {
                "thread_id": operation["thread_id"],
                "phase": operation["phase"],
                "operation": op_type,
                "result": response,
            }
        )

    payload = {
        "dry_run": False,
        "apply_succeeded": True,
        "fingerprint_match": bool(validated.get("fingerprint_match")),
        "context_fingerprint": validated.get("context_fingerprint"),
        "phase": args.phase,
        "counters": validated.get("counters", {}),
        "warnings": validated.get("warnings", []),
        "normalized_thread_actions": entries,
        "results": results,
        "mutations": [
            {
                "kind": item["operation"],
                "thread_id": item["thread_id"],
                "phase": item["phase"],
            }
            for item in results
        ],
        "mutation_type": results[0]["operation"] if results else None,
    }
    if isinstance(validated.get("reconciliation_summary"), dict):
        payload["reconciliation_summary"] = validated["reconciliation_summary"]
    write_json_output(args.result_output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"apply_thread_action_plan.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
