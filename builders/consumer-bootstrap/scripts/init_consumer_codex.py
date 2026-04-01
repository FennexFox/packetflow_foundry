#!/usr/bin/env python3
"""Initialize the minimum `.codex` layout for a PacketFlow Foundry consumer repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import TypeAlias, TypedDict


FOUNDRY_KEYWORDS = (
    "packetflow_foundry",
    "packetflow foundry",
    ".codex/vendor/packetflow_foundry",
)
BOOTSTRAP_MARKER_START = "<!-- packetflow_foundry consumer bootstrap:start -->"
BOOTSTRAP_MARKER_END = "<!-- packetflow_foundry consumer bootstrap:end -->"
CODEX_AGENTS_RELATIVE = Path(".codex/AGENTS.md")
ROOT_AGENTS_RELATIVE = Path("AGENTS.md")
GITIGNORE_RELATIVE = Path(".gitignore")
PROJECT_PROFILE_RELATIVE = Path(".codex/project/profiles/default/profile.json")
PROJECT_AGENT_DISCOVERY_RELATIVE = Path(".codex/agents")
LEGACY_PROJECT_AGENTS_RELATIVE = Path(".codex/project/agents")
ROOT_SKILLS_RELATIVE = Path(".agents/skills")
LEGACY_PROJECT_SKILLS_RELATIVE = Path(".codex/project/skills")
BRIDGE_STATE_RELATIVE = Path(".codex/project/bootstrap/bridge-state.json")
PROJECT_LOCAL_PROFILE_KIND = "project-local-scaffold-profile"
BRIDGE_STATE_KIND = "packetflow-foundry-bootstrap-bridge-state"
BRIDGE_STATE_VERSION = 1
BRIDGE_MODE_COPY = "copy"
BRIDGE_MODE_COPY_ON_FAIL = "copy-on-fail"
CODEX_TMP_GITIGNORE_ENTRY = ".codex/tmp/"
CODEX_TMP_GITIGNORE_ALIASES = frozenset(
    {
        ".codex/tmp",
        ".codex/tmp/",
        "/.codex/tmp",
        "/.codex/tmp/",
    }
)
CONFLICT_TARGETS = (
    PROJECT_PROFILE_RELATIVE,
)

BridgeEvent: TypeAlias = tuple[str, str]


class BridgeReport(TypedDict):
    events: list[BridgeEvent]
    notices: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(Path.cwd()),
        help="Consumer repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--bridge-mode",
        choices=(BRIDGE_MODE_COPY, BRIDGE_MODE_COPY_ON_FAIL),
        default=BRIDGE_MODE_COPY,
        help=(
            "Bridge strategy for vendored agents and skills. "
            "`copy` writes managed copies and refreshes them on rerun while "
            "they remain unchanged locally. `copy-on-fail` is kept as a "
            "deprecated compatibility alias for `copy`."
        ),
    )
    return parser.parse_args()


def normalize_bridge_mode(value: str) -> str:
    if value == BRIDGE_MODE_COPY_ON_FAIL:
        return BRIDGE_MODE_COPY
    return value


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


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def sha256_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_digest(path.read_bytes())


def relative_repo_path(path: Path, repo_root: Path) -> str:
    try:
        resolved_path = path.resolve()
    except OSError as exc:
        raise RuntimeError(
            "Failed to resolve bootstrap bridge source path: "
            f"{path.as_posix()}."
        ) from exc
    try:
        return resolved_path.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError(
            "Bootstrap bridge source path must resolve inside the repository root: "
            f"{path.as_posix()}."
        ) from exc


def default_bridge_state() -> dict[str, object]:
    return {
        "kind": BRIDGE_STATE_KIND,
        "version": BRIDGE_STATE_VERSION,
        "agents": {},
        "skills": {},
    }


def load_bridge_state(repo_root: Path) -> dict[str, object]:
    state_path = repo_root / BRIDGE_STATE_RELATIVE
    if not state_path.exists():
        return default_bridge_state()

    try:
        state = json.loads(read_text(state_path))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Malformed bootstrap bridge state at "
            f"{state_path.as_posix()}."
        ) from exc

    if not isinstance(state, dict):
        raise RuntimeError(
            "Malformed bootstrap bridge state at "
            f"{state_path.as_posix()}."
        )
    if state.get("kind") != BRIDGE_STATE_KIND or state.get("version") != BRIDGE_STATE_VERSION:
        raise RuntimeError(
            "Unsupported bootstrap bridge state at "
            f"{state_path.as_posix()}."
        )
    for key in ("agents", "skills"):
        if not isinstance(state.get(key), dict):
            raise RuntimeError(
                "Malformed bootstrap bridge state at "
                f"{state_path.as_posix()}."
            )
    return state


def save_bridge_state(repo_root: Path, state: dict[str, object]) -> None:
    write_text(
        repo_root / BRIDGE_STATE_RELATIVE,
        json.dumps(state, indent=2, ensure_ascii=True),
    )


def delete_bridge_state(repo_root: Path) -> None:
    state_path = repo_root / BRIDGE_STATE_RELATIVE
    if state_path.exists():
        state_path.unlink()


def persist_bridge_state(repo_root: Path, state: dict[str, object]) -> None:
    if bridge_state_has_entries(state):
        save_bridge_state(repo_root, state)
    else:
        delete_bridge_state(repo_root)


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
                "surface. Bootstrap writes managed copies of vendored foundry "
                "agent TOMLs there from "
                "`.codex/vendor/packetflow_foundry/.codex/agents/`."
            ),
            (
                "- `.agents/skills/` is a thin discovery-wrapper surface. "
                "Bootstrap writes managed copies of vendored wrappers there "
                "while reusable retained kernels stay under "
                "`.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`."
            ),
            (
                "- Rerun consumer bootstrap after updating the vendor subtree "
                "to refresh managed agent and skill copies that were not "
                "modified locally."
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


def ensure_gitignore_target(path: Path) -> None:
    if path.exists() and not path.is_file():
        raise RuntimeError(f".gitignore target is not a file: {path.as_posix()}")


def contains_codex_tmp_gitignore(text: str) -> bool:
    return any(line.strip() in CODEX_TMP_GITIGNORE_ALIASES for line in text.splitlines())


def append_gitignore_entry(existing: str, entry: str) -> str:
    stripped = existing.rstrip()
    if not stripped:
        return entry
    return stripped + "\n" + entry


def update_gitignore(repo_root: Path) -> str:
    path = repo_root / GITIGNORE_RELATIVE
    ensure_gitignore_target(path)
    if not path.exists():
        write_text(path, CODEX_TMP_GITIGNORE_ENTRY)
        return f"created with {CODEX_TMP_GITIGNORE_ENTRY}"
    existing = read_text(path)
    if contains_codex_tmp_gitignore(existing):
        return "unchanged"
    write_text(path, append_gitignore_entry(existing, CODEX_TMP_GITIGNORE_ENTRY))
    return f"appended {CODEX_TMP_GITIGNORE_ENTRY}"


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


def is_existing_project_local_profile(path: Path) -> bool:
    try:
        document = json.loads(read_text(path))
    except json.JSONDecodeError:
        return False
    if not isinstance(document, dict):
        return False
    return (
        document.get("kind") == PROJECT_LOCAL_PROFILE_KIND
        and document.get("profile_path") == PROJECT_PROFILE_RELATIVE.as_posix()
    )


def preflight_non_agents(repo_root: Path) -> None:
    conflicts: list[str] = []
    for relative_path in CONFLICT_TARGETS:
        target = repo_root / relative_path
        if target.exists():
            if relative_path == PROJECT_PROFILE_RELATIVE and is_existing_project_local_profile(
                target
            ):
                continue
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
        if child.is_dir():
            validate_managed_source_directory(
                child,
                source_root=root,
                bridge_kind="skill",
                root_label="skill root",
            )
        if child.is_dir() and (child / "SKILL.md").is_file():
            skills[child.name] = child
    return skills


def path_has_reparse_point(path: Path) -> bool:
    try:
        file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def validate_managed_source_directory(
    path: Path,
    *,
    source_root: Path,
    bridge_kind: str,
    root_label: str,
) -> None:
    if path.is_symlink() or path_has_reparse_point(path):
        raise RuntimeError(
            f"Managed {bridge_kind} bridge source contains unsupported linked directory: "
            f"{path.as_posix()}."
        )
    try:
        resolved_path = path.resolve()
    except OSError as exc:
        raise RuntimeError(
            f"Failed to resolve managed {bridge_kind} bridge source: "
            f"{path.as_posix()}."
        ) from exc
    try:
        resolved_path.relative_to(source_root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Managed {bridge_kind} bridge source resolves outside the {root_label}: "
            f"{path.as_posix()}."
        ) from exc


def validate_managed_source_file(
    path: Path,
    *,
    source_root: Path,
    bridge_kind: str,
    root_label: str,
) -> None:
    if path.is_symlink():
        raise RuntimeError(
            f"Managed {bridge_kind} bridge source contains unsupported symlinked file: "
            f"{path.as_posix()}."
        )
    try:
        resolved_path = path.resolve()
    except OSError as exc:
        raise RuntimeError(
            f"Failed to resolve managed {bridge_kind} bridge source: "
            f"{path.as_posix()}."
        ) from exc
    try:
        resolved_path.relative_to(source_root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Managed {bridge_kind} bridge source resolves outside the {root_label}: "
            f"{path.as_posix()}."
        ) from exc


def iter_agent_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    agents: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda entry: entry.name):
        if child.is_file() and child.suffix == ".toml":
            validate_managed_source_file(
                child,
                source_root=root,
                bridge_kind="agent",
                root_label="agent root",
            )
            agents[child.name] = child
    return agents


def iter_relative_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    files: dict[str, Path] = {}
    for child in sorted(root.rglob("*")):
        if child.is_file():
            files[child.relative_to(root).as_posix()] = child
    return files


def remove_empty_parent_dirs(path: Path, *, stop: Path) -> None:
    current = path.parent
    while current != stop and current.exists():
        if any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def same_resolved_path(path: Path, other: Path) -> bool:
    try:
        return path.resolve() == other.resolve()
    except OSError:
        return False


def maybe_remove_expected_bridge_symlink(target_path: Path, source_path: Path) -> bool:
    if not target_path.is_symlink():
        return False
    if not same_resolved_path(target_path, source_path):
        return False
    target_path.unlink()
    return True


def skill_bridge_anchor(repo_root: Path, source_root: Path) -> Path | None:
    vendor_skills_root = repo_root / ".codex" / "vendor" / "packetflow_foundry" / ".agents" / "skills"
    legacy_skills_root = repo_root / LEGACY_PROJECT_SKILLS_RELATIVE
    if path_is_within(source_root, vendor_skills_root):
        return repo_root / ".codex" / "vendor" / "packetflow_foundry"
    if path_is_within(source_root, legacy_skills_root):
        return repo_root
    return None


def rewrite_skill_wrapper_for_target(
    repo_root: Path,
    source_root: Path,
    target_root: Path,
    content: bytes,
) -> bytes:
    anchor = skill_bridge_anchor(repo_root, source_root)
    if anchor is None:
        return content

    source_prefix = Path(os.path.relpath(anchor / "builders", start=source_root)).as_posix()
    target_prefix = Path(os.path.relpath(anchor / "builders", start=target_root)).as_posix()
    source_token = f"{source_prefix}/"
    target_token = f"{target_prefix}/"

    text = content.decode("utf-8")
    if source_token not in text:
        return content
    return text.replace(source_token, target_token).encode("utf-8")


def build_skill_bridge_files(
    repo_root: Path,
    source_root: Path,
    target_root: Path,
) -> dict[str, bytes]:
    copied_files: dict[str, bytes] = {}
    for relative_path, source_file in iter_relative_files(source_root).items():
        validate_managed_source_file(
            source_file,
            source_root=source_root,
            bridge_kind="skill",
            root_label="skill root",
        )
        content = source_file.read_bytes()
        if relative_path == "SKILL.md":
            content = rewrite_skill_wrapper_for_target(
                repo_root,
                source_root,
                target_root,
                content,
            )
        copied_files[relative_path] = content
    return copied_files


def append_bridge_event(
    events: list[BridgeEvent],
    *,
    bridge_kind: str,
    status: str,
    detail: str,
    legacy: bool = False,
    migrated: bool = False,
) -> None:
    if status == "unchanged":
        return

    words: list[str] = []
    if status == "refreshed":
        words.append("refreshed")
    if migrated:
        words.append("migrated")
    if legacy:
        words.append("legacy")
    if status == "removed":
        words.append("removed")
    elif status in {"copied", "refreshed"}:
        words.append("copied")
    elif status == "skipped":
        words.append("skipped")
    else:
        raise RuntimeError(f"Unsupported bridge status: {status}")

    words.extend((bridge_kind, "bridge"))
    events.append((" ".join(words), detail))


def bridge_state_group(
    state: dict[str, object],
    key: str,
) -> dict[str, object]:
    group = state.get(key)
    if not isinstance(group, dict):
        raise RuntimeError(
            "Malformed bootstrap bridge state at "
            f"{BRIDGE_STATE_RELATIVE.as_posix()}."
        )
    return group


def build_file_copy_state_entry(repo_root: Path, source_path: Path) -> dict[str, str]:
    return {
        "type": "file-copy",
        "source": relative_repo_path(source_path, repo_root),
        "sha256": sha256_path(source_path),
    }


def build_directory_copy_state_entry(
    repo_root: Path,
    source_root: Path,
    copied_files: dict[str, bytes],
) -> dict[str, object]:
    return {
        "type": "directory-copy",
        "source": relative_repo_path(source_root, repo_root),
        "files": {
            relative_path: {"sha256": sha256_digest(content)}
            for relative_path, content in copied_files.items()
        },
    }


def validate_file_copy_state_entry(
    entry: object,
    *,
    bridge_name: str,
) -> str:
    if not isinstance(entry, dict) or entry.get("type") != "file-copy":
        raise RuntimeError(f"Malformed managed file copy state for {bridge_name}.")
    expected_hash = entry.get("sha256")
    if not isinstance(expected_hash, str):
        raise RuntimeError(f"Malformed managed file copy state for {bridge_name}.")
    return expected_hash


def validate_directory_copy_state_entry(
    entry: object,
    *,
    bridge_name: str,
) -> dict[str, str]:
    if not isinstance(entry, dict) or entry.get("type") != "directory-copy":
        raise RuntimeError(f"Malformed managed directory copy state for {bridge_name}.")
    raw_files = entry.get("files")
    if not isinstance(raw_files, dict):
        raise RuntimeError(f"Malformed managed directory copy state for {bridge_name}.")

    validated: dict[str, str] = {}
    for relative_path, metadata in raw_files.items():
        if not isinstance(relative_path, str) or not isinstance(metadata, dict):
            raise RuntimeError(f"Malformed managed directory copy state for {bridge_name}.")
        expected_hash = metadata.get("sha256")
        if not isinstance(expected_hash, str):
            raise RuntimeError(f"Malformed managed directory copy state for {bridge_name}.")
        validated[relative_path] = expected_hash
    return validated


def sync_directory_copy(
    target_root: Path,
    copied_files: dict[str, bytes],
    *,
    previous_files: set[str] | None = None,
) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    if previous_files is not None:
        for relative_path in sorted(previous_files - set(copied_files)):
            stale_file = target_root / Path(relative_path)
            if stale_file.exists():
                stale_file.unlink()
                remove_empty_parent_dirs(stale_file, stop=target_root)

    for relative_path, content in copied_files.items():
        write_bytes(target_root / Path(relative_path), content)


def sync_managed_file_copy(
    repo_root: Path,
    source_path: Path,
    target_path: Path,
    *,
    bridge_name: str,
    state_group: dict[str, object],
) -> tuple[str, str, str | None]:
    state_entry = build_file_copy_state_entry(repo_root, source_path)
    source_hash = str(state_entry["sha256"])
    entry = state_group.get(bridge_name)
    if entry is not None:
        expected_hash = validate_file_copy_state_entry(entry, bridge_name=bridge_name)
        existed_before = target_path.exists()
        if target_path.exists():
            if target_path.is_symlink() or not target_path.is_file():
                return (
                    "skipped",
                    (
                        f"{target_path.as_posix()} "
                        "(managed copy target is no longer a regular file)"
                    ),
                    (
                        "Managed copied agent bridge no longer points to a regular file: "
                        f"{target_path.as_posix()}. Remove it to resume bootstrap refreshes."
                    ),
                )
            current_hash = sha256_path(target_path)
            if current_hash != expected_hash:
                return (
                    "skipped",
                    (
                        f"{target_path.as_posix()} "
                        "(managed copy was modified locally; leaving in place)"
                    ),
                    (
                        "Managed copied agent bridge was modified locally and was not "
                        f"overwritten: {target_path.as_posix()}."
                    ),
                )
            if source_hash == expected_hash:
                return "unchanged", target_path.as_posix(), None

        write_bytes(target_path, source_path.read_bytes())
        state_group[bridge_name] = state_entry
        status = "refreshed" if existed_before else "copied"
        return status, f"{target_path.as_posix()} <- {source_path.as_posix()}", None

    write_bytes(target_path, source_path.read_bytes())
    state_group[bridge_name] = state_entry
    return "copied", f"{target_path.as_posix()} <- {source_path.as_posix()}", None


def sync_managed_directory_copy(
    repo_root: Path,
    source_root: Path,
    target_root: Path,
    *,
    bridge_name: str,
    state_group: dict[str, object],
) -> tuple[str, str, str | None]:
    validate_managed_source_directory(
        source_root,
        source_root=source_root,
        bridge_kind="skill",
        root_label="skill root",
    )
    relative_repo_path(source_root, repo_root)
    copied_files = build_skill_bridge_files(repo_root, source_root, target_root)
    state_entry = build_directory_copy_state_entry(
        repo_root,
        source_root,
        copied_files,
    )
    entry = state_group.get(bridge_name)
    if entry is not None:
        expected_hashes = validate_directory_copy_state_entry(entry, bridge_name=bridge_name)
        if target_root.exists():
            if target_root.is_symlink() or not target_root.is_dir():
                return (
                    "skipped",
                    (
                        f"{target_root.as_posix()} "
                        "(managed copy target is no longer a regular directory)"
                    ),
                    (
                        "Managed copied skill bridge no longer points to a regular directory: "
                        f"{target_root.as_posix()}. Remove it to resume bootstrap refreshes."
                    ),
                )

            target_files = iter_relative_files(target_root)
            for relative_path, target_file in target_files.items():
                if target_file.is_symlink() or not target_file.is_file():
                    return (
                        "skipped",
                        (
                            f"{target_root.as_posix()} "
                            "(managed copy contents were modified locally; leaving in place)"
                        ),
                        (
                            "Managed copied skill bridge was modified locally and was not "
                            f"overwritten: {target_root.as_posix()}."
                        ),
                    )
                expected_hash = expected_hashes.get(relative_path)
                if expected_hash is None:
                    return (
                        "skipped",
                        (
                            f"{target_root.as_posix()} "
                            "(managed copy contents were modified locally; leaving in place)"
                        ),
                        (
                            "Managed copied skill bridge was modified locally and was not "
                            f"overwritten: {target_root.as_posix()}."
                        ),
                    )
                if sha256_path(target_file) != expected_hash:
                    return (
                        "skipped",
                        (
                            f"{target_root.as_posix()} "
                            "(managed copy contents were modified locally; leaving in place)"
                        ),
                        (
                            "Managed copied skill bridge was modified locally and was not "
                            f"overwritten: {target_root.as_posix()}."
                        ),
                    )

            copied_hashes = {
                relative_path: sha256_digest(content)
                for relative_path, content in copied_files.items()
            }
            if copied_hashes == expected_hashes and set(target_files) == set(expected_hashes):
                return "unchanged", target_root.as_posix(), None

            sync_directory_copy(
                target_root,
                copied_files,
                previous_files=set(target_files),
            )
            state_group[bridge_name] = state_entry
            return "refreshed", f"{target_root.as_posix()} <- {source_root.as_posix()}", None

    sync_directory_copy(target_root, copied_files)
    state_group[bridge_name] = state_entry
    return "copied", f"{target_root.as_posix()} <- {source_root.as_posix()}", None


def prune_stale_managed_file_copy(
    target_path: Path,
    *,
    managed_root: Path,
    bridge_name: str,
    state_group: dict[str, object],
) -> tuple[str, str, str | None]:
    entry = state_group.get(bridge_name)
    if entry is None:
        return "unchanged", target_path.as_posix(), None

    expected_hash = validate_file_copy_state_entry(entry, bridge_name=bridge_name)
    if not target_path.exists():
        state_group.pop(bridge_name, None)
        return "unchanged", target_path.as_posix(), None
    if target_path.is_symlink() or not target_path.is_file():
        return (
            "skipped",
            (
                f"{target_path.as_posix()} "
                "(managed copy target is no longer a regular file after upstream deletion)"
            ),
            (
                "Managed copied agent bridge no longer points to a regular file after "
                f"upstream deletion: {target_path.as_posix()}. Remove it to clear the "
                "stale bootstrap entry."
            ),
        )

    current_hash = sha256_path(target_path)
    if current_hash != expected_hash:
        return (
            "skipped",
            (
                f"{target_path.as_posix()} "
                "(managed copy was modified locally after upstream deletion; leaving in place)"
            ),
            (
                "Managed copied agent bridge was modified locally after upstream deletion "
                f"and was not removed: {target_path.as_posix()}."
            ),
        )

    target_path.unlink()
    remove_empty_parent_dirs(target_path, stop=managed_root)
    state_group.pop(bridge_name, None)
    return "removed", f"{target_path.as_posix()} (upstream source was deleted)", None


def prune_stale_managed_directory_copy(
    target_root: Path,
    *,
    managed_root: Path,
    bridge_name: str,
    state_group: dict[str, object],
) -> tuple[str, str, str | None]:
    entry = state_group.get(bridge_name)
    if entry is None:
        return "unchanged", target_root.as_posix(), None

    expected_hashes = validate_directory_copy_state_entry(entry, bridge_name=bridge_name)
    if not target_root.exists():
        state_group.pop(bridge_name, None)
        return "unchanged", target_root.as_posix(), None
    if target_root.is_symlink() or not target_root.is_dir():
        return (
            "skipped",
            (
                f"{target_root.as_posix()} "
                "(managed copy target is no longer a regular directory after upstream deletion)"
            ),
            (
                "Managed copied skill bridge no longer points to a regular directory after "
                f"upstream deletion: {target_root.as_posix()}. Remove it to clear the stale "
                "bootstrap entry."
            ),
        )

    target_files = iter_relative_files(target_root)
    if set(target_files) != set(expected_hashes):
        return (
            "skipped",
            (
                f"{target_root.as_posix()} "
                "(managed copy contents were modified locally after upstream deletion; leaving in place)"
            ),
            (
                "Managed copied skill bridge was modified locally after upstream deletion "
                f"and was not removed: {target_root.as_posix()}."
            ),
        )

    for relative_path, target_file in target_files.items():
        if target_file.is_symlink() or not target_file.is_file():
            return (
                "skipped",
                (
                    f"{target_root.as_posix()} "
                    "(managed copy contents were modified locally after upstream deletion; leaving in place)"
                ),
                (
                    "Managed copied skill bridge was modified locally after upstream deletion "
                    f"and was not removed: {target_root.as_posix()}."
                ),
            )
        if sha256_path(target_file) != expected_hashes[relative_path]:
            return (
                "skipped",
                (
                    f"{target_root.as_posix()} "
                    "(managed copy contents were modified locally after upstream deletion; leaving in place)"
                ),
                (
                    "Managed copied skill bridge was modified locally after upstream deletion "
                    f"and was not removed: {target_root.as_posix()}."
                ),
            )

    shutil.rmtree(target_root)
    remove_empty_parent_dirs(target_root, stop=managed_root)
    state_group.pop(bridge_name, None)
    return "removed", f"{target_root.as_posix()} (upstream source was deleted)", None


def bridge_state_has_entries(state: dict[str, object]) -> bool:
    return bool(bridge_state_group(state, "agents")) or bool(bridge_state_group(state, "skills"))


def create_skill_bridges(
    repo_root: Path,
    vendor_skills_root: Path,
    *,
    bridge_state: dict[str, object],
) -> BridgeReport:
    root_skills = ensure_root_skill_dir(repo_root)
    vendor_skills = iter_skill_directories(vendor_skills_root)
    legacy_skills = iter_skill_directories(repo_root / LEGACY_PROJECT_SKILLS_RELATIVE)
    skill_state = bridge_state_group(bridge_state, "skills")

    events: list[BridgeEvent] = []
    notices: list[str] = []

    for skill_name in sorted(set(vendor_skills) | set(legacy_skills)):
        target_path = root_skills / skill_name
        legacy_source = legacy_skills.get(skill_name)
        source_path = legacy_source or vendor_skills[skill_name]
        managed_copy_exists = skill_name in skill_state
        if maybe_remove_expected_bridge_symlink(target_path, source_path):
            status, detail, notice = sync_managed_directory_copy(
                repo_root,
                source_path,
                target_path,
                bridge_name=skill_name,
                state_group=skill_state,
            )
            persist_bridge_state(repo_root, bridge_state)
            append_bridge_event(
                events,
                bridge_kind="skill",
                status=status,
                detail=detail,
                legacy=legacy_source is not None,
                migrated=True,
            )
            if notice is not None:
                notices.append(notice)
            if legacy_source is not None:
                notices.append(
                    "Legacy `.codex/project/skills/` entry bridged for migration: "
                    f"{skill_name}. Move canonical ownership to `.agents/skills/{skill_name}`."
                )
            continue

        if target_path.is_symlink():
            events.append(
                (
                    "skipped skill bridge",
                    f"{target_path.as_posix()} (existing root symlink takes precedence)",
                )
            )
            continue

        if target_path.exists():
            if managed_copy_exists:
                status, detail, notice = sync_managed_directory_copy(
                    repo_root,
                    source_path,
                    target_path,
                    bridge_name=skill_name,
                    state_group=skill_state,
                )
                persist_bridge_state(repo_root, bridge_state)
                append_bridge_event(
                    events,
                    bridge_kind="skill",
                    status=status,
                    detail=detail,
                )
                if notice is not None:
                    notices.append(notice)
                continue

            events.append(
                (
                    "skipped skill bridge",
                    f"{target_path.as_posix()} (existing root entry takes precedence)",
                )
            )
            continue

        if legacy_source is not None:
            status, detail, notice = sync_managed_directory_copy(
                repo_root,
                legacy_source,
                target_path,
                bridge_name=skill_name,
                state_group=skill_state,
            )
            persist_bridge_state(repo_root, bridge_state)
            append_bridge_event(
                events,
                bridge_kind="skill",
                status=status,
                detail=detail,
                legacy=True,
            )
            if notice is not None:
                notices.append(notice)

            notices.append(
                "Legacy `.codex/project/skills/` entry bridged for migration: "
                f"{skill_name}. Move canonical ownership to `.agents/skills/{skill_name}`."
            )
            continue

        status, detail, notice = sync_managed_directory_copy(
            repo_root,
            source_path,
            target_path,
            bridge_name=skill_name,
            state_group=skill_state,
        )
        persist_bridge_state(repo_root, bridge_state)
        append_bridge_event(
            events,
            bridge_kind="skill",
            status=status,
            detail=detail,
        )
        if notice is not None:
            notices.append(notice)

    stale_skill_names = sorted(set(skill_state) - set(vendor_skills) - set(legacy_skills))
    for skill_name in stale_skill_names:
        status, detail, notice = prune_stale_managed_directory_copy(
            root_skills / skill_name,
            managed_root=root_skills,
            bridge_name=skill_name,
            state_group=skill_state,
        )
        persist_bridge_state(repo_root, bridge_state)
        append_bridge_event(
            events,
            bridge_kind="skill",
            status=status,
            detail=detail,
        )
        if notice is not None:
            notices.append(notice)

    if legacy_skills:
        notices.append(
            "Legacy `.codex/project/skills/` is deprecated and remains migration-only."
        )

    return {
        "events": events,
        "notices": notices,
    }


def create_agent_bridges(
    repo_root: Path,
    vendor_agents_root: Path,
    *,
    bridge_state: dict[str, object],
) -> BridgeReport:
    project_agents = ensure_project_agent_dir(repo_root)
    vendor_agents = iter_agent_files(vendor_agents_root)
    legacy_agents = iter_agent_files(repo_root / LEGACY_PROJECT_AGENTS_RELATIVE)
    agent_state = bridge_state_group(bridge_state, "agents")

    events: list[BridgeEvent] = []
    notices: list[str] = []

    for agent_filename in sorted(set(vendor_agents) | set(legacy_agents)):
        target_path = project_agents / agent_filename
        legacy_source = legacy_agents.get(agent_filename)
        source_path = legacy_source or vendor_agents[agent_filename]
        managed_copy_exists = agent_filename in agent_state
        if maybe_remove_expected_bridge_symlink(target_path, source_path):
            status, detail, notice = sync_managed_file_copy(
                repo_root,
                source_path,
                target_path,
                bridge_name=agent_filename,
                state_group=agent_state,
            )
            persist_bridge_state(repo_root, bridge_state)
            append_bridge_event(
                events,
                bridge_kind="agent",
                status=status,
                detail=detail,
                legacy=legacy_source is not None,
                migrated=True,
            )
            if notice is not None:
                notices.append(notice)
            if legacy_source is not None:
                notices.append(
                    "Legacy `.codex/project/agents/` entry bridged for migration: "
                    f"{Path(agent_filename).stem}. Move canonical ownership to "
                    f"`.codex/agents/{agent_filename}`."
                )
            continue

        if target_path.is_symlink():
            events.append(
                (
                    "skipped agent bridge",
                    f"{target_path.as_posix()} (existing root symlink takes precedence)",
                )
            )
            continue

        if target_path.exists():
            if managed_copy_exists:
                status, detail, notice = sync_managed_file_copy(
                    repo_root,
                    source_path,
                    target_path,
                    bridge_name=agent_filename,
                    state_group=agent_state,
                )
                persist_bridge_state(repo_root, bridge_state)
                append_bridge_event(
                    events,
                    bridge_kind="agent",
                    status=status,
                    detail=detail,
                )
                if notice is not None:
                    notices.append(notice)
                continue

            events.append(
                (
                    "skipped agent bridge",
                    f"{target_path.as_posix()} (existing root entry takes precedence)",
                )
            )
            continue

        if legacy_source is not None:
            status, detail, notice = sync_managed_file_copy(
                repo_root,
                legacy_source,
                target_path,
                bridge_name=agent_filename,
                state_group=agent_state,
            )
            persist_bridge_state(repo_root, bridge_state)
            append_bridge_event(
                events,
                bridge_kind="agent",
                status=status,
                detail=detail,
                legacy=True,
            )
            if notice is not None:
                notices.append(notice)

            notices.append(
                "Legacy `.codex/project/agents/` entry bridged for migration: "
                f"{Path(agent_filename).stem}. Move canonical ownership to "
                f"`.codex/agents/{agent_filename}`."
            )
            continue

        status, detail, notice = sync_managed_file_copy(
            repo_root,
            source_path,
            target_path,
            bridge_name=agent_filename,
            state_group=agent_state,
        )
        persist_bridge_state(repo_root, bridge_state)
        append_bridge_event(
            events,
            bridge_kind="agent",
            status=status,
            detail=detail,
        )
        if notice is not None:
            notices.append(notice)

    stale_agent_names = sorted(set(agent_state) - set(vendor_agents) - set(legacy_agents))
    for agent_filename in stale_agent_names:
        status, detail, notice = prune_stale_managed_file_copy(
            project_agents / agent_filename,
            managed_root=project_agents,
            bridge_name=agent_filename,
            state_group=agent_state,
        )
        persist_bridge_state(repo_root, bridge_state)
        append_bridge_event(
            events,
            bridge_kind="agent",
            status=status,
            detail=detail,
        )
        if notice is not None:
            notices.append(notice)

    if legacy_agents:
        notices.append(
            "Legacy `.codex/project/agents/` is deprecated and remains migration-only."
        )

    return {
        "events": events,
        "notices": notices,
    }


def create_non_agents(repo_root: Path) -> list[str]:
    created: list[str] = []

    profile_path = repo_root / PROJECT_PROFILE_RELATIVE
    if profile_path.exists():
        if not is_existing_project_local_profile(profile_path):
            raise RuntimeError(
                "Refusing to overwrite existing bootstrap outputs: "
                f"{PROJECT_PROFILE_RELATIVE.as_posix()}. "
                "AGENTS.md append targets are the only exception."
            )
        return created

    write_text(profile_path, render_project_local_profile(repo_root))
    created.append(PROJECT_PROFILE_RELATIVE.as_posix())

    return created


def main() -> int:
    args = parse_args()

    try:
        repo_root = resolve_repo_root(args.repo_root)
        bridge_mode = normalize_bridge_mode(args.bridge_mode)
        bridge_state = load_bridge_state(repo_root)
        vendor_dir = require_vendor_subtree(repo_root)
        vendor_agents_root = require_vendor_agents_root(vendor_dir)
        vendor_skills_root = require_vendor_skills_root(vendor_dir)
        preflight_non_agents(repo_root)
        root_agents_status = update_root_agents(repo_root)
        codex_agents_status = update_codex_agents(repo_root)
        gitignore_status = update_gitignore(repo_root)
        created = create_non_agents(repo_root)
        agent_bridge_report = create_agent_bridges(
            repo_root,
            vendor_agents_root,
            bridge_state=bridge_state,
        )
        persist_bridge_state(repo_root, bridge_state)
        bridge_report = create_skill_bridges(
            repo_root,
            vendor_skills_root,
            bridge_state=bridge_state,
        )
        persist_bridge_state(repo_root, bridge_state)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Initialized PacketFlow consumer scaffold at {repo_root.as_posix()}")
    print(f" - bridge mode: {bridge_mode}")
    print(f" - root AGENTS.md: {root_agents_status}")
    print(f" - .codex/AGENTS.md: {codex_agents_status}")
    print(f" - {GITIGNORE_RELATIVE.as_posix()}: {gitignore_status}")
    for relative_path in created:
        print(f" - {relative_path}: created")
    print(f" - {PROJECT_AGENT_DISCOVERY_RELATIVE.as_posix()}: ready")
    for label, detail in agent_bridge_report["events"]:
        print(f" - {label}: {detail}")
    print(f" - {ROOT_SKILLS_RELATIVE.as_posix()}: ready")
    for label, detail in bridge_report["events"]:
        print(f" - {label}: {detail}")
    for notice in agent_bridge_report["notices"]:
        print(f"[NOTICE] {notice}", file=sys.stderr)
    for notice in bridge_report["notices"]:
        print(f"[NOTICE] {notice}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
