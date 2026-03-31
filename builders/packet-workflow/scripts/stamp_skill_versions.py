#!/usr/bin/env python3
"""Stamp semver-only packet-workflow version metadata on retained skills."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from packet_workflow_versioning import (
    STATUS_CURRENT,
    STATUS_SEMVER_BEHIND_COMPATIBLE,
    canonical_retained_skills_root,
    evaluate_skill_dir,
    load_builder_versioning,
    load_json_document,
    retained_skill_dirs,
    write_json_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skills-root",
        default=str(canonical_retained_skills_root()),
        help="Directory containing retained skill folders.",
    )
    parser.add_argument(
        "skills",
        nargs="*",
        help="Optional skill names to stamp. Defaults to all retained skills under --skills-root.",
    )
    return parser.parse_args()


def profile_versioning_from_builder(builder_version: dict[str, Any]) -> dict[str, Any]:
    return {
        "builder_family": builder_version["builder_family"],
        "builder_semver": builder_version["builder_semver"],
        "compatibility_epoch": builder_version["compatibility_epoch"],
        "repo_profile_schema_version": builder_version["repo_profile_schema_version"],
    }


def selected_skill_dirs(skills_root: Path, selected: list[str]) -> list[Path]:
    retained = {path.name: path for path in retained_skill_dirs(skills_root)}
    if not selected:
        return [retained[name] for name in sorted(retained)]
    missing = [name for name in selected if name not in retained]
    if missing:
        raise SystemExit(f"[ERROR] Unknown retained skill(s): {', '.join(sorted(missing))}")
    return [retained[name] for name in selected]


def stamp_skill(skill_dir: Path, *, builder_version: dict[str, Any]) -> dict[str, Any]:
    report = evaluate_skill_dir(skill_dir, current_builder=builder_version)
    if report["status"] not in {STATUS_CURRENT, STATUS_SEMVER_BEHIND_COMPATIBLE}:
        raise SystemExit(
            f"[ERROR] Refusing to stamp {skill_dir.name}: compatibility status is {report['status']}."
        )

    spec_path = skill_dir / "builder-spec.json"
    profile_path = skill_dir / "profiles" / "default" / "profile.json"
    spec_payload = load_json_document(spec_path)
    profile_payload = load_json_document(profile_path)
    if not isinstance(spec_payload, dict):
        raise SystemExit(f"[ERROR] Invalid skill builder-spec payload: {spec_path}")
    if not isinstance(profile_payload, dict):
        raise SystemExit(f"[ERROR] Invalid skill profile payload: {profile_path}")

    spec_payload["builder_versioning"] = dict(builder_version)
    metadata = profile_payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        profile_payload["metadata"] = metadata
    metadata["versioning"] = profile_versioning_from_builder(builder_version)

    write_json_document(spec_path, spec_payload)
    write_json_document(profile_path, profile_payload)
    return {
        "skill_name": skill_dir.name,
        "status_before": report["status"],
        "builder_semver": builder_version["builder_semver"],
    }


def main() -> int:
    args = parse_args()
    builder_version = load_builder_versioning()
    skills_root = Path(args.skills_root).resolve()
    updates = [
        stamp_skill(skill_dir, builder_version=builder_version)
        for skill_dir in selected_skill_dirs(skills_root, list(args.skills))
    ]
    sys.stdout.write(json.dumps({"updated": updates}, indent=2, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

