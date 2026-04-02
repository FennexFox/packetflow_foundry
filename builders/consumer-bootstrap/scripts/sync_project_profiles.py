#!/usr/bin/env python3
"""Scaffold and safe-sync project-local profiles for consumer repos."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

from project_profile_support import (
    PROJECT_PROFILE_RELATIVE,
    apply_project_local_owned_fields,
    build_default_project_local_profile,
    build_skill_project_local_profile,
    project_local_profile_relative,
    render_json_document,
)


PACKET_WORKFLOW_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "packet-workflow" / "scripts"
if str(PACKET_WORKFLOW_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PACKET_WORKFLOW_SCRIPT_DIR))

from packet_workflow_versioning import (  # type: ignore  # noqa: E402
    STATUS_AHEAD_OF_BUILDER,
    STATUS_CURRENT,
    STATUS_MISSING_PROFILE_VERSIONING,
    STATUS_SEMVER_BEHIND_COMPATIBLE,
    STATUS_STALE_PROFILE,
    classify_builder_compatibility,
    compare_builder_semver,
    extract_profile_versioning,
    extract_skill_builder_versioning,
    load_builder_versioning,
)


REPORT_KIND = "packetflow-foundry-project-profile-sync-report"
DEFAULT_REPORT_RELATIVE = Path(".codex/tmp/project-profile-sync/report.json")
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_UNCHANGED = "unchanged"
ACTION_IGNORED = "ignored"
ACTION_MANUAL = "manual_migration_required"
WRAPPER_RETAINED_SKILL_RE = re.compile(
    r"`(?P<relative>[^`]*builders/packet-workflow/retained-skills/(?P<skill>[a-z0-9][a-z0-9-]*)/)`"
)


class WrapperInfo(TypedDict):
    skill_name: str
    wrapper_dir: str
    retained_skill_dir: str
    retained_profile_path: str
    builder_spec_path: str


class GapInfo(TypedDict):
    kind: str
    path: str


class ProfileResult(TypedDict):
    skill_name: str
    profile_path: str
    source_profile_path: str | None
    action: str
    blocking: bool
    compatibility_status: str | None
    reason: str | None
    unresolved_gaps: list[GapInfo]


def new_profile_result(
    *,
    skill_name: str,
    profile_path: str,
    source_profile_path: str | None,
) -> ProfileResult:
    return {
        "skill_name": skill_name,
        "profile_path": profile_path,
        "source_profile_path": source_profile_path,
        "action": ACTION_UNCHANGED,
        "blocking": False,
        "compatibility_status": None,
        "reason": None,
        "unresolved_gaps": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        required=True,
        help="Consumer repository root to inspect and sync.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help=(
            "Optional skill name to sync. Repeat for multiple skills. "
            "When set, the default profile is always included."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute actions and write only the JSON report.",
    )
    parser.add_argument(
        "--report",
        default=None,
        help=(
            "Optional JSON report output path. Defaults to "
            "`.codex/tmp/project-profile-sync/report.json` under the repo root."
        ),
    )
    return parser.parse_args()


def resolve_repo_root(value: str) -> Path:
    repo_root = Path(value).resolve()
    if not repo_root.exists():
        raise RuntimeError(f"Missing repo root: {repo_root.as_posix()}")
    if not repo_root.is_dir():
        raise RuntimeError(f"Repo root is not a directory: {repo_root.as_posix()}")
    return repo_root


def resolve_report_path(repo_root: Path, report_path: str | None) -> Path:
    if not report_path:
        return (repo_root / DEFAULT_REPORT_RELATIVE).resolve()
    candidate = Path(report_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON document must be an object: {path.as_posix()}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_document(payload) + "\n", encoding="utf-8", newline="\n")


def discover_packet_workflow_wrappers(repo_root: Path) -> dict[str, WrapperInfo]:
    wrappers_root = repo_root / ".agents" / "skills"
    if not wrappers_root.is_dir():
        return {}

    discovered: dict[str, WrapperInfo] = {}
    for child in sorted(wrappers_root.iterdir(), key=lambda entry: entry.name):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        wrapper = resolve_packet_workflow_wrapper(
            child,
            skill_md,
            repo_root=repo_root,
        )
        if wrapper is None:
            continue
        discovered[wrapper["skill_name"]] = wrapper
    return discovered


def resolve_packet_workflow_wrapper(
    wrapper_dir: Path,
    skill_md_path: Path,
    *,
    repo_root: Path,
) -> WrapperInfo | None:
    text = skill_md_path.read_text(encoding="utf-8-sig")
    resolved_repo_root = repo_root.resolve()
    for match in WRAPPER_RETAINED_SKILL_RE.finditer(text):
        retained_relative = match.group("relative")
        skill_name = match.group("skill")
        retained_relative_path = Path(retained_relative)
        if retained_relative_path.is_absolute():
            continue
        retained_skill_dir = (wrapper_dir / retained_relative).resolve()
        try:
            retained_skill_dir.relative_to(resolved_repo_root)
        except ValueError:
            continue
        retained_profile_path = retained_skill_dir / "profiles" / "default" / "profile.json"
        builder_spec_path = retained_skill_dir / "builder-spec.json"
        if skill_name != wrapper_dir.name:
            continue
        if not retained_skill_dir.is_dir():
            continue
        if not retained_profile_path.is_file() or not builder_spec_path.is_file():
            continue
        return {
            "skill_name": skill_name,
            "wrapper_dir": wrapper_dir.resolve().as_posix(),
            "retained_skill_dir": retained_skill_dir.as_posix(),
            "retained_profile_path": retained_profile_path.as_posix(),
            "builder_spec_path": builder_spec_path.as_posix(),
        }
    return None


def normalize_requested_skills(skills: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in skills:
        text = str(item or "").strip()
        if text == "default":
            continue
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def safe_additive_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, source_value in source.items():
        if key not in target:
            target[key] = copy.deepcopy(source_value)
            continue
        target_value = target[key]
        if isinstance(target_value, dict) and isinstance(source_value, dict):
            safe_additive_merge(target_value, source_value)


def unsupported_profile_shape_reason(payload: dict[str, Any]) -> str | None:
    for key in ("repo_match", "bindings", "packet_defaults", "lint_rules", "metadata"):
        value = payload.get(key)
        if value is not None and not isinstance(value, dict):
            return f"Unsupported profile shape at `{key}`."
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, list):
        return "Unsupported profile shape at `notes`."
    packet_defaults = payload.get("packet_defaults")
    if isinstance(packet_defaults, dict):
        for key in ("review_docs", "source_path_globs"):
            value = packet_defaults.get(key)
            if value is not None and not isinstance(value, dict):
                return f"Unsupported profile shape at `packet_defaults.{key}`."
    return None


def classify_profile_versioning_only(
    *,
    current_builder: dict[str, Any],
    profile_versioning: dict[str, Any] | None,
    allow_missing_versioning: bool = False,
) -> tuple[str | None, bool]:
    if profile_versioning is None:
        return STATUS_MISSING_PROFILE_VERSIONING, not allow_missing_versioning
    if profile_versioning["builder_family"] != current_builder["builder_family"]:
        return "profile-family-mismatch", True
    if (
        profile_versioning["compatibility_epoch"] > current_builder["compatibility_epoch"]
        or profile_versioning["repo_profile_schema_version"]
        > current_builder["repo_profile_schema_version"]
    ):
        return STATUS_AHEAD_OF_BUILDER, True
    if (
        profile_versioning["compatibility_epoch"] < current_builder["compatibility_epoch"]
        or profile_versioning["repo_profile_schema_version"]
        < current_builder["repo_profile_schema_version"]
    ):
        return STATUS_STALE_PROFILE, True
    semver_cmp = compare_builder_semver(
        profile_versioning["builder_semver"],
        current_builder["builder_semver"],
    )
    if semver_cmp > 0:
        return STATUS_AHEAD_OF_BUILDER, True
    if semver_cmp < 0:
        return STATUS_SEMVER_BEHIND_COMPATIBLE, False
    return STATUS_CURRENT, False


def load_skill_builder_versioning(retained_skill_dir: Path) -> dict[str, Any] | None:
    spec_path = retained_skill_dir / "builder-spec.json"
    return extract_skill_builder_versioning(load_json_object(spec_path))


def profile_versioning_is_missing(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata")
    if metadata is None:
        return True
    if not isinstance(metadata, dict):
        return False
    return "versioning" not in metadata


def classify_retained_skill_source(
    *,
    current_builder: dict[str, Any],
    skill_versioning: dict[str, Any] | None,
    profile_versioning: dict[str, Any] | None,
) -> tuple[str | None, bool]:
    compatibility = classify_builder_compatibility(
        current_builder=current_builder,
        skill_versioning=skill_versioning,
        profile_versioning=profile_versioning,
    )
    return str(compatibility["status"]), bool(compatibility["blocking"])


def collect_unresolved_gaps(
    payload: dict[str, Any],
    *,
    reference_payload: dict[str, Any] | None = None,
) -> list[GapInfo]:
    gaps: list[GapInfo] = []

    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        gaps.append({"kind": "missing_section", "path": "bindings"})
    else:
        for key in sorted(bindings):
            value = bindings.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                gaps.append({"kind": "null_binding", "path": f"bindings.{key}"})

    packet_defaults = payload.get("packet_defaults")
    if not isinstance(packet_defaults, dict):
        gaps.append({"kind": "missing_section", "path": "packet_defaults"})
    else:
        review_docs = packet_defaults.get("review_docs")
        if not isinstance(review_docs, dict) or not review_docs:
            gaps.append({"kind": "empty_review_docs", "path": "packet_defaults.review_docs"})
        else:
            for key in sorted(review_docs):
                docs = review_docs.get(key)
                if not isinstance(docs, list) or not docs:
                    gaps.append(
                        {
                            "kind": "empty_review_docs_group",
                            "path": f"packet_defaults.review_docs.{key}",
                        }
                    )

        source_globs = packet_defaults.get("source_path_globs")
        if not isinstance(source_globs, dict) or not source_globs:
            gaps.append(
                {"kind": "empty_source_path_globs", "path": "packet_defaults.source_path_globs"}
            )
        else:
            for key in sorted(source_globs):
                globs = source_globs.get(key)
                if not isinstance(globs, list) or not globs:
                    gaps.append(
                        {
                            "kind": "empty_source_path_glob_group",
                            "path": f"packet_defaults.source_path_globs.{key}",
                        }
                    )

    if reference_payload is not None:
        for path in (
            "bindings",
            "packet_defaults.review_docs",
            "packet_defaults.source_path_globs",
            "extra",
        ):
            if values_equal_at_path(payload, reference_payload, path):
                gaps.append({"kind": "retained_placeholder_section", "path": path})

    return gaps


def values_equal_at_path(left: dict[str, Any], right: dict[str, Any], dotted_path: str) -> bool:
    left_value = value_at_path(left, dotted_path)
    right_value = value_at_path(right, dotted_path)
    return left_value == right_value and right_value not in (None, {}, [])


def value_at_path(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def sync_default_profile(
    repo_root: Path,
    *,
    current_builder: dict[str, Any],
    dry_run: bool,
) -> ProfileResult:
    target_path = repo_root / PROJECT_PROFILE_RELATIVE
    default_payload = build_default_project_local_profile(
        repo_root,
        current_builder=current_builder,
    )

    result = new_profile_result(
        skill_name="default",
        profile_path=target_path.as_posix(),
        source_profile_path=PROJECT_PROFILE_RELATIVE.as_posix(),
    )

    if not target_path.exists():
        result["action"] = ACTION_CREATED
        result["blocking"] = False
        result["compatibility_status"] = STATUS_CURRENT
        result["unresolved_gaps"] = collect_unresolved_gaps(default_payload)
        if not dry_run:
            write_json(target_path, default_payload)
        return result

    try:
        payload = load_json_object(target_path)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = None
        result["reason"] = str(exc)
        result["unresolved_gaps"] = []
        return result

    shape_reason = unsupported_profile_shape_reason(payload)
    if shape_reason is not None:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = None
        result["reason"] = shape_reason
        result["unresolved_gaps"] = []
        return result

    profile_versioning = extract_profile_versioning(payload)
    compatibility_status, blocking = classify_profile_versioning_only(
        current_builder=current_builder,
        profile_versioning=profile_versioning,
        allow_missing_versioning=profile_versioning is None
        and profile_versioning_is_missing(payload),
    )
    result["compatibility_status"] = compatibility_status
    if blocking:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["reason"] = "Existing default profile requires manual migration."
        result["unresolved_gaps"] = []
        return result

    updated_payload = copy.deepcopy(payload)
    safe_additive_merge(updated_payload, default_payload)
    apply_project_local_owned_fields(
        updated_payload,
        skill_name="default",
        profile_relative=PROJECT_PROFILE_RELATIVE,
        current_builder=current_builder,
    )
    changed = updated_payload != payload
    result["action"] = ACTION_UPDATED if changed else ACTION_UNCHANGED
    result["blocking"] = False
    result["unresolved_gaps"] = collect_unresolved_gaps(updated_payload)
    if changed and not dry_run:
        write_json(target_path, updated_payload)
    return result


def sync_skill_profile(
    repo_root: Path,
    *,
    wrapper: WrapperInfo,
    current_builder: dict[str, Any],
    dry_run: bool,
) -> ProfileResult:
    skill_name = wrapper["skill_name"]
    retained_skill_dir = Path(wrapper["retained_skill_dir"])
    retained_profile_path = Path(wrapper["retained_profile_path"])
    target_relative = project_local_profile_relative(skill_name)
    target_path = repo_root / target_relative

    result = new_profile_result(
        skill_name=skill_name,
        profile_path=target_path.as_posix(),
        source_profile_path=retained_profile_path.as_posix(),
    )

    try:
        retained_profile = load_json_object(retained_profile_path)
        skill_versioning = load_skill_builder_versioning(retained_skill_dir)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = None
        result["reason"] = str(exc)
        result["unresolved_gaps"] = []
        return result

    source_status, source_blocking = classify_retained_skill_source(
        current_builder=current_builder,
        skill_versioning=skill_versioning,
        profile_versioning=extract_profile_versioning(retained_profile),
    )
    if source_blocking:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = source_status
        result["reason"] = "Retained skill source requires manual migration before sync."
        result["unresolved_gaps"] = []
        return result

    scaffold_payload = build_skill_project_local_profile(
        repo_root,
        skill_name=skill_name,
        retained_profile=retained_profile,
        current_builder=current_builder,
    )

    if not target_path.exists():
        result["action"] = ACTION_CREATED
        result["blocking"] = False
        result["compatibility_status"] = source_status
        result["unresolved_gaps"] = collect_unresolved_gaps(
            scaffold_payload,
            reference_payload=retained_profile,
        )
        if not dry_run:
            write_json(target_path, scaffold_payload)
        return result

    try:
        payload = load_json_object(target_path)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = None
        result["reason"] = str(exc)
        result["unresolved_gaps"] = []
        return result

    shape_reason = unsupported_profile_shape_reason(payload)
    if shape_reason is not None:
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["compatibility_status"] = None
        result["reason"] = shape_reason
        result["unresolved_gaps"] = []
        return result

    compatibility = classify_builder_compatibility(
        current_builder=current_builder,
        skill_versioning=skill_versioning,
        profile_versioning=extract_profile_versioning(payload),
    )
    result["compatibility_status"] = str(compatibility["status"])
    if bool(compatibility["blocking"]):
        result["action"] = ACTION_MANUAL
        result["blocking"] = True
        result["reason"] = "Existing skill profile requires manual migration."
        result["unresolved_gaps"] = []
        return result

    updated_payload = copy.deepcopy(payload)
    safe_additive_merge(updated_payload, scaffold_payload)
    apply_project_local_owned_fields(
        updated_payload,
        skill_name=skill_name,
        profile_relative=target_relative,
        current_builder=current_builder,
    )
    changed = updated_payload != payload
    result["action"] = ACTION_UPDATED if changed else ACTION_UNCHANGED
    result["blocking"] = False
    result["unresolved_gaps"] = collect_unresolved_gaps(
        updated_payload,
        reference_payload=retained_profile,
    )
    if changed and not dry_run:
        write_json(target_path, updated_payload)
    return result


def build_report(
    repo_root: Path,
    *,
    results: list[ProfileResult],
    dry_run: bool,
) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for item in results:
        action = item["action"]
        summary[action] = summary.get(action, 0) + 1
    return {
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "dry_run": dry_run,
        "blocking_count": sum(1 for item in results if item.get("blocking")),
        "summary": summary,
        "profiles": results,
    }


def main() -> int:
    args = parse_args()
    try:
        repo_root = resolve_repo_root(cast(str, args.repo_root))
        report_path = resolve_report_path(repo_root, cast(str | None, args.report))
        current_builder = load_builder_versioning()
        discovered = discover_packet_workflow_wrappers(repo_root)
        requested_skills = normalize_requested_skills(cast(list[str], args.skill))
        results: list[ProfileResult] = []

        results.append(
            sync_default_profile(
                repo_root,
                current_builder=current_builder,
                dry_run=cast(bool, args.dry_run),
            )
        )

        if requested_skills:
            skill_names = requested_skills
        else:
            skill_names = sorted(discovered)

        for skill_name in skill_names:
            wrapper = discovered.get(skill_name)
            if wrapper is None:
                ignored_result = new_profile_result(
                    skill_name=skill_name,
                    profile_path=(
                        repo_root / project_local_profile_relative(skill_name)
                    ).as_posix(),
                    source_profile_path=None,
                )
                ignored_result["action"] = ACTION_IGNORED
                ignored_result["reason"] = (
                    "No packet-workflow thin wrapper was discovered for this skill."
                )
                results.append(ignored_result)
                continue
            results.append(
                sync_skill_profile(
                    repo_root,
                    wrapper=wrapper,
                    current_builder=current_builder,
                    dry_run=cast(bool, args.dry_run),
                )
            )
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    report = build_report(repo_root, results=results, dry_run=cast(bool, args.dry_run))
    write_json(report_path, report)

    has_blocking = any(item.get("blocking") for item in results)
    summary_prefix = "[ERROR]" if has_blocking else "[OK]"
    summary_text = (
        "Synced project-local profiles with blocking items"
        if has_blocking
        else "Synced project-local profiles"
    )
    print(f"{summary_prefix} {summary_text} at {repo_root.as_posix()}")
    print(f" - report: {report_path.as_posix()}")
    for item in results:
        detail = item["profile_path"]
        if item.get("reason"):
            detail = f"{detail} ({item['reason']})"
        print(f" - {item['action']}: {detail}")

    if has_blocking:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
