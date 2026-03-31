from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BUILDER_SCRIPTS_DIR = Path(__file__).resolve().parents[4] / "builders" / "packet-workflow" / "scripts"
if str(BUILDER_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(BUILDER_SCRIPTS_DIR))

from packet_workflow_versioning import (  # type: ignore  # noqa: E402
    classify_builder_compatibility,
    extract_profile_versioning,
    extract_skill_builder_versioning,
    format_runtime_warning,
    load_builder_versioning,
    load_json_document,
)
from pr_writeup_tools import build_context


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_repo_profile_path() -> Path:
    return skill_root() / "profiles" / "default" / "profile.json"


def resolve_profile_path(profile_path: str) -> Path:
    candidate = Path(profile_path)
    if not candidate.is_absolute():
        candidate = (skill_root() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.is_file():
        raise SystemExit(f"[ERROR] Missing repo profile: {candidate}")
    return candidate


def load_repo_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise SystemExit("[ERROR] Repo profile must be a JSON object.")
    return payload


def build_builder_compatibility(repo_profile: dict[str, Any]) -> dict[str, Any]:
    return classify_builder_compatibility(
        current_builder=load_builder_versioning(),
        skill_versioning=extract_skill_builder_versioning(
            load_json_document(skill_root() / "builder-spec.json")
        ),
        profile_versioning=extract_profile_versioning(repo_profile),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect structured context for auditing a GitHub PR writeup."
    )
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing .git and PR guidance files",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional GitHub repo slug such as owner/name",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output file path. Prints JSON to stdout when omitted.",
    )
    parser.add_argument(
        "--profile",
        default=str(default_repo_profile_path()),
        help="Path to the active repo profile JSON. Relative paths resolve from the skill root.",
    )
    args = parser.parse_args()

    profile_path = resolve_profile_path(args.profile)
    repo_profile = load_repo_profile(profile_path)
    try:
        context = build_context(
            pr_number=args.pr_number,
            repo_root=Path(args.repo_root).resolve(),
            repo_slug=args.repo,
        )
    except RuntimeError as exc:
        print(f"collect_pr_context.py: {exc}", file=sys.stderr)
        return 1
    context["repo_profile_name"] = repo_profile.get("name")
    context["repo_profile_path"] = profile_path.as_posix()
    context["repo_profile_summary"] = repo_profile.get("summary")
    context["repo_profile"] = repo_profile
    context["builder_compatibility"] = build_builder_compatibility(repo_profile)
    payload = json.dumps(context, indent=2, ensure_ascii=True)

    if context["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(context["builder_compatibility"]), file=sys.stderr)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


