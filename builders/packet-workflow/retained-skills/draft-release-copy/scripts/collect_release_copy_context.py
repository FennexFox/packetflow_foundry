#!/usr/bin/env python3
"""Collect release-copy context for packet-based release preparation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
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


GROUP_SAMPLE_LIMIT = 16


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


def resolve_profile_path(profile_path: str | None, repo_root: Path) -> Path:
    if not profile_path:
        return default_repo_profile_path(repo_root)

    candidate = Path(profile_path)
    if candidate.is_absolute():
        resolved_candidates = [candidate.resolve()]
    else:
        resolved_candidates = [
            (repo_root / candidate).resolve(),
            (skill_root() / candidate).resolve(),
        ]
    for resolved in resolved_candidates:
        if resolved.is_file():
            return resolved
    searched = ", ".join(path.as_posix() for path in resolved_candidates)
    raise RuntimeError(f"missing repo profile: {searched}")


def load_repo_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError("repo profile must be a JSON object")
    return payload


def build_builder_compatibility(repo_profile: dict[str, Any]) -> dict[str, Any]:
    return classify_builder_compatibility(
        current_builder=load_builder_versioning(),
        skill_versioning=extract_skill_builder_versioning(
            load_json_document(skill_root() / "builder-spec.json")
        ),
        profile_versioning=extract_profile_versioning(repo_profile),
    )


def run_command(args: list[str], cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return result.stdout


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_text_if_exists(path: Path) -> str | None:
    if not path.is_file():
        return None
    return read_text(path)


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_fingerprint(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def merge_optional_dicts(*sources: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if isinstance(value, str):
                if value.strip():
                    merged[key] = value.strip()
                continue
            if value is not None:
                merged[key] = value
    return merged or None


def normalize_repo_relative_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def resolve_repo_binding(repo_root: Path, raw_value: str | None, label: str) -> tuple[str, Path]:
    text = normalize_repo_relative_path(str(raw_value or ""))
    if not text:
        raise RuntimeError(f"missing required repo profile binding: {label}")
    candidate = Path(text)
    if candidate.is_absolute():
        raise RuntimeError(f"repo profile binding `{label}` must be repo-relative, not absolute")
    resolved = (repo_root / candidate).resolve()
    repo_root_resolved = repo_root.resolve()
    common = Path(os.path.commonpath([str(repo_root_resolved), str(resolved)]))
    if common != repo_root_resolved:
        raise RuntimeError(f"repo profile binding `{label}` must stay inside the repository root")
    return text, resolved


def require_repo_binding_file(path: Path, repo_relative: str, label: str) -> None:
    if path.is_file():
        return
    raise RuntimeError(f"repo profile binding `{label}` points to a missing file: {repo_relative}")


def validate_local_helper_path(repo_root: Path, helper_path: str) -> tuple[str, Path]:
    candidate = Path(helper_path)
    if candidate.is_absolute():
        raise RuntimeError("local release helper path must be repo-relative, not absolute")
    resolved = (repo_root / candidate).resolve()
    repo_root_resolved = repo_root.resolve()
    common = Path(os.path.commonpath([str(repo_root_resolved), str(resolved)]))
    if common != repo_root_resolved:
        raise RuntimeError("local release helper path must stay inside the repository root")
    return normalize_repo_relative_path(str(candidate)), resolved


def infer_repo_slug(repo_root: Path) -> str | None:
    try:
        payload = json.loads(run_command(["gh", "repo", "view", "--json", "nameWithOwner"], cwd=repo_root))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        slug = str(payload.get("nameWithOwner") or "").strip()
        if slug:
            return slug

    try:
        remote = run_command(["git", "config", "--get", "remote.origin.url"], cwd=repo_root).strip()
    except RuntimeError:
        return None
    match = re.search(r"github\.com[:/](?P<slug>[^/]+/[^/.]+)(?:\.git)?$", remote)
    return match.group("slug") if match else None


def gh_repo_args(repo_slug: str | None) -> list[str]:
    return ["--repo", repo_slug] if repo_slug else []


def normalized_release_version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("v") else f"v{text}"


def git_branch(repo_root: Path) -> str:
    return run_command(["git", "branch", "--show-current"], cwd=repo_root, check=False).strip()


def git_head_commit(repo_root: Path) -> str:
    return run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root).strip()


def latest_reachable_tag(repo_root: Path) -> str | None:
    output = run_command(
        ["git", "tag", "--merged", "HEAD", "--list", "v*", "--sort=-creatordate"],
        cwd=repo_root,
        check=False,
    )
    tags = [line.strip() for line in output.splitlines() if line.strip()]
    return tags[0] if tags else None


def git_commit_subjects(repo_root: Path, revision_range: str) -> list[str]:
    output = run_command(["git", "log", "--format=%s", revision_range], cwd=repo_root, check=False)
    return [line.strip() for line in output.splitlines() if line.strip()]


def git_commit_count(repo_root: Path, revision_range: str) -> int:
    output = run_command(["git", "rev-list", "--count", revision_range], cwd=repo_root, check=False).strip()
    return int(output) if output.isdigit() else 0


def git_changed_files(repo_root: Path, revision_range: str) -> list[str]:
    output = run_command(["git", "diff", "--name-only", revision_range], cwd=repo_root, check=False)
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def parse_numstat_int(raw: str) -> int:
    raw = raw.strip()
    if raw == "-" or not raw:
        return 0
    return int(raw) if raw.isdigit() else 0


def git_changed_file_stats(repo_root: Path, revision_range: str) -> dict[str, dict[str, int]]:
    output = run_command(["git", "diff", "--numstat", revision_range], cwd=repo_root, check=False)
    stats: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        insertions = parse_numstat_int(parts[0])
        deletions = parse_numstat_int(parts[1])
        path = parts[-1].strip().replace("\\", "/")
        if not path:
            continue
        stats[path] = {
            "insertions": insertions,
            "deletions": deletions,
            "churn": insertions + deletions,
        }
    return stats


def git_diff_stat(repo_root: Path, revision_range: str) -> str | None:
    output = run_command(["git", "diff", "--stat", revision_range], cwd=repo_root, check=False).strip()
    return output or None


def classify_changed_files(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "runtime": [],
        "automation": [],
        "docs": [],
        "tests": [],
        "config": [],
        "other": [],
    }
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        lower = path.lower()
        if (
            "/tests/" in lower
            or lower.endswith("_test.py")
            or lower.endswith(".tests.cs")
            or lower.endswith(".spec.ts")
            or lower.startswith(".github/scripts/tests/")
        ):
            groups["tests"].append(path)
        elif (
            lower.startswith(".github/workflows/")
            or lower.startswith(".github/scripts/")
            or lower.startswith(".github/issue_template/")
            or lower.startswith(".github/instructions/")
        ):
            groups["automation"].append(path)
        elif lower.endswith(".md") or lower.startswith("docs/"):
            groups["docs"].append(path)
        elif lower.endswith((".yml", ".yaml", ".toml", ".json", ".csproj", ".props", ".targets", ".xml")):
            groups["config"].append(path)
        elif lower.endswith((".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java")):
            groups["runtime"].append(path)
        else:
            groups["other"].append(path)
    return groups


def sample_parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def select_representative_files(paths: list[str], limit: int = GROUP_SAMPLE_LIMIT) -> list[str]:
    ordered_paths: list[str] = []
    for path in paths:
        if path not in ordered_paths:
            ordered_paths.append(path)
    if len(ordered_paths) <= limit:
        return ordered_paths

    buckets: dict[str, list[str]] = {}
    bucket_order: list[str] = []
    for path in ordered_paths:
        parent = sample_parent(path)
        if parent not in buckets:
            buckets[parent] = []
            bucket_order.append(parent)
        buckets[parent].append(path)

    selected: list[str] = []
    while len(selected) < limit:
        progressed = False
        for parent in bucket_order:
            bucket = buckets[parent]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    original_index = {path: index for index, path in enumerate(ordered_paths)}
    return sorted(selected, key=original_index.__getitem__)


def summarize_groups(groups: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for name, paths in groups.items():
        sample_files = select_representative_files(paths)
        summary[name] = {
            "count": len(paths),
            "sample_files": sample_files,
            "omitted_file_count": max(len(paths) - len(sample_files), 0),
            "sample_strategy": "directory_round_robin",
        }
    return summary


def parse_markdown_sections(markdown_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


def parse_readme_settings_table(section_body: str) -> dict[str, dict[str, str]]:
    defaults: dict[str, dict[str, str]] = {}
    lines = section_body.splitlines()
    in_table = False
    for line in lines:
        if line.strip().startswith("| Setting | Default | Purpose |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            break
        if set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if len(parts) != 3:
            continue
        setting_name = parts[0].strip("`")
        defaults[setting_name] = {
            "default": parts[1].strip("`"),
            "purpose": parts[2],
        }
    return defaults


def first_heading_block(markdown_text: str, heading: str) -> str | None:
    lines = markdown_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).replace("\r\n", "\n").strip()


def parse_publish_configuration(path: Path) -> dict[str, Any]:
    return parse_publish_configuration_text(read_text(path), str(path))


def parse_publish_configuration_text(text: str, source_path: str) -> dict[str, Any]:
    root = ET.fromstring(text)

    def value_of(tag_name: str) -> str:
        element = root.find(tag_name)
        if element is None:
            return ""
        return element.attrib.get("Value", "").strip()

    return {
        "path": source_path,
        "mod_id": value_of("ModId"),
        "display_name": value_of("DisplayName"),
        "short_description": value_of("ShortDescription"),
        "long_description": element_text(root.find("LongDescription")),
        "thumbnail": value_of("Thumbnail"),
        "tags": [tag.attrib.get("Value", "").strip() for tag in root.findall("Tag") if tag.attrib.get("Value")],
        "forum_link": value_of("ForumLink"),
        "mod_version": value_of("ModVersion"),
        "game_version": value_of("GameVersion"),
        "change_log": element_text(root.find("ChangeLog")),
        "external_links": [
            {
                "type": link.attrib.get("Type", "").strip(),
                "url": link.attrib.get("Url", "").strip(),
            }
            for link in root.findall("ExternalLink")
        ],
        "access_level": value_of("AccessLevel"),
    }


def publish_configuration_at_tag(repo_root: Path, tag: str, repo_relative_path: str) -> dict[str, Any] | None:
    try:
        text = run_command(["git", "show", f"{tag}:{repo_relative_path}"], cwd=repo_root, check=False)
    except RuntimeError:
        return None
    if not text.strip():
        return None
    try:
        return parse_publish_configuration_text(text, f"{tag}:{repo_relative_path}")
    except ET.ParseError:
        return None


def parse_release_checklist(text: str) -> dict[str, Any]:
    labels_match = re.search(r"^labels:\s*\[(?P<body>.+?)\]\s*$", text, re.MULTILINE)
    labels: list[str] = []
    if labels_match:
        labels = [item.strip().strip("\"'") for item in labels_match.group("body").split(",") if item.strip()]

    current_id = None
    fields: list[dict[str, str]] = []
    checkbox_labels: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            current_id = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("label:"):
            label = stripped.split(":", 1)[1].strip().strip("\"'")
            if current_id == "checks":
                continue
            if current_id:
                fields.append({"id": current_id, "label": label})
            continue
        if stripped.startswith("- label:"):
            checkbox_labels.append(stripped.split(":", 1)[1].strip().strip("\"'"))

    title_match = re.search(r"^title:\s*\"(?P<title>.+?)\"\s*$", text, re.MULTILINE)
    return {
        "title_prefix": title_match.group("title") if title_match else "[Release] ",
        "labels": labels,
        "fields": fields,
        "checkbox_labels": checkbox_labels,
    }


def parse_release_issue_evidence(section_text: str) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()
        if ":" not in content:
            continue
        key, value = [part.strip() for part in content.split(":", 1)]
        normalized_key = re.sub(r"\s+", " ", key).strip().lower()
        if normalized_key == "software track status":
            evidence["software_track_status"] = value
        elif normalized_key == "current software anchor evidence entry":
            evidence["current_software_anchor_evidence"] = value
        elif normalized_key.startswith("comparable software evidence"):
            evidence["comparable_evidence"] = value
        elif normalized_key.startswith("software anchor comparison summary"):
            evidence["anchor_comparison"] = value
        elif normalized_key == "software release pr validation note":
            evidence["release_pr_validation_note"] = value
        elif normalized_key in {
            "performance telemetry validation artifact",
            "telemetry validation artifact",
            "performance telemetry issue or validation artifact",
        }:
            evidence["telemetry_validation_artifact"] = value
        elif normalized_key in {
            "performance telemetry validation summary",
            "telemetry validation summary",
        }:
            evidence["telemetry_validation_summary"] = value
    return evidence


def parse_existing_release_issue(issue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(issue, dict):
        return None
    body = str(issue.get("body") or "")
    sections = parse_markdown_sections(body)
    evidence_section = sections.get("Release-gate evidence / validation", "")
    checklist_section = sections.get("Checklist", "")
    checked_labels = [
        line[6:].strip()
        for line in checklist_section.splitlines()
        if line.strip().startswith("- [x] ")
    ]
    return {
        "number": issue.get("number"),
        "title": str(issue.get("title") or "").strip(),
        "url": str(issue.get("url") or "").strip(),
        "state": str(issue.get("state") or "").strip(),
        "body": body,
        "evidence": parse_release_issue_evidence(evidence_section),
        "checked_labels": checked_labels,
    }


def existing_issue_snapshot(existing_issue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(existing_issue, dict):
        return None
    body = str(existing_issue.get("body") or "")
    snapshot = {
        "number": existing_issue.get("number"),
        "title": str(existing_issue.get("title") or "").strip(),
        "state": str(existing_issue.get("state") or "").strip(),
        "url": str(existing_issue.get("url") or "").strip(),
        "body_fingerprint": json_fingerprint(body),
    }
    return snapshot


def freshness_tuple(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "head_commit": str(context.get("head_commit") or "").strip(),
        "base_tag": str(context.get("base_tag") or "").strip(),
        "target_version": str(context.get("target_version") or "").strip(),
        "evidence_fingerprint": json_fingerprint(context.get("evidence") or {}),
        "existing_release_issue": existing_issue_snapshot(context.get("existing_release_issue")),
    }


def release_issue_by_number(repo_root: Path, repo_slug: str | None, number: int) -> dict[str, Any] | None:
    args = [
        "gh",
        "issue",
        "view",
        str(number),
        "--json",
        "number,title,body,url,state",
        *gh_repo_args(repo_slug),
    ]
    try:
        payload = json.loads(run_command(args, cwd=repo_root))
    except Exception:
        return None
    return parse_existing_release_issue(payload)


def find_existing_release_issue(repo_root: Path, repo_slug: str | None, target_version: str) -> dict[str, Any] | None:
    release_title = f"[Release] {normalized_release_version(target_version)}"
    args = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--label",
        "release",
        "--json",
        "number,title,body,url,state",
        *gh_repo_args(repo_slug),
    ]
    try:
        payload = json.loads(run_command(args, cwd=repo_root, check=False) or "[]")
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    matches = [
        issue
        for issue in payload
        if str(issue.get("title") or "").strip() == release_title
    ]
    if not matches:
        return None
    latest = max(matches, key=lambda issue: int(issue.get("number") or 0))
    return parse_existing_release_issue(latest)


def parse_release_workflow(text: str) -> dict[str, Any]:
    tag_patterns: list[str] = []
    in_tags = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "tags:":
            in_tags = True
            continue
        if in_tags:
            if stripped.startswith("- "):
                tag_patterns.append(stripped[2:].strip().strip("\"'"))
                continue
            if stripped and not stripped.startswith("#"):
                in_tags = False
    return {
        "tag_patterns": tag_patterns,
        "generate_release_notes": "generate_release_notes: true" in text.lower(),
    }


def parse_setting_defaults(text: str) -> dict[str, str]:
    defaults: dict[str, str] = {}
    match = re.search(r"public override void SetDefaults\(\)\s*\{(?P<body>.*?)^\s*\}", text, re.DOTALL | re.MULTILINE)
    body = match.group("body") if match else ""
    for line in body.splitlines():
        assignment = re.match(r"^\s*(?P<name>[A-Za-z0-9_]+)\s*=\s*(?P<value>[^;]+);", line)
        if not assignment:
            continue
        defaults[assignment.group("name")] = normalize_literal(assignment.group("value"))
    return defaults


def normalize_literal(value: str) -> str:
    cleaned = value.strip()
    lowered = cleaned.lower()
    if lowered in {"true", "false"}:
        return lowered
    if lowered.endswith("f"):
        lowered = lowered[:-1]
    try:
        if "." in lowered:
            number = float(lowered)
            return f"{number:.1f}" if number.is_integer() else str(number)
        return str(int(lowered))
    except ValueError:
        return cleaned


def parse_local_helper(text: str, repo_relative_path: str) -> dict[str, Any]:
    required_parameters = re.findall(
        r"\[Parameter\(Mandatory\)\]\s*\[string\]\$(?P<name>[A-Za-z0-9_]+)",
        text,
        re.MULTILINE,
    )
    optional_string_parameters = re.findall(
        r"^\s*\[string\]\$(?P<name>[A-Za-z0-9_]+)",
        text,
        re.MULTILINE,
    )
    switch_parameters = re.findall(
        r"^\s*\[switch\]\$(?P<name>[A-Za-z0-9_]+)",
        text,
        re.MULTILINE,
    )
    required_env_vars = sorted(
        {
            *re.findall(r'Get-RequiredEnvironmentValue -Name "(?P<name>[^"]+)"', text),
            *re.findall(r'Assert-PathValue -Name "(?P<name>[^"]+)"', text),
        }
    )
    preflight_notes: list[str] = []
    if "Working tree is not clean" in text:
        preflight_notes.append("Requires a clean working tree unless SkipGitChecks is used.")
    if "Local tag $tag already exists." in text or "Remote tag $tag already exists." in text:
        preflight_notes.append("Refuses to reuse an existing release tag unless SkipGitTag is used.")
    if "PublishConfiguration.xml has ModVersion" in text:
        preflight_notes.append("Requires PublishConfiguration.xml ModVersion to match the requested release version.")

    return {
        "repo_relative_path": repo_relative_path,
        "script_kind": "powershell" if repo_relative_path.lower().endswith(".ps1") else "unknown",
        "required_parameters": sorted(set(required_parameters)),
        "optional_parameters": sorted(set(optional_string_parameters + switch_parameters)),
        "required_env_vars": required_env_vars,
        "preflight_notes": preflight_notes,
    }


def project_title_default(*texts: str) -> str | None:
    for text in texts:
        match = re.search(r"\[(?P<title>[^\]]+Tracker)\]\(", text)
        if match:
            return match.group("title")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect release-copy context for packet-based release preparation."
    )
    parser.add_argument("--repo-root", required=True, help="Repository root")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--base-tag", default=None, help="Optional base release tag such as v0.2.1")
    parser.add_argument("--target-version", default=None, help="Optional release version override")
    parser.add_argument("--evidence-file", default=None, help="Optional evidence JSON file")
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Optional path to the active repo profile JSON. Relative paths resolve from the "
            "repo root first, then the skill root. When omitted, the collector prefers "
            "`.codex/project/profiles/<skill-name>/profile.json`, then "
            "`.codex/project/profiles/default/profile.json`, then the retained neutral scaffold."
        ),
    )
    parser.add_argument(
        "--release-issue-number",
        type=int,
        default=None,
        help="Optional existing release checklist issue number to read evidence from",
    )
    parser.add_argument(
        "--local-release-helper",
        default="scripts/release.ps1",
        help="Repo-relative local release helper path",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        profile_path = resolve_profile_path(args.profile, repo_root)
        repo_profile = load_repo_profile(profile_path)
        bindings = repo_profile.get("bindings") if isinstance(repo_profile.get("bindings"), dict) else {}
        extra_root = repo_profile.get("extra") if isinstance(repo_profile.get("extra"), dict) else {}
        release_extra = extra_root.get("release_copy") if isinstance(extra_root.get("release_copy"), dict) else {}
        publish_repo_relative, publish_path = resolve_repo_binding(
            repo_root,
            bindings.get("publish_config_path"),
            "bindings.publish_config_path",
        )
        readme_repo_relative, readme_path = resolve_repo_binding(
            repo_root,
            bindings.get("primary_readme_path"),
            "bindings.primary_readme_path",
        )
        maintaining_repo_relative, maintaining_path = resolve_repo_binding(
            repo_root,
            release_extra.get("maintaining_path"),
            "extra.release_copy.maintaining_path",
        )
        checklist_repo_relative, checklist_path = resolve_repo_binding(
            repo_root,
            release_extra.get("release_checklist_template_path"),
            "extra.release_copy.release_checklist_template_path",
        )
        workflow_repo_relative, workflow_path = resolve_repo_binding(
            repo_root,
            release_extra.get("release_workflow_path"),
            "extra.release_copy.release_workflow_path",
        )
        settings_repo_relative, setting_path = resolve_repo_binding(
            repo_root,
            bindings.get("settings_source_path"),
            "bindings.settings_source_path",
        )
        for repo_relative, path, label in (
            (publish_repo_relative, publish_path, "bindings.publish_config_path"),
            (readme_repo_relative, readme_path, "bindings.primary_readme_path"),
            (maintaining_repo_relative, maintaining_path, "extra.release_copy.maintaining_path"),
            (
                checklist_repo_relative,
                checklist_path,
                "extra.release_copy.release_checklist_template_path",
            ),
            (workflow_repo_relative, workflow_path, "extra.release_copy.release_workflow_path"),
            (settings_repo_relative, setting_path, "bindings.settings_source_path"),
        ):
            require_repo_binding_file(path, repo_relative, label)
        issue_defaults = (
            release_extra.get("issue_defaults")
            if isinstance(release_extra.get("issue_defaults"), dict)
            else {}
        )
        helper_repo_relative, helper_resolved = validate_local_helper_path(repo_root, args.local_release_helper)
        base_tag = args.base_tag or latest_reachable_tag(repo_root)
        if not base_tag:
            raise RuntimeError("no reachable v* tag was found; supply --base-tag explicitly")
    except RuntimeError as exc:
        print(f"collect_release_copy_context.py: {exc}", file=sys.stderr)
        return 1

    revision_range = f"{base_tag}..HEAD"

    publish = parse_publish_configuration(publish_path)
    base_tag_publish = publish_configuration_at_tag(repo_root, base_tag, publish_repo_relative)
    target_version = (args.target_version or publish["mod_version"]).strip()
    repo_slug = infer_repo_slug(repo_root)
    readme_text = read_text(readme_path)
    readme_sections = parse_markdown_sections(readme_text)
    maintaining_text = read_text(maintaining_path)
    checklist_text = read_text(checklist_path)
    workflow_text = read_text(workflow_path)
    setting_text = read_text(setting_path)

    changed_files = git_changed_files(repo_root, revision_range)
    changed_file_stats = git_changed_file_stats(repo_root, revision_range)
    changed_groups = summarize_groups(classify_changed_files(changed_files))
    evidence_file_payload = load_json_file(Path(args.evidence_file)) if args.evidence_file else None
    existing_release_issue = (
        release_issue_by_number(repo_root, repo_slug, args.release_issue_number)
        if args.release_issue_number
        else find_existing_release_issue(repo_root, repo_slug, target_version)
    )
    evidence = merge_optional_dicts(
        existing_release_issue.get("evidence") if isinstance(existing_release_issue, dict) else None,
        evidence_file_payload if isinstance(evidence_file_payload, dict) else None,
    )

    local_helper: dict[str, Any] = {
        "requested_path": helper_repo_relative,
        "path": str(helper_resolved),
        "repo_relative_path": helper_repo_relative,
        "status": "missing_local_release_script",
    }
    if helper_resolved.is_file():
        local_helper.update(parse_local_helper(read_text(helper_resolved), helper_repo_relative))
        local_helper["status"] = "present"

    context = {
        "repo_root": str(repo_root),
        "repo_slug": repo_slug,
        "branch": git_branch(repo_root),
        "head_commit": git_head_commit(repo_root),
        "base_tag": base_tag,
        "revision_range": revision_range,
        "repo_profile_name": repo_profile.get("name"),
        "repo_profile_path": profile_path.as_posix(),
        "repo_profile_summary": repo_profile.get("summary"),
        "repo_profile": repo_profile,
        "builder_compatibility": build_builder_compatibility(repo_profile),
        "target_version": target_version,
        "rule_files": {
            "publish_configuration": str(publish_path),
            "readme": str(readme_path),
            "maintaining": str(maintaining_path),
            "release_checklist_template": str(checklist_path),
            "release_workflow": str(workflow_path),
            "setting_defaults": str(setting_path),
        },
        "publish_configuration": publish,
        "base_tag_publish_configuration": base_tag_publish,
        "readme": {
            "path": str(readme_path),
            "intro_text": readme_text.split("\n## ", 1)[0].strip(),
            "sections": readme_sections,
            "settings_defaults": parse_readme_settings_table(readme_sections.get("Settings", "")),
        },
        "maintaining": {
            "path": str(maintaining_path),
            "release_operations_excerpt": first_heading_block(maintaining_text, "## Release Operations"),
        },
        "release_checklist": {
            "path": str(checklist_path),
            **parse_release_checklist(checklist_text),
        },
        "release_workflow": {
            "path": str(workflow_path),
            **parse_release_workflow(workflow_text),
        },
        "setting_defaults": parse_setting_defaults(setting_text),
        "changed_files": changed_files,
        "changed_file_stats": changed_file_stats,
        "changed_file_groups": changed_groups,
        "diff_stat": git_diff_stat(repo_root, revision_range),
        "commit_subjects": git_commit_subjects(repo_root, revision_range),
        "commit_count": git_commit_count(repo_root, revision_range),
        "evidence_file": str(Path(args.evidence_file).resolve()) if args.evidence_file else None,
        "existing_release_issue": existing_release_issue,
        "evidence": evidence,
        "project_title_default": (
            str(issue_defaults.get("project_title") or "").strip()
            or project_title_default(readme_text, maintaining_text)
        ),
        "issue_defaults": issue_defaults,
        "local_release_helper": local_helper,
        "source_fingerprints": {
            "publish_configuration": json_fingerprint(read_text(publish_path)),
            "readme": json_fingerprint(readme_text),
            "maintaining": json_fingerprint(maintaining_text),
            "release_checklist_template": json_fingerprint(checklist_text),
            "release_workflow": json_fingerprint(workflow_text),
            "setting_defaults": json_fingerprint(setting_text),
        },
    }

    context["freshness_tuple"] = freshness_tuple(context)
    context["context_fingerprint"] = json_fingerprint(
        {
            key: value
            for key, value in context.items()
            if key != "context_fingerprint"
        }
    )

    if context["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(context["builder_compatibility"]), file=sys.stderr)
    output_path.write_text(json.dumps(context, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
