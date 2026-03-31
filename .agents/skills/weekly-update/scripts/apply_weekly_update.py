#!/usr/bin/env python3
"""Dry-run or apply a planned action file for weekly-update."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from weekly_update_lib import apply_plan, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--plan", required=True, help="Planned action JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Report the apply plan without mutating.")
    parser.add_argument("--state-file", help="Optional state marker path override.")
    parser.add_argument("--result-output", help="Optional machine-readable apply result JSON.")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    plan = load_json(Path(args.plan).resolve())
    summary = apply_plan(
        context=context,
        plan=plan,
        state_file=args.state_file,
        dry_run=args.dry_run,
    )
    if args.result_output:
        write_json(Path(args.result_output).resolve(), summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
