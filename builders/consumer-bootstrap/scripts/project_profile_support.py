#!/usr/bin/env python3
"""Shared project-local profile helpers for consumer bootstrap and sync."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


PACKET_WORKFLOW_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "packet-workflow" / "scripts"
if str(PACKET_WORKFLOW_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PACKET_WORKFLOW_SCRIPT_DIR))

from packet_workflow_versioning import load_builder_versioning  # type: ignore  # noqa: E402


PROJECT_PROFILES_ROOT_RELATIVE = Path(".codex/project/profiles")
PROJECT_PROFILE_RELATIVE = PROJECT_PROFILES_ROOT_RELATIVE / "default" / "profile.json"
PROJECT_LOCAL_PROFILE_KIND = "project-local-profile"
LEGACY_PROJECT_LOCAL_PROFILE_KINDS = frozenset({"project-local-scaffold-profile"})


def project_root_markers(repo_root: Path) -> list[str]:
    markers = [".git"]
    if (repo_root / "README.md").is_file():
        markers.append("README.md")
    return markers


def project_local_profile_relative(skill_name: str) -> Path:
    return PROJECT_PROFILES_ROOT_RELATIVE / skill_name / "profile.json"


def project_local_profile_versioning(
    current_builder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    builder = current_builder or load_builder_versioning()
    return {
        "builder_family": builder["builder_family"],
        "builder_semver": builder["builder_semver"],
        "compatibility_epoch": builder["compatibility_epoch"],
        "repo_profile_schema_version": builder["repo_profile_schema_version"],
    }


def build_default_project_local_profile(
    repo_root: Path,
    *,
    current_builder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": PROJECT_LOCAL_PROFILE_KIND,
        "name": "default",
        "profile_path": PROJECT_PROFILE_RELATIVE.as_posix(),
        "summary": (
            "Project-local scaffold for this consumer repository. "
            "Keep repo-wide defaults here and put skill-specific bindings in "
            "skill-named profiles."
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
                "Keep this profile data-only: add repo-specific bindings, review docs, "
                "booleans, and notes here."
            ),
            (
                "Skill-specific packet-workflow bindings should live in "
                "`.codex/project/profiles/<skill-name>/profile.json` instead "
                "of this default scaffold."
            ),
        ],
        "metadata": {
            "versioning": project_local_profile_versioning(current_builder),
        },
    }


def build_skill_project_local_profile(
    repo_root: Path,
    *,
    skill_name: str,
    retained_profile: dict[str, Any],
    current_builder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = copy.deepcopy(retained_profile)
    if not isinstance(payload, dict):
        raise RuntimeError("Retained repo profile must be a JSON object.")

    project_profile_relative = project_local_profile_relative(skill_name)
    apply_project_local_owned_fields(
        payload,
        skill_name=skill_name,
        profile_relative=project_profile_relative,
        current_builder=current_builder,
    )

    payload["summary"] = (
        f"Project-local {skill_name} profile scaffold for this consumer repository. "
        "Replace retained defaults with repo-specific bindings, review docs, "
        "and local notes."
    )

    repo_match = payload.get("repo_match")
    if not isinstance(repo_match, dict):
        repo_match = {}
        payload["repo_match"] = repo_match
    repo_match.setdefault("root_markers", project_root_markers(repo_root))
    repo_match.setdefault("remote_patterns", [])

    existing_notes = payload.get("notes")
    retained_notes = existing_notes if isinstance(existing_notes, list) else []
    payload["notes"] = _merged_string_notes(
        [
            (
                "This file is a project-local skill profile for one consumer repository."
            ),
            (
                "It is not a reusable foundry overlay and should stay outside "
                "the vendor subtree."
            ),
            (
                "Keep this profile data-only: add repo-specific bindings, review docs, "
                "booleans, and notes here."
            ),
            (
                "Review retained defaults before trusting this profile; unchanged "
                "values may still be reusable placeholders."
            ),
        ],
        retained_notes,
    )
    return payload


def apply_project_local_owned_fields(
    payload: dict[str, Any],
    *,
    skill_name: str,
    profile_relative: Path,
    current_builder: dict[str, Any] | None = None,
) -> None:
    payload["kind"] = PROJECT_LOCAL_PROFILE_KIND
    payload["name"] = skill_name
    payload["profile_path"] = profile_relative.as_posix()
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        payload["metadata"] = metadata
    metadata["versioning"] = project_local_profile_versioning(current_builder)


def render_json_document(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def is_existing_project_local_profile_payload(
    payload: Any,
    *,
    expected_profile_path: str,
) -> bool:
    if not isinstance(payload, dict):
        return False
    kind = payload.get("kind")
    if kind not in {PROJECT_LOCAL_PROFILE_KIND, *LEGACY_PROJECT_LOCAL_PROFILE_KINDS}:
        return False
    return payload.get("profile_path") == expected_profile_path


def is_existing_project_local_profile(path: Path, *, expected_profile_path: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    return is_existing_project_local_profile_payload(
        payload,
        expected_profile_path=expected_profile_path,
    )


def _merged_string_notes(*groups: list[Any]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged
