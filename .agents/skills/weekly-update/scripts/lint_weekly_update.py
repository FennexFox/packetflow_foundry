#!/usr/bin/env python3
"""Run deterministic lint checks for weekly-update."""

from __future__ import annotations

import argparse
from pathlib import Path

from weekly_update_lib import lint_context, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--output", required=True, help="Output lint JSON.")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    findings = lint_context(context)
    write_json(Path(args.output).resolve(), findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
