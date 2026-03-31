#!/usr/bin/env python3
"""Check retained packet-workflow skill compatibility metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from packet_workflow_versioning import (
    canonical_retained_skills_root,
    evaluate_skill_dir,
    load_builder_versioning,
    retained_skill_dirs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skills-root",
        default=str(canonical_retained_skills_root()),
        help="Directory containing retained skill folders.",
    )
    parser.add_argument(
        "--output",
        help="Optional output path for the JSON report. Prints to stdout when omitted.",
    )
    return parser.parse_args()


def build_report(skills_root: Path) -> dict[str, object]:
    current_builder = load_builder_versioning()
    skills = [
        evaluate_skill_dir(skill_dir, current_builder=current_builder)
        for skill_dir in retained_skill_dirs(skills_root)
    ]
    summary: dict[str, int] = {}
    blocking_count = 0
    for skill in skills:
        status = str(skill["status"])
        summary[status] = summary.get(status, 0) + 1
        if bool(skill["blocking"]):
            blocking_count += 1
    return {
        "builder_version": current_builder,
        "skills_root": skills_root.as_posix(),
        "skills": skills,
        "summary": summary,
        "blocking_count": blocking_count,
    }


def main() -> int:
    args = parse_args()
    skills_root = Path(args.skills_root).resolve()
    report = build_report(skills_root)
    payload = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 1 if int(report["blocking_count"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

