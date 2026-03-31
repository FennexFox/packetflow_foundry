#!/usr/bin/env python3
"""Validate a synthesized weekly-update plan against the collected context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_update_lib import load_json, validate_weekly_update_plan, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--plan", required=True, help="Synthesized weekly update plan JSON.")
    parser.add_argument("--output", help="Optional machine-readable validation result JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    plan = load_json(Path(args.plan).resolve())
    result = validate_weekly_update_plan(context, plan)
    if args.output:
        write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, indent=2))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
