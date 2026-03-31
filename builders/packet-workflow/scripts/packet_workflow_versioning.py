#!/usr/bin/env python3
"""Shared builder-version compatibility helpers for packet-workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


STATUS_CURRENT = "current"
STATUS_SEMVER_BEHIND_COMPATIBLE = "semver-behind-compatible"
STATUS_STALE_SKILL = "stale-skill"
STATUS_STALE_PROFILE = "stale-profile"
STATUS_MISSING_SKILL_VERSIONING = "missing-skill-versioning"
STATUS_MISSING_PROFILE_VERSIONING = "missing-profile-versioning"
STATUS_AHEAD_OF_BUILDER = "ahead-of-builder"

BLOCKING_STATUSES = {
    STATUS_STALE_SKILL,
    STATUS_STALE_PROFILE,
    STATUS_MISSING_SKILL_VERSIONING,
    STATUS_MISSING_PROFILE_VERSIONING,
    STATUS_AHEAD_OF_BUILDER,
}

SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


def foundry_root_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def canonical_builder_version_path() -> Path:
    return foundry_root_dir() / "builders" / "packet-workflow" / "version.json"


def canonical_retained_skills_root() -> Path:
    return foundry_root_dir() / "builders" / "packet-workflow" / "retained-skills"


def load_json_document(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_document(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def parse_semver(value: Any) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    match = SEMVER_RE.fullmatch(text)
    if match is None:
        return None
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def normalize_versioning_block(
    value: Any,
    *,
    require_builder_spec_schema_version: bool,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    builder_family = value.get("builder_family")
    builder_semver = value.get("builder_semver")
    compatibility_epoch = value.get("compatibility_epoch")
    repo_profile_schema_version = value.get("repo_profile_schema_version")
    if not isinstance(builder_family, str) or not builder_family.strip():
        return None
    if parse_semver(builder_semver) is None:
        return None
    if not isinstance(compatibility_epoch, int):
        return None
    if not isinstance(repo_profile_schema_version, int):
        return None
    normalized = {
        "builder_family": builder_family.strip(),
        "builder_semver": str(builder_semver).strip(),
        "compatibility_epoch": compatibility_epoch,
        "repo_profile_schema_version": repo_profile_schema_version,
    }
    if require_builder_spec_schema_version:
        builder_spec_schema_version = value.get("builder_spec_schema_version")
        if not isinstance(builder_spec_schema_version, int):
            return None
        normalized["builder_spec_schema_version"] = builder_spec_schema_version
    return normalized


def load_builder_versioning(path: Path | None = None) -> dict[str, Any]:
    version_path = path or canonical_builder_version_path()
    normalized = normalize_versioning_block(
        load_json_document(version_path),
        require_builder_spec_schema_version=True,
    )
    if normalized is None:
        raise RuntimeError(f"Invalid builder version metadata: {version_path}")
    return normalized


def extract_skill_builder_versioning(spec_payload: Any) -> dict[str, Any] | None:
    if not isinstance(spec_payload, dict):
        return None
    return normalize_versioning_block(
        spec_payload.get("builder_versioning"),
        require_builder_spec_schema_version=True,
    )


def extract_profile_versioning(profile_payload: Any) -> dict[str, Any] | None:
    if not isinstance(profile_payload, dict):
        return None
    metadata = profile_payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return normalize_versioning_block(
        metadata.get("versioning"),
        require_builder_spec_schema_version=False,
    )


def compare_builder_semver(left: str, right: str) -> int:
    left_semver = parse_semver(left)
    right_semver = parse_semver(right)
    if left_semver is None or right_semver is None:
        raise ValueError("Invalid semver comparison input")
    if left_semver < right_semver:
        return -1
    if left_semver > right_semver:
        return 1
    return 0


def blocking_for_status(status: str) -> bool:
    return status in BLOCKING_STATUSES


def classify_builder_compatibility(
    *,
    current_builder: dict[str, Any],
    skill_versioning: dict[str, Any] | None,
    profile_versioning: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    status = STATUS_CURRENT

    if skill_versioning is None:
        status = STATUS_MISSING_SKILL_VERSIONING
        warnings.append("Skill builder_versioning is missing or invalid.")
    elif skill_versioning["builder_family"] != current_builder["builder_family"]:
        status = STATUS_MISSING_SKILL_VERSIONING
        warnings.append(
            "Skill builder_versioning.builder_family does not match the current builder family."
        )
    elif profile_versioning is None:
        status = STATUS_MISSING_PROFILE_VERSIONING
        warnings.append("Profile metadata.versioning is missing or invalid.")
    elif profile_versioning["builder_family"] != current_builder["builder_family"]:
        status = STATUS_MISSING_PROFILE_VERSIONING
        warnings.append(
            "Profile metadata.versioning.builder_family does not match the current builder family."
        )
    else:
        skill_semver_cmp = compare_builder_semver(
            skill_versioning["builder_semver"],
            current_builder["builder_semver"],
        )
        profile_semver_cmp = compare_builder_semver(
            profile_versioning["builder_semver"],
            current_builder["builder_semver"],
        )

        if (
            skill_versioning["compatibility_epoch"] > current_builder["compatibility_epoch"]
            or skill_versioning["builder_spec_schema_version"]
            > current_builder["builder_spec_schema_version"]
            or skill_versioning["repo_profile_schema_version"]
            > current_builder["repo_profile_schema_version"]
            or profile_versioning["compatibility_epoch"]
            > current_builder["compatibility_epoch"]
            or profile_versioning["repo_profile_schema_version"]
            > current_builder["repo_profile_schema_version"]
            or skill_semver_cmp > 0
            or profile_semver_cmp > 0
        ):
            status = STATUS_AHEAD_OF_BUILDER
        elif (
            skill_versioning["compatibility_epoch"] < current_builder["compatibility_epoch"]
            or skill_versioning["builder_spec_schema_version"]
            < current_builder["builder_spec_schema_version"]
            or skill_versioning["repo_profile_schema_version"]
            < current_builder["repo_profile_schema_version"]
        ):
            status = STATUS_STALE_SKILL
        elif (
            profile_versioning["compatibility_epoch"] < current_builder["compatibility_epoch"]
            or profile_versioning["repo_profile_schema_version"]
            < current_builder["repo_profile_schema_version"]
        ):
            status = STATUS_STALE_PROFILE
        elif skill_semver_cmp < 0 or profile_semver_cmp < 0:
            status = STATUS_SEMVER_BEHIND_COMPATIBLE

        if status in {STATUS_CURRENT, STATUS_SEMVER_BEHIND_COMPATIBLE}:
            if compare_builder_semver(
                skill_versioning["builder_semver"],
                profile_versioning["builder_semver"],
            ) != 0:
                warnings.append(
                    "Skill and active profile semver differ while remaining compatibility-safe."
                )
            if status == STATUS_SEMVER_BEHIND_COMPATIBLE:
                if skill_semver_cmp < 0:
                    warnings.append(
                        f"Skill builder_semver {skill_versioning['builder_semver']} trails current builder {current_builder['builder_semver']}."
                    )
                if profile_semver_cmp < 0:
                    warnings.append(
                        f"Active profile builder_semver {profile_versioning['builder_semver']} trails current builder {current_builder['builder_semver']}."
                    )

    return {
        "status": status,
        "blocking": blocking_for_status(status),
        "current_builder_semver": current_builder["builder_semver"],
        "current_compatibility_epoch": current_builder["compatibility_epoch"],
        "current_builder_spec_schema_version": current_builder["builder_spec_schema_version"],
        "current_repo_profile_schema_version": current_builder["repo_profile_schema_version"],
        "skill_builder_semver": None if skill_versioning is None else skill_versioning["builder_semver"],
        "skill_compatibility_epoch": None if skill_versioning is None else skill_versioning["compatibility_epoch"],
        "skill_builder_spec_schema_version": None if skill_versioning is None else skill_versioning["builder_spec_schema_version"],
        "skill_repo_profile_schema_version": None if skill_versioning is None else skill_versioning["repo_profile_schema_version"],
        "active_profile_builder_semver": None if profile_versioning is None else profile_versioning["builder_semver"],
        "active_profile_compatibility_epoch": None if profile_versioning is None else profile_versioning["compatibility_epoch"],
        "active_profile_repo_profile_schema_version": None if profile_versioning is None else profile_versioning["repo_profile_schema_version"],
        "warnings": warnings,
    }


def format_runtime_warning(compatibility: dict[str, Any]) -> str:
    warning_text = "; ".join(str(item) for item in compatibility.get("warnings") or [])
    suffix = f" {warning_text}" if warning_text else ""
    return (
        "[WARN] packet-workflow builder compatibility "
        f"status={compatibility.get('status')}.{suffix}"
    ).strip()


def retained_skill_dirs(skills_root: Path) -> list[Path]:
    result: list[Path] = []
    for path in sorted(skills_root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "builder-spec.json").is_file():
            result.append(path)
    return result


def load_skill_artifacts(skill_dir: Path) -> tuple[Any, Any]:
    spec_payload = load_json_document(skill_dir / "builder-spec.json")
    profile_payload = load_json_document(skill_dir / "profiles" / "default" / "profile.json")
    return spec_payload, profile_payload


def evaluate_skill_dir(
    skill_dir: Path,
    *,
    current_builder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    builder_version = current_builder or load_builder_versioning()
    spec_payload, profile_payload = load_skill_artifacts(skill_dir)
    report = classify_builder_compatibility(
        current_builder=builder_version,
        skill_versioning=extract_skill_builder_versioning(spec_payload),
        profile_versioning=extract_profile_versioning(profile_payload),
    )
    report.update(
        {
            "skill_name": skill_dir.name,
            "builder_spec_path": (skill_dir / "builder-spec.json").as_posix(),
            "profile_path": (skill_dir / "profiles" / "default" / "profile.json").as_posix(),
        }
    )
    return report
