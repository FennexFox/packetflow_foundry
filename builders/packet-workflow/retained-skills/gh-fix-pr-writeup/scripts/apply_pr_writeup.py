#!/usr/bin/env python3
"""Apply a PR title/body update only from validator output."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pr_writeup_contract as contract
import pr_writeup_tools as tools
from validate_pr_writeup_edit import (
    json_fingerprint,
    load_json,
    normalize_paths,
    normalize_scalar,
    stale_snapshot_fields,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", required=True, help="Validator output JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned gh command without editing the PR.")
    parser.add_argument("--result-output", help="Optional machine-readable apply result JSON.")
    return parser.parse_args()


def fail(payload: dict[str, Any], result_output: Path | None, reason: str, message: str, **extra: Any) -> int:
    payload.update(extra)
    payload["apply_succeeded"] = False
    payload["stop_reason"] = reason
    payload["stop_reasons"] = [reason]
    if result_output is not None:
        write_json(result_output, payload)
    print(f"apply_pr_writeup.py: {message}", file=sys.stderr)
    return 1


def normalized_edit_from_validation(validation: dict[str, Any]) -> dict[str, Any]:
    normalized_edit = validation.get("normalized_edit")
    if not isinstance(normalized_edit, dict):
        raise RuntimeError("validator output is missing `normalized_edit`")
    expected_fingerprint = str(validation.get("normalized_edit_fingerprint") or "").strip()
    if not expected_fingerprint:
        raise RuntimeError("validator output is missing `normalized_edit_fingerprint`")
    if json_fingerprint(normalized_edit) != expected_fingerprint:
        raise RuntimeError("validator mismatch: normalized-edit fingerprint changed")
    if not validation.get("valid"):
        raise RuntimeError("refusing to apply validator output marked invalid")
    if not validation.get("can_apply"):
        raise RuntimeError("refusing to apply validator output marked not apply-safe")
    apply_gate_status = validation.get("apply_gate_status") or {}
    if apply_gate_status.get("uncovered_stop_categories"):
        raise RuntimeError("refusing to apply while applicable stop categories remain uncovered")
    qa_gate = normalized_edit.get("qa_gate") or {}
    if qa_gate.get("required") and not qa_gate.get("qa_clear"):
        raise RuntimeError("refusing to apply while QA-required draft lacks QA clear signal")
    return normalized_edit


def main() -> int:
    args = parse_args()
    validation = load_json(Path(args.validation).resolve())
    result_output = Path(args.result_output).resolve() if args.result_output else None
    payload: dict[str, Any] = {
        "dry_run": args.dry_run,
        "validation_source": "validator_normalized_edit",
        "mutation_type": "gh_pr_edit",
        "command": None,
    }

    try:
        normalized_edit = normalized_edit_from_validation(validation)
    except Exception as exc:
        return fail(payload, result_output, "validator_mismatch", str(exc))

    repo_root = Path(str(normalized_edit.get("repo_root") or ".")).resolve()
    repo_slug = normalized_edit.get("repo_slug")
    pr_number = int(normalized_edit["pr_number"])
    title = normalize_scalar(normalized_edit.get("title"))
    body = str(normalized_edit.get("body") or "")
    validated_snapshot = dict(normalized_edit.get("validated_snapshot") or {})

    payload.update(
        {
            "pr_number": pr_number,
            "repo_slug": repo_slug,
            "validation_commands": list(normalized_edit.get("validation_commands") or []),
            "normalized_edit_fingerprint": str(validation.get("normalized_edit_fingerprint") or ""),
            "current_pr_url": normalize_scalar(validated_snapshot.get("url")),
            "qa_required": bool((normalized_edit.get("qa_gate") or {}).get("required")),
            "qa_clear": bool((normalized_edit.get("qa_gate") or {}).get("qa_clear")),
        }
    )

    try:
        tools.run_command(["gh", "auth", "status"], cwd=repo_root)
    except Exception as exc:
        return fail(payload, result_output, "missing_auth", str(exc))

    try:
        live_pr = tools.load_pr_metadata(pr_number, repo_root, repo_slug)
        live_changed_files = tools.load_pr_changed_files(pr_number, repo_root, repo_slug)
    except Exception as exc:
        return fail(payload, result_output, "live_snapshot_unavailable", str(exc))

    stale_fields = stale_snapshot_fields(validated_snapshot, live_pr, live_changed_files)
    if stale_fields:
        return fail(
            payload,
            result_output,
            "stale_context",
            "the live PR snapshot changed after validation; rerun validation before editing",
            stale_fields=stale_fields,
        )

    qa_gate = normalized_edit.get("qa_gate") or {}
    if qa_gate.get("required") and not qa_gate.get("qa_clear"):
        return fail(
            payload,
            result_output,
            "qa_required",
            "the draft still requires QA clearance before apply",
            apply_gate_status=contract.stop_status(),
        )

    temp_root = repo_root / ".codex" / "tmp" / "packet-workflow" / "gh-fix-pr-writeup"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".md",
        dir=temp_root,
        delete=False,
    ) as temp_file:
        temp_file.write(body)
        temp_path = Path(temp_file.name)
    try:
        command = ["gh", "pr", "edit", str(pr_number), "--title", title, "--body-file", str(temp_path)]
        if repo_slug:
            command.extend(["--repo", str(repo_slug)])
        payload["command"] = command

        if args.dry_run:
            payload["apply_succeeded"] = True
            if result_output is not None:
                write_json(result_output, payload)
            print(json.dumps(payload, indent=2, ensure_ascii=True))
            return 0

        try:
            tools.run_command(command, cwd=repo_root)
            confirmed = tools.load_pr_metadata(pr_number, repo_root, repo_slug)
        except Exception as exc:
            return fail(payload, result_output, "apply_failed", str(exc))

        if normalize_scalar(confirmed.get("title")) != title or normalize_scalar(confirmed.get("body")) != body.strip():
            return fail(
                payload,
                result_output,
                "apply_verification_failed",
                "gh pr edit returned, but the confirmed PR title/body do not match the requested replacement",
                confirmed_pr_url=normalize_scalar(confirmed.get("url")),
            )

        payload["current_pr_url"] = normalize_scalar(confirmed.get("url"))
        payload["apply_succeeded"] = True
        if result_output is not None:
            write_json(result_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
