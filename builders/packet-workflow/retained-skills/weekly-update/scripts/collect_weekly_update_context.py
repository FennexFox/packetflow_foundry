#!/usr/bin/env python3
"""Collect structured workflow context for weekly-update."""

from __future__ import annotations

import argparse
from pathlib import Path

from weekly_update_lib import (
    collect_context,
    default_repo_profile_path,
    emit_builder_compatibility_warning,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, help="Repository root to inspect.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Optional path to the active repo profile JSON. Relative paths resolve from the "
            "repo root first, then the skill root. When omitted, the collector prefers "
            "`.codex/project/profiles/<skill-name>/profile.json`, then "
            "`.codex/project/profiles/default/profile.json`, then the retained default scaffold."
        ),
    )
    parser.add_argument("--state-file", help="Optional state marker path override.")
    parser.add_argument("--window-days", type=int, default=7, help="Window size when no state marker is reused.")
    parser.add_argument("--now-utc", help="Optional ISO8601 UTC timestamp override for deterministic runs.")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    payload = collect_context(
        repo_root=args.repo_root,
        profile=args.profile,
        state_file=args.state_file,
        window_days=args.window_days,
        now_utc=args.now_utc,
    )
    emit_builder_compatibility_warning(payload.get("builder_compatibility") or {})
    write_json(Path(args.output).resolve(), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
