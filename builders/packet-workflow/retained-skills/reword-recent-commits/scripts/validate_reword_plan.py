#!/usr/bin/env python3
"""Validate and normalize rewritten commit-message plans."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from reword_plan_contract import (
    branch_state,
    detect_operation,
    load_json,
    validate_reword_plan_payload,
)


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and normalize rewritten commit-message plans."
    )
    parser.add_argument("--rules", type=Path, required=True, help="Path to rules JSON from collect_commit_rules.py")
    parser.add_argument("--context", type=Path, required=True, help="Path to collected plan JSON from collect_recent_commits.py")
    parser.add_argument("--plan", type=Path, required=True, help="Path to the raw draft plan JSON with new_message values")
    parser.add_argument("--output", type=Path, help="Optional path to write the validation envelope")
    args = parser.parse_args()

    try:
        rules = load_json(args.rules)
        context = load_json(args.context)
        raw_plan = load_json(args.plan)
        repo_root = Path(str(context.get("repo_root") or ".")).resolve()
        repo_state = branch_state(repo_root)
        operation = detect_operation(repo_root)
        payload = validate_reword_plan_payload(
            context,
            rules,
            raw_plan,
            repo_state=repo_state,
            active_operation=operation,
        )
    except Exception as exc:
        print(f"validate_reword_plan.py: {exc}", file=sys.stderr)
        return 1

    write_json(args.output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0 if payload.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
