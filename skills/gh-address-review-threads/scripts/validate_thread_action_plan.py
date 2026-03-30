#!/usr/bin/env python3
"""Validate and normalize thread action plans for PR review threads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from thread_action_contract import validate_thread_action_payload


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and normalize thread action plans for PR review threads."
    )
    parser.add_argument("--context", type=Path, required=True, help="Path to JSON from collect_review_threads.py")
    parser.add_argument("--plan", type=Path, required=True, help="Path to raw thread-actions JSON")
    parser.add_argument("--phase", choices=["ack", "complete"], required=True, help="Action phase to validate")
    parser.add_argument("--output", type=Path, help="Optional path to write the normalized validation JSON")
    args = parser.parse_args()

    try:
        context = load_json(args.context)
        plan = load_json(args.plan)
        payload = validate_thread_action_payload(context, plan, args.phase)
    except RuntimeError as exc:
        print(f"validate_thread_action_plan.py: {exc}", file=sys.stderr)
        return 1

    write_json(args.output, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
