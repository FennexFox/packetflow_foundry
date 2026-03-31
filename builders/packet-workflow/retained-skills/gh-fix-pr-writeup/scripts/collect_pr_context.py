from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def resolve_builder_scripts_dir() -> Path:
    script_path = Path(__file__).resolve()
    searched: list[Path] = []
    seen: set[Path] = set()
    for base in script_path.parents:
        for candidate in (
            base / "builders" / "packet-workflow" / "scripts",
            base
            / ".codex"
            / "vendor"
            / "packetflow_foundry"
            / "builders"
            / "packet-workflow"
            / "scripts",
        ):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            searched.append(resolved)
            if resolved.is_dir():
                return resolved
    search_list = ", ".join(path.as_posix() for path in searched)
    raise SystemExit(
        "[ERROR] Missing packet-workflow builder scripts. "
        f"Searched: {search_list}"
    )


BUILDER_SCRIPTS_DIR = resolve_builder_scripts_dir()
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


def retained_default_repo_profile_path() -> Path:
    return skill_root() / "profiles" / "default" / "profile.json"


def project_local_profile_candidates(repo_root: Path) -> list[Path]:
    repo_root = repo_root.resolve()
    return [
        repo_root / ".codex" / "project" / "profiles" / skill_root().name / "profile.json",
        repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json",
    ]


def default_repo_profile_path(repo_root: Path | None = None) -> Path:
    if repo_root is not None:
        for candidate in project_local_profile_candidates(repo_root):
            if candidate.is_file():
                return candidate.resolve()
    return retained_default_repo_profile_path()


def resolve_profile_path(profile_path: str | None, repo_root: Path | None = None) -> Path:
    if not profile_path:
        return default_repo_profile_path(repo_root)

    candidate = Path(profile_path)
    if candidate.is_absolute():
        resolved_candidates = [candidate.resolve()]
    else:
        resolved_candidates: list[Path] = []
        if repo_root is not None:
            resolved_candidates.append((repo_root / candidate).resolve())
        resolved_candidates.append((skill_root() / candidate).resolve())
    for resolved in resolved_candidates:
        if resolved.is_file():
            return resolved
    searched = ", ".join(path.as_posix() for path in resolved_candidates)
    raise SystemExit(f"[ERROR] Missing repo profile: {searched}")


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
        default=None,
        help=(
            "Optional path to the active repo profile JSON. Relative paths resolve from the "
            "repo root first, then the skill root. When omitted, the collector prefers "
            "`.codex/project/profiles/<skill-name>/profile.json`, then "
            "`.codex/project/profiles/default/profile.json`, then the retained default scaffold."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile_path = resolve_profile_path(args.profile, repo_root)
    repo_profile = load_repo_profile(profile_path)
    try:
        context = build_context(
            pr_number=args.pr_number,
            repo_root=repo_root,
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


