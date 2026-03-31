#!/usr/bin/env python3
"""Initialize the minimum `.codex` layout for a PacketFlow Foundry consumer repo."""

from __future__ import annotations

import argparse
import json
import os
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
PROJECT_AGENT_DISCOVERY_RELATIVE = Path(".codex/agents")
LEGACY_PROJECT_AGENTS_RELATIVE = Path(".codex/project/agents")
ROOT_SKILLS_RELATIVE = Path(".agents/skills")
LEGACY_PROJECT_SKILLS_RELATIVE = Path(".codex/project/skills")
PROJECT_LOCAL_PROFILE_KIND = "project-local-scaffold-profile"
CONFLICT_TARGETS = (
    PROJECT_PROFILE_RELATIVE,
)


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


def require_vendor_skills_root(vendor_dir: Path) -> Path:
    vendor_skills = vendor_dir / ".agents" / "skills"
    if not vendor_skills.is_dir():
        raise RuntimeError(
            "Missing PacketFlow Foundry vendor skills subtree at "
            f"{vendor_skills.as_posix()}"
        )
    return vendor_skills


def require_vendor_agents_root(vendor_dir: Path) -> Path:
    vendor_agents = vendor_dir / ".codex" / "agents"
    if not vendor_agents.is_dir():
        raise RuntimeError(
            "Missing PacketFlow Foundry vendor agents subtree at "
            f"{vendor_agents.as_posix()}"
        )
    return vendor_agents


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
                "`.agents/skills/`, `.codex/agents/`"
            ),
            (
                "- `.codex/agents/` is the project-scoped subagent discovery "
                "surface. Vendored foundry agent TOMLs are bridged there from "
                "`.codex/vendor/packetflow_foundry/.codex/agents/`."
            ),
            (
                "- `.agents/skills/` is a thin discovery-wrapper surface. "
                "Reusable retained kernels stay under "
                "`.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`."
            ),
            "- Do not edit `.codex/vendor/packetflow_foundry` for local needs.",
            (
                "- `.codex/project/profiles/default/profile.json` is a "
                "project-local scaffold."
            ),
            (
                "- Skill-specific packet-workflow overrides may live at "
                "`.codex/project/profiles/<skill-name>/profile.json`."
            ),
            "- Legacy `.codex/project/agents/` is migration-only and should move to `.codex/agents/`.",
            "- Legacy `.codex/project/skills/` is migration-only and should move to `.agents/skills/`.",
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
                "Skill-specific packet-workflow bindings should live in "
                "`.codex/project/profiles/<skill-name>/profile.json` instead "
                "of this default scaffold."
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


def ensure_root_skill_dir(repo_root: Path) -> Path:
    root_skills = repo_root / ROOT_SKILLS_RELATIVE
    if root_skills.exists() and not root_skills.is_dir():
        raise RuntimeError(
            f"Root skills target is not a directory: {root_skills.as_posix()}"
        )
    root_skills.mkdir(parents=True, exist_ok=True)
    return root_skills


def ensure_project_agent_dir(repo_root: Path) -> Path:
    project_agents = repo_root / PROJECT_AGENT_DISCOVERY_RELATIVE
    if project_agents.exists() and not project_agents.is_dir():
        raise RuntimeError(
            "Project-scoped agent discovery target is not a directory: "
            f"{project_agents.as_posix()}"
        )
    project_agents.mkdir(parents=True, exist_ok=True)
    return project_agents


def iter_skill_directories(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    skills: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda entry: entry.name):
        if child.is_dir() and (child / "SKILL.md").is_file():
            skills[child.name] = child
    return skills


def iter_agent_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    agents: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda entry: entry.name):
        if child.is_file() and child.suffix == ".toml":
            agents[child.name] = child
    return agents


def relative_link_target(source: Path, *, target_parent: Path) -> Path:
    return Path(os.path.relpath(source, start=target_parent))


def create_symlink(link_path: Path, source_path: Path, *, is_directory: bool) -> str:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    relative_target = relative_link_target(source_path, target_parent=link_path.parent)
    try:
        link_path.symlink_to(relative_target, target_is_directory=is_directory)
    except OSError as exc:
        kind = "directory" if is_directory else "file"
        raise RuntimeError(
            f"Failed to create {kind} symlink "
            f"{link_path.as_posix()} -> {source_path.as_posix()}. "
            "Enable Windows Developer Mode or run the bootstrap with permissions "
            "that allow symbolic links."
        ) from exc
    return f"{link_path.as_posix()} -> {source_path.as_posix()}"


def create_skill_bridges(repo_root: Path, vendor_skills_root: Path) -> dict[str, list[str]]:
    root_skills = ensure_root_skill_dir(repo_root)
    vendor_skills = iter_skill_directories(vendor_skills_root)
    legacy_skills = iter_skill_directories(repo_root / LEGACY_PROJECT_SKILLS_RELATIVE)

    created: list[str] = []
    migrated: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []

    for skill_name in sorted(set(vendor_skills) | set(legacy_skills)):
        target_path = root_skills / skill_name
        if target_path.exists():
            skipped.append(
                f"{target_path.as_posix()} (existing root entry takes precedence)"
            )
            continue

        legacy_source = legacy_skills.get(skill_name)
        if legacy_source is not None:
            migrated.append(
                create_symlink(target_path, legacy_source, is_directory=True)
            )
            notices.append(
                "Legacy `.codex/project/skills/` entry bridged for migration: "
                f"{skill_name}. Move canonical ownership to `.agents/skills/{skill_name}`."
            )
            continue

        created.append(
            create_symlink(target_path, vendor_skills[skill_name], is_directory=True)
        )

    if legacy_skills:
        notices.append(
            "Legacy `.codex/project/skills/` is deprecated and remains migration-only."
        )

    return {
        "created": created,
        "migrated": migrated,
        "skipped": skipped,
        "notices": notices,
    }


def create_agent_bridges(repo_root: Path, vendor_agents_root: Path) -> dict[str, list[str]]:
    project_agents = ensure_project_agent_dir(repo_root)
    vendor_agents = iter_agent_files(vendor_agents_root)
    legacy_agents = iter_agent_files(repo_root / LEGACY_PROJECT_AGENTS_RELATIVE)

    created: list[str] = []
    migrated: list[str] = []
    skipped: list[str] = []
    notices: list[str] = []

    for agent_filename in sorted(set(vendor_agents) | set(legacy_agents)):
        target_path = project_agents / agent_filename
        if target_path.exists():
            skipped.append(
                f"{target_path.as_posix()} (existing root entry takes precedence)"
            )
            continue

        legacy_source = legacy_agents.get(agent_filename)
        if legacy_source is not None:
            migrated.append(
                create_symlink(target_path, legacy_source, is_directory=False)
            )
            notices.append(
                "Legacy `.codex/project/agents/` entry bridged for migration: "
                f"{Path(agent_filename).stem}. Move canonical ownership to "
                f"`.codex/agents/{agent_filename}`."
            )
            continue

        created.append(
            create_symlink(target_path, vendor_agents[agent_filename], is_directory=False)
        )

    if legacy_agents:
        notices.append(
            "Legacy `.codex/project/agents/` is deprecated and remains migration-only."
        )

    return {
        "created": created,
        "migrated": migrated,
        "skipped": skipped,
        "notices": notices,
    }


def create_non_agents(repo_root: Path) -> list[str]:
    created: list[str] = []

    profile_path = repo_root / PROJECT_PROFILE_RELATIVE
    write_text(profile_path, render_project_local_profile(repo_root))
    created.append(PROJECT_PROFILE_RELATIVE.as_posix())

    return created


def main() -> int:
    args = parse_args()

    try:
        repo_root = resolve_repo_root(args.repo_root)
        vendor_dir = require_vendor_subtree(repo_root)
        vendor_agents_root = require_vendor_agents_root(vendor_dir)
        vendor_skills_root = require_vendor_skills_root(vendor_dir)
        preflight_non_agents(repo_root)
        root_agents_status = update_root_agents(repo_root)
        codex_agents_status = update_codex_agents(repo_root)
        created = create_non_agents(repo_root)
        agent_bridge_report = create_agent_bridges(repo_root, vendor_agents_root)
        bridge_report = create_skill_bridges(repo_root, vendor_skills_root)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Initialized PacketFlow consumer scaffold at {repo_root.as_posix()}")
    print(f" - root AGENTS.md: {root_agents_status}")
    print(f" - .codex/AGENTS.md: {codex_agents_status}")
    for relative_path in created:
        print(f" - {relative_path}: created")
    print(f" - {PROJECT_AGENT_DISCOVERY_RELATIVE.as_posix()}: ready")
    for bridge in agent_bridge_report["created"]:
        print(f" - agent bridge: {bridge}")
    for bridge in agent_bridge_report["migrated"]:
        print(f" - legacy agent bridge: {bridge}")
    for bridge in agent_bridge_report["skipped"]:
        print(f" - skipped agent bridge: {bridge}")
    print(f" - {ROOT_SKILLS_RELATIVE.as_posix()}: ready")
    for bridge in bridge_report["created"]:
        print(f" - skill bridge: {bridge}")
    for bridge in bridge_report["migrated"]:
        print(f" - legacy skill bridge: {bridge}")
    for bridge in bridge_report["skipped"]:
        print(f" - skipped skill bridge: {bridge}")
    for notice in agent_bridge_report["notices"]:
        print(f"[NOTICE] {notice}", file=sys.stderr)
    for notice in bridge_report["notices"]:
        print(f"[NOTICE] {notice}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
