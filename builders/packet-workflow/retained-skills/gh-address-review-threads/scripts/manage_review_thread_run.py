#!/usr/bin/env python3
"""Manage run-scoped runtime artifacts for gh-address-review-threads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import review_thread_run as run_support


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    start = subparsers.add_parser("start", help="Create a new run-scoped manifest and stage the pre-push context.")
    start.add_argument("--repo-root", type=Path, required=True)
    start.add_argument("--context", type=Path, required=True)
    start.add_argument("--run-id")
    start.add_argument("--eval-log", type=Path, help="Optional explicit evaluation-log path.")

    record_plan = subparsers.add_parser(
        "record-plan",
        help="Copy a validated phase plan into the run manifest and update accepted-thread state for ack.",
    )
    record_plan.add_argument("--manifest", type=Path, required=True)
    record_plan.add_argument("--phase", choices=["ack", "complete"], required=True)
    record_plan.add_argument("--validated-plan", type=Path, required=True)

    record_validation = subparsers.add_parser(
        "record-validation",
        help="Store the validation commands that should feed same-run post-push reconciliation.",
    )
    record_validation.add_argument("--manifest", type=Path, required=True)
    record_validation.add_argument(
        "--validation-command",
        "--command",
        dest="validation_commands",
        action="append",
        default=[],
    )

    record_accepts = subparsers.add_parser(
        "record-accepts",
        help="Store accepted thread ids explicitly when no validated ack plan is available to parse.",
    )
    record_accepts.add_argument("--manifest", type=Path, required=True)
    record_accepts.add_argument("--thread-id", action="append", default=[])

    post_push = subparsers.add_parser(
        "post-push",
        help="Stage the post-push context and emit reconciliation-input.json from manifest state.",
    )
    post_push.add_argument("--manifest", type=Path, required=True)
    post_push.add_argument("--context", type=Path, required=True)

    latest = subparsers.add_parser("latest", help="Show the latest run pointer for a repository.")
    latest.add_argument("--repo-root", type=Path, required=True)

    show = subparsers.add_parser("show", help="Show the full manifest JSON.")
    show.add_argument("--manifest", type=Path, required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    action = args.action

    if action == "start":
        repo_root = args.repo_root.resolve()
        manifest = run_support.create_run(
            repo_root,
            args.context.resolve(),
            run_id=args.run_id,
            evaluation_log_path=args.eval_log.resolve() if args.eval_log else None,
        )
        print_json(manifest)
        return 0

    if action == "record-plan":
        manifest_path = args.manifest.resolve()
        manifest = run_support.load_manifest(manifest_path)
        if args.phase == "complete":
            run_support.require_last_completed_phase(
                manifest,
                action_label="record-plan --phase complete",
                allowed={"post-prepared"},
            )
        run_support.copy_validated_plan_into_manifest(
            manifest,
            phase=str(args.phase),
            source_path=args.validated_plan.resolve(),
        )
        run_support.write_manifest(manifest_path, manifest)
        run_support.write_latest_pointer(Path(manifest["repo_root"]), manifest)
        print_json(manifest)
        return 0

    if action == "record-validation":
        manifest_path = args.manifest.resolve()
        manifest = run_support.load_manifest(manifest_path)
        run_support.require_last_completed_phase(
            manifest,
            action_label="record-validation",
            allowed={"ack-validated"},
        )
        run_support.set_validation_commands(manifest, list(args.validation_commands or []))
        run_support.write_manifest(manifest_path, manifest)
        run_support.write_latest_pointer(Path(manifest["repo_root"]), manifest)
        print_json(manifest)
        return 0

    if action == "record-accepts":
        manifest_path = args.manifest.resolve()
        manifest = run_support.load_manifest(manifest_path)
        run_support.set_accepted_threads(manifest, list(args.thread_id or []))
        run_support.write_manifest(manifest_path, manifest)
        run_support.write_latest_pointer(Path(manifest["repo_root"]), manifest)
        print_json(manifest)
        return 0

    if action == "post-push":
        manifest_path = args.manifest.resolve()
        manifest = run_support.load_manifest(manifest_path)
        run_support.require_last_completed_phase(
            manifest,
            action_label="post-push",
            allowed={"ack-validated"},
        )
        run_support.require_post_push_validation_provenance(manifest)
        run_support.copy_context_into_manifest(
            manifest,
            phase="post",
            source_path=args.context.resolve(),
        )
        reconciliation = run_support.write_reconciliation_input(manifest)
        run_support.write_manifest(manifest_path, manifest)
        run_support.write_latest_pointer(Path(manifest["repo_root"]), manifest)
        print_json(
            {
                "manifest": manifest,
                "reconciliation_input": reconciliation,
            }
        )
        return 0

    if action == "latest":
        print_json(run_support.read_json(run_support.latest_pointer_path(args.repo_root.resolve())))
        return 0

    if action == "show":
        print_json(run_support.load_manifest(args.manifest.resolve()))
        return 0

    raise RuntimeError(f"Unsupported command: {action}")


if __name__ == "__main__":
    raise SystemExit(main())
