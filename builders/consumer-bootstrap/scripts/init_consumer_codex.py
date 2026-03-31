#!/usr/bin/env python3
"""Initialize the minimum `.codex` layout for a PacketFlow Foundry consumer repo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


FOUNDRY_KEYWORDS = (
    "packetflow_foundry",
    "packetflow foundry",
    ".codex/vendor/packetflow_foundry",
)
BOOTSTRAP_MARKER_START = "<!-- packetflow_foundry consumer bootstrap:start -->"
BOOTSTRAP_MARKER_END = "<!-- packetflow_foundry consumer bootstrap:end -->"
CODEX_AGENTS_RELATIVE = Path(".codex/AGENTS.md")
ROOT_AGENTS_RELATIVE = Path("AGENTS.md")
PROJECT_PROFILE_RELATIVE = Path(".codex/project/profiles/default/profile.json")
PROJECT_SKILLS_GITKEEP_RELATIVE = Path(".codex/project/skills/.gitkeep")
PROJECT_AGENTS_GITKEEP_RELATIVE = Path(".codex/project/agents/.gitkeep")
CONFLICT_TARGETS = (
    PROJECT_PROFILE_RELATIVE,
    PROJECT_SKILLS_GITKEEP_RELATIVE,
    PROJECT_AGENTS_GITKEEP_RELATIVE,
)
PROJECT_LOCAL_PROFILE_KIND = "project-local-scaffold-profile"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Consumer repository root. Defaults to the current directory.",
    )
    return parser.parse_args()


def resolve_repo_root(value: str) -> Path:
    repo_root = Path(value).resolve()
    if not repo_root.exists():
        raise RuntimeError(f"Missing repo root: {repo_root}")
    if not repo_root.is_dir():
        raise RuntimeError(f"Repo root is not a directory: {repo_root}")
    return repo_root


def require_vendor_subtree(repo_root: Path) -> Path:
    vendor_dir = repo_root / ".codex" / "vendor" / "packetflow_foundry"
    if not vendor_dir.is_dir():
        raise RuntimeError(
            "Missing PacketFlow Foundry vendor subtree at "
            f"{vendor_dir.as_posix()}"
        )
    return vendor_dir


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def render_agents_block() -> str:
    return "\n".join(
        [
            BOOTSTRAP_MARKER_START,
            "## PacketFlow Foundry",
            "- Vendor: `.codex/vendor/packetflow_foundry`",
            (
                "- Project-local overlays: `.codex/project/profiles/`, "
                "`.codex/project/skills/`, `.codex/project/agents/`"
            ),
            "- Do not edit `.codex/vendor/packetflow_foundry` for local needs.",
            (
                "- `.codex/project/profiles/default/profile.json` is a "
                "project-local scaffold."
            ),
            BOOTSTRAP_MARKER_END,
        ]
    )


def render_codex_agents_file() -> str:
    return "\n".join(
        [
            "# .codex AGENTS",
            "",
            render_agents_block(),
        ]
    )


def contains_foundry_guidance(text: str) -> bool:
    lowered = text.lower()
    if BOOTSTRAP_MARKER_START in text:
        return True
    return any(keyword in lowered for keyword in FOUNDRY_KEYWORDS)


def append_block(existing: str, block: str) -> str:
    stripped = existing.rstrip()
    if not stripped:
        return block
    return stripped + "\n\n" + block


def ensure_agents_target(path: Path) -> None:
    if path.exists() and not path.is_file():
        raise RuntimeError(f"AGENTS target is not a file: {path.as_posix()}")


def update_root_agents(repo_root: Path) -> str:
    path = repo_root / ROOT_AGENTS_RELATIVE
    ensure_agents_target(path)
    if not path.exists():
        return "not present"
    existing = read_text(path)
    if contains_foundry_guidance(existing):
        return "unchanged"
    write_text(path, append_block(existing, render_agents_block()))
    return "appended foundry block"


def update_codex_agents(repo_root: Path) -> str:
    path = repo_root / CODEX_AGENTS_RELATIVE
    ensure_agents_target(path)
    if not path.exists():
        write_text(path, render_codex_agents_file())
        return "created"
    existing = read_text(path)
    if contains_foundry_guidance(existing):
        return "unchanged"
    write_text(path, append_block(existing, render_agents_block()))
    return "appended foundry block"


def project_root_markers(repo_root: Path) -> list[str]:
    markers = [".git"]
    if (repo_root / "README.md").is_file():
        markers.append("README.md")
    return markers


def build_project_local_profile(repo_root: Path) -> dict[str, object]:
    return {
        "name": "default",
        "kind": PROJECT_LOCAL_PROFILE_KIND,
        "profile_path": PROJECT_PROFILE_RELATIVE.as_posix(),
        "summary": (
            "Project-local scaffold profile for this consumer repository. "
            "This is not a reusable foundry overlay; replace the placeholder "
            "values here with repo-specific bindings, review docs, and local notes."
        ),
        "repo_match": {
            "root_markers": project_root_markers(repo_root),
            "remote_patterns": [],
        },
        "bindings": {
            "primary_readme_path": "README.md",
            "settings_source_path": None,
            "publish_config_path": None,
        },
        "packet_defaults": {
            "review_docs": {},
            "source_path_globs": {},
        },
        "lint_rules": {
            "require_readme_settings_table": False,
            "missing_review_docs_are_errors": False,
        },
        "notes": [
            "This file is a project-local scaffold profile for one consumer repository.",
            "It is not a reusable foundry overlay and should stay outside the vendor subtree.",
            (
                "Keep this profile data-only: add repo-specific bindings, globs, "
                "review docs, booleans, and notes here."
            ),
            (
                "Do not add executable hooks, prompt fragments, or packet routing "
                "authority here."
            ),
        ],
    }


def render_project_local_profile(repo_root: Path) -> str:
    return json.dumps(
        build_project_local_profile(repo_root),
        indent=2,
        ensure_ascii=True,
    )


def preflight_non_agents(repo_root: Path) -> None:
    conflicts: list[str] = []
    for relative_path in CONFLICT_TARGETS:
        target = repo_root / relative_path
        if target.exists():
            conflicts.append(relative_path.as_posix())
    if conflicts:
        joined = ", ".join(conflicts)
        raise RuntimeError(
            "Refusing to overwrite existing bootstrap outputs: "
            f"{joined}. AGENTS.md append targets are the only exception."
        )


def create_non_agents(repo_root: Path) -> list[str]:
    created: list[str] = []

    profile_path = repo_root / PROJECT_PROFILE_RELATIVE
    write_text(profile_path, render_project_local_profile(repo_root))
    created.append(PROJECT_PROFILE_RELATIVE.as_posix())

    write_text(repo_root / PROJECT_SKILLS_GITKEEP_RELATIVE, "")
    created.append(PROJECT_SKILLS_GITKEEP_RELATIVE.as_posix())

    write_text(repo_root / PROJECT_AGENTS_GITKEEP_RELATIVE, "")
    created.append(PROJECT_AGENTS_GITKEEP_RELATIVE.as_posix())

    return created


def main() -> int:
    args = parse_args()

    try:
        repo_root = resolve_repo_root(args.repo_root)
        require_vendor_subtree(repo_root)
        preflight_non_agents(repo_root)
        root_agents_status = update_root_agents(repo_root)
        codex_agents_status = update_codex_agents(repo_root)
        created = create_non_agents(repo_root)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Initialized PacketFlow consumer scaffold at {repo_root.as_posix()}")
    print(f" - root AGENTS.md: {root_agents_status}")
    print(f" - .codex/AGENTS.md: {codex_agents_status}")
    for relative_path in created:
        print(f" - {relative_path}: created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
