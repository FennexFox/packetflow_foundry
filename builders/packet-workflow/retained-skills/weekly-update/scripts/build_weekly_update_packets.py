#!/usr/bin/env python3
"""Build focused packets for weekly-update from collected context."""

from __future__ import annotations

import argparse
from pathlib import Path

from weekly_update_lib import build_packet_artifacts, load_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Collected context JSON.")
    parser.add_argument("--lint", help="Optional lint findings JSON.")
    parser.add_argument("--output-dir", required=True, help="Packet output directory.")
    parser.add_argument("--result-output", help="Optional machine-readable build result JSON.")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    context = load_json(Path(args.context).resolve())
    lint = load_json(Path(args.lint)) if args.lint else {}
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = build_packet_artifacts(context, lint)
    packets = artifacts["packets"]
    for file_name, payload in packets.items():
        write_json(output_dir / file_name, payload)
    write_json(output_dir / "packet_metrics.json", artifacts["packet_metrics"])
    if args.result_output:
        write_json(Path(args.result_output).resolve(), artifacts["build_result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
