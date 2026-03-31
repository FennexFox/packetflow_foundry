#!/usr/bin/env python3
"""Collect structured workflow context for public-docs-sync."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fnmatch import fnmatch
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

SKILL_NAME = "public-docs-sync"
SKILL_VERSION = "0.2.0"
WORKFLOW_FAMILY = "repo-audit"
ARCHETYPE = "audit-and-apply"
GITHUB_AUTH_POLICY = "fail-closed"
DEFAULT_AUTHORITY_ORDER = [
    "tracked runtime and shipped metadata",
    "tracked public docs and public workflow templates",
    "selected GitHub PR or discussion evidence for the relevant change unit",
    "structured workflow packets",
    "local last-success state",
]
DEFAULT_STOP_CONDITIONS = [
    "low confidence",
    "stale snapshot or stale context",
    "ambiguous packet or ownership match",
    "unreachable saved baseline",
    "GitHub evidence is required but gh auth is invalid",
    "narrative-only drift that exceeds deterministic apply boundaries",
]
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
SETTING_PROPERTY_RE = re.compile(
    r"public\s+(?P<type>\w+)\s+(?P<name>\w+)\s*\{[^}]*\}(?:\s*=\s*(?P<value>[^;]+)\s*;)?",
    re.MULTILINE,
)
SET_DEFAULTS_BODY_RE = re.compile(
    r"public\s+override\s+void\s+SetDefaults\(\)\s*\{(?P<body>.*?)\n\s*\}",
    re.DOTALL,
)
SET_DEFAULTS_ASSIGN_RE = re.compile(r"(?P<name>\w+)\s*=\s*(?P<value>[^;]+);")
LOCALE_TEXT_RE = re.compile(
    r'GetOption(?P<kind>Label|Desc)LocaleID\(nameof\(Setting\.(?P<name>\w+)\)\),\s*"(?P<text>(?:[^"\\]|\\.)*)"'
)
README_TABLE_ROW_RE = re.compile(
    r"^\|\s*`(?P<name>[^`]+)`\s*\|\s*`?(?P<default>[^|`]+)`?\s*\|\s*(?P<purpose>.+?)\s*\|\s*$"
)
GENERATED_PATH_RE = re.compile(
    r"(^|/)(bin|obj|dist|build|coverage|generated|gen|out|artifacts)/|"
    r"\.(g|generated)\.[^.]+$|"
    r"\.designer\.[^.]+$",
    re.IGNORECASE,
)
MERGE_PR_SUBJECT_RE = re.compile(r"^Merge pull request #(?P<number>\d+) from (?P<head>[^\s]+)\s*$")
DISCUSSION_URL_RE = re.compile(
    r"https://github\.com/(?P<slug>[^/\s]+/[^/\s]+)/discussions/(?P<number>\d+)",
    re.IGNORECASE,
)
REPO_SLUG_RE = re.compile(r"github\.com[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE)
PACKET_KEYWORDS = {
    "claims_packet": [
        "setting",
        "default",
        "compatibility",
        "behavior",
        "readme",
        "release copy",
        "version",
        "shipped",
    ],
    "reporting_packet": [
        "telemetry",
        "diagnostic",
        "diagnostics",
        "performance",
        "perf",
        "log",
        "logs",
        "report",
        "reporting",
        "investigation",
        "evidence",
        "triage",
    ],
    "workflow_packet": [
        "workflow",
        "contributing",
        "maintaining",
        "pull request",
        "release",
        "automation",
        "checklist",
        "template",
    ],
    "forms_batch_packet": [
        "issue form",
        "issue template",
        "bug report",
        "feature request",
        "investigation form",
        "release checklist",
    ],
}


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


def repo_profile_bindings(repo_profile: dict[str, Any]) -> dict[str, Any]:
    bindings = repo_profile.get("bindings")
    return bindings if isinstance(bindings, dict) else {}


def public_docs_profile_extra(repo_profile: dict[str, Any]) -> dict[str, Any]:
    extra_root = repo_profile.get("extra")
    if not isinstance(extra_root, dict):
        return {}
    extra = extra_root.get("public_docs_sync")
    return extra if isinstance(extra, dict) else {}


def packet_defaults(repo_profile: dict[str, Any]) -> dict[str, Any]:
    defaults = repo_profile.get("packet_defaults")
    return defaults if isinstance(defaults, dict) else {}


def packet_review_doc_config(repo_profile: dict[str, Any]) -> dict[str, list[str]]:
    review_docs = packet_defaults(repo_profile).get("review_docs")
    if not isinstance(review_docs, dict):
        return {}
    return {
        str(packet): [normalize_path(item) for item in items if str(item or "").strip()]
        for packet, items in review_docs.items()
        if isinstance(items, list)
    }


def packet_source_globs(repo_profile: dict[str, Any]) -> dict[str, list[str]]:
    source_globs = packet_defaults(repo_profile).get("source_path_globs")
    if not isinstance(source_globs, dict):
        return {}
    return {
        str(packet): [normalize_path(item) for item in items if str(item or "").strip()]
        for packet, items in source_globs.items()
        if isinstance(items, list)
    }


def issue_template_groups(repo_profile: dict[str, Any]) -> dict[str, set[str]]:
    groups = public_docs_profile_extra(repo_profile).get("issue_template_groups")
    if not isinstance(groups, dict):
        return {"reporting": set(), "workflow": set()}
    return {
        "reporting": {
            str(name).strip()
            for name in groups.get("reporting", [])
            if str(name or "").strip()
        },
        "workflow": {
            str(name).strip()
            for name in groups.get("workflow", [])
            if str(name or "").strip()
        },
    }


def configured_public_doc_inventory(repo_profile: dict[str, Any]) -> list[str]:
    inventory = public_docs_profile_extra(repo_profile).get("audited_public_doc_inventory")
    if not isinstance(inventory, list):
        return []
    return [normalize_path(item) for item in inventory if str(item or "").strip()]


def configured_state_namespace(repo_profile: dict[str, Any]) -> str:
    state = public_docs_profile_extra(repo_profile).get("state")
    if not isinstance(state, dict):
        return SKILL_NAME
    text = str(state.get("namespace") or "").strip()
    return text or SKILL_NAME


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, help="Repository root to inspect.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
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
    parser.add_argument("--full", action="store_true", help="Ignore saved state and audit the full public surface.")
    parser.add_argument(
        "--since-ref",
        help="Explicit git ref to diff against for this run. Overrides saved state for the run.",
    )
    parser.add_argument(
        "--state-file",
        help="Optional override for the last-success marker JSON path.",
    )
    return parser.parse_args()


def normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_command(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
    stdin_text: str | None = None,
) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        input=stdin_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"{args[0]} failed"
        raise RuntimeError(detail)
    return result.stdout


def run_git(repo_root: Path, args: list[str], *, check: bool = True) -> str:
    return run_command(["git", *args], repo_root, check=check)


def run_gh_json(
    repo_root: Path,
    args: list[str],
    *,
    stdin_text: str | None = None,
) -> Any:
    output = run_command(["gh", *args], repo_root, stdin_text=stdin_text)
    text = output.strip()
    return json.loads(text) if text else {}


def resolve_repo_root(repo_root: str) -> Path:
    requested = Path(repo_root).resolve()
    if not requested.exists():
        raise SystemExit(f"[ERROR] Missing repo root: {requested}")
    try:
        actual = run_git(requested, ["rev-parse", "--show-toplevel"]).strip()
    except RuntimeError as exc:
        raise SystemExit(f"[ERROR] {requested} is not inside a git repository: {exc}") from exc
    return Path(actual).resolve()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_exists(repo_root: Path, relpath: str) -> bool:
    return (repo_root / Path(relpath)).exists()


def read_text_file(repo_root: Path, relpath: str) -> str:
    return (repo_root / Path(relpath)).read_text(encoding="utf-8", errors="replace")


def extract_headings(text: str) -> list[str]:
    return [match.group(2).strip() for match in MARKDOWN_HEADING_RE.finditer(text)]


def parse_scalar_text(raw: str) -> str:
    text = raw.strip().strip("`").strip().rstrip(",")
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower
    trimmed = re.sub(r"[fFdDmM]$", "", text)
    try:
        if "." in trimmed or "e" in trimmed.lower():
            value = float(trimmed)
            if value.is_integer():
                return str(int(value))
            return format(value, ".12g")
        return str(int(trimmed))
    except ValueError:
        return text


def parse_csharp_string(raw: str) -> str:
    text = raw.encode("utf-8").decode("unicode_escape")
    return text.strip()


def parse_setting_defaults(setting_text: str) -> dict[str, dict[str, Any]]:
    defaults_from_properties: dict[str, dict[str, Any]] = {}
    for match in SETTING_PROPERTY_RE.finditer(setting_text):
        name = match.group("name")
        defaults_from_properties[name] = {
            "type": match.group("type"),
            "default": parse_scalar_text(match.group("value")) if match.group("value") else None,
        }

    defaults_from_method: dict[str, str] = {}
    body_match = SET_DEFAULTS_BODY_RE.search(setting_text)
    if body_match:
        for match in SET_DEFAULTS_ASSIGN_RE.finditer(body_match.group("body")):
            defaults_from_method[match.group("name")] = parse_scalar_text(match.group("value"))

    labels: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    for match in LOCALE_TEXT_RE.finditer(setting_text):
        bucket = labels if match.group("kind") == "Label" else descriptions
        bucket[match.group("name")] = parse_csharp_string(match.group("text"))

    merged: dict[str, dict[str, Any]] = {}
    for name, info in defaults_from_properties.items():
        merged[name] = {
            "type": info["type"],
            "default": defaults_from_method.get(name, info["default"]),
            "label": labels.get(name),
            "description": descriptions.get(name),
        }
    return merged


def parse_readme_settings_table(readme_text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    in_table = False
    for line in readme_text.splitlines():
        if line.strip() == "| Setting | Default | Purpose |":
            in_table = True
            continue
        if not in_table:
            continue
        if line.strip().startswith("| ---"):
            continue
        if not line.strip().startswith("|"):
            break
        match = README_TABLE_ROW_RE.match(line)
        if not match:
            continue
        rows[match.group("name")] = {
            "default": parse_scalar_text(match.group("default")),
            "raw_default": match.group("default").strip(),
            "purpose": match.group("purpose").strip(),
        }
    return rows


def parse_publish_configuration(publish_text: str) -> dict[str, Any]:
    root = ET.fromstring(publish_text)

    def read_attr(tag_name: str, attr_name: str = "Value") -> str | None:
        element = root.find(tag_name)
        return element.attrib.get(attr_name) if element is not None else None

    def read_block_lines(tag_name: str) -> list[str]:
        element = root.find(tag_name)
        if element is None:
            return []
        text = "".join(element.itertext())
        return [line.strip() for line in text.splitlines() if line.strip()]

    return {
        "display_name": read_attr("DisplayName"),
        "short_description": read_attr("ShortDescription"),
        "mod_version": read_attr("ModVersion"),
        "game_version": read_attr("GameVersion"),
        "long_description_lines": read_block_lines("LongDescription"),
        "change_log_lines": read_block_lines("ChangeLog"),
    }


def parse_issue_form_metadata(text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("name", "description", "title", "labels"):
        match = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        if not match:
            continue
        value = match.group(1).strip()
        if key == "labels" and value.startswith("[") and value.endswith("]"):
            labels = [
                part.strip().strip('"').strip("'")
                for part in value[1:-1].split(",")
                if part.strip()
            ]
            metadata[key] = labels
        else:
            metadata[key] = value.strip('"').strip("'")
    return metadata


def classify_text_kind(relpath: str) -> str:
    lower = relpath.lower()
    if lower.endswith(".md"):
        return "markdown"
    if lower.endswith((".yml", ".yaml")):
        return "yaml"
    if lower.endswith(".xml"):
        return "xml"
    if lower.endswith(".cs"):
        return "code"
    return "text"


def scan_relative_links(repo_root: Path, relpath: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    links: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    parent = (repo_root / Path(relpath)).parent
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if target.startswith(("app://", "plugin://")):
            continue
        base_target = target.split("#", 1)[0]
        candidate = (parent / Path(base_target)).resolve()
        try:
            normalized_target = normalize_path(candidate.relative_to(repo_root))
            within_repo = True
        except ValueError:
            normalized_target = normalize_path(candidate)
            within_repo = False
        entry = {
            "source_path": relpath,
            "target": target,
            "resolved_path": normalized_target,
            "within_repo": within_repo,
            "exists": within_repo and candidate.exists(),
        }
        links.append(entry)
        if not entry["exists"]:
            missing.append(entry)
    return links, missing


def summarize_file(repo_root: Path, relpath: str, *, publish_config_path: str | None = None) -> dict[str, Any]:
    path = repo_root / Path(relpath)
    summary: dict[str, Any] = {
        "path": relpath,
        "exists": path.exists(),
        "kind": classify_text_kind(relpath),
    }
    if not path.exists():
        return summary

    text = path.read_text(encoding="utf-8", errors="replace")
    summary.update(
        {
            "sha256": "sha256:" + sha256_text(text),
            "line_count": len(text.splitlines()),
            "preview_lines": text.splitlines()[:12],
        }
    )
    links, missing_links = scan_relative_links(repo_root, relpath, text)
    summary["relative_links"] = links
    summary["missing_links"] = missing_links

    if summary["kind"] == "markdown":
        summary["headings"] = extract_headings(text)
        if relpath == "README.md":
            summary["settings_table"] = parse_readme_settings_table(text)
    elif relpath.endswith(".yml") or relpath.endswith(".yaml"):
        summary["issue_form"] = parse_issue_form_metadata(text)
    elif publish_config_path and relpath == normalize_path(publish_config_path):
        summary["publish_configuration"] = parse_publish_configuration(text)

    return summary


def discover_issue_template_paths(repo_root: Path) -> list[str]:
    issue_dir = repo_root / ".github" / "ISSUE_TEMPLATE"
    if not issue_dir.is_dir():
        return []
    paths = [
        normalize_path(path.relative_to(repo_root))
        for path in issue_dir.glob("*.yml")
        if path.is_file()
    ]
    return sorted(dict.fromkeys(paths))


def collect_public_doc_paths(repo_root: Path, repo_profile: dict[str, Any]) -> list[str]:
    discovered = configured_public_doc_inventory(repo_profile) + discover_issue_template_paths(repo_root)
    return sorted(dict.fromkeys(discovered))


def infer_repo_slug(remote_url: str) -> str | None:
    match = REPO_SLUG_RE.search(remote_url.strip())
    return match.group("slug") if match else None


def repo_identity(repo_root: Path) -> dict[str, str]:
    remote = run_git(repo_root, ["config", "--get", "remote.origin.url"], check=False).strip()
    repo_id = remote or normalize_path(repo_root)
    repo_hash = sha256_text(repo_id)[:16]
    repo_slug = infer_repo_slug(remote)
    return {
        "repo_id": repo_id,
        "repo_hash": repo_hash,
        "remote_url": remote or "",
        "repo_slug": repo_slug or "",
        "repo_name": repo_root.name,
    }


def default_state_file(repo_hash: str, repo_profile: dict[str, Any] | None = None) -> Path:
    active_profile = repo_profile or load_repo_profile(default_repo_profile_path())
    namespace = configured_state_namespace(active_profile)
    return Path.home() / ".codex" / "state" / namespace / f"{repo_hash}.json"


def git_head_commit(repo_root: Path) -> str:
    return run_git(repo_root, ["rev-parse", "HEAD"]).strip()


def git_branch(repo_root: Path) -> str | None:
    branch = run_git(repo_root, ["branch", "--show-current"], check=False).strip()
    return branch or None


def git_ref_exists(repo_root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def git_ref_to_commit(repo_root: Path, ref: str) -> str:
    try:
        return run_git(repo_root, ["rev-parse", f"{ref}^{{commit}}"]).strip()
    except RuntimeError as exc:
        raise SystemExit(f"[ERROR] Invalid --since-ref `{ref}`: {exc}") from exc


def commit_exists(repo_root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def commit_is_ancestor(repo_root: Path, older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def git_merge_base(repo_root: Path, left: str, right: str) -> str | None:
    try:
        return run_git(repo_root, ["merge-base", left, right]).strip() or None
    except RuntimeError:
        return None


def git_commit_subject(repo_root: Path, commit: str = "HEAD") -> str:
    return run_git(repo_root, ["show", "-s", "--format=%s", commit], check=False).strip()


def git_commit_parents(repo_root: Path, commit: str) -> list[str]:
    output = run_git(repo_root, ["rev-list", "--parents", "-n", "1", commit], check=False).strip()
    if not output:
        return []
    parts = output.split()
    return parts[1:]


def git_tracking_branch(repo_root: Path, branch: str | None) -> str | None:
    if not branch:
        return None
    output = run_git(repo_root, ["rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], check=False).strip()
    return output or None


def git_default_remote_branch(repo_root: Path) -> str | None:
    output = run_git(repo_root, ["symbolic-ref", "refs/remotes/origin/HEAD"], check=False).strip()
    return output.replace("refs/remotes/", "", 1) if output else None


def collect_status_paths(repo_root: Path) -> list[str]:
    output = run_git(repo_root, ["status", "--porcelain=v1", "--untracked-files=all"], check=False)
    paths: list[str] = []
    for line in output.splitlines():
        if not line or line.startswith("## "):
            continue
        raw_path = line[3:].strip()
        if " -> " in raw_path:
            left, right = raw_path.split(" -> ", 1)
            paths.extend([normalize_path(left), normalize_path(right)])
        else:
            paths.append(normalize_path(raw_path))
    return sorted(dict.fromkeys(paths))


def collect_diff_paths(repo_root: Path, base_commit: str) -> list[str]:
    output = run_git(repo_root, ["diff", "--name-only", f"{base_commit}..HEAD"], check=False)
    paths = [normalize_path(line.strip()) for line in output.splitlines() if line.strip()]
    return sorted(dict.fromkeys(paths))


def forms_doc_paths(public_doc_paths: list[str]) -> list[str]:
    return [path for path in public_doc_paths if path.startswith(".github/ISSUE_TEMPLATE/")]


def is_generated_path(relpath: str) -> bool:
    return bool(GENERATED_PATH_RE.search(relpath))


def path_matches_any_glob(relpath: str, patterns: list[str]) -> bool:
    normalized = normalize_path(relpath)
    return any(fnmatch(normalized, normalize_path(pattern)) for pattern in patterns)


def packet_for_path(relpath: str, public_doc_paths: list[str], repo_profile: dict[str, Any]) -> set[str]:
    packets: set[str] = set()
    form_paths = set(forms_doc_paths(public_doc_paths))
    groups = issue_template_groups(repo_profile)
    review_doc_map = packet_review_doc_config(repo_profile)
    source_glob_map = packet_source_globs(repo_profile)
    reporting_forms = {path for path in form_paths if Path(path).name in groups["reporting"]}
    workflow_forms = {path for path in form_paths if Path(path).name in groups["workflow"]}

    if relpath in form_paths:
        packets.add("forms_batch_packet")
        if relpath in reporting_forms:
            packets.add("reporting_packet")
        if relpath in workflow_forms:
            packets.add("workflow_packet")

    for packet_name, review_docs in review_doc_map.items():
        if relpath in review_docs:
            packets.add(packet_name)
    for packet_name, patterns in source_glob_map.items():
        if path_matches_any_glob(relpath, patterns):
            packets.add(packet_name)

    return packets


def packet_review_docs(public_doc_paths: list[str], repo_profile: dict[str, Any]) -> dict[str, list[str]]:
    configured = packet_review_doc_config(repo_profile)
    form_paths = forms_doc_paths(public_doc_paths)
    result = {
        "claims_packet": [path for path in configured.get("claims_packet", []) if path in public_doc_paths],
        "reporting_packet": [path for path in configured.get("reporting_packet", []) if path in public_doc_paths],
        "workflow_packet": [path for path in configured.get("workflow_packet", []) if path in public_doc_paths],
        "forms_batch_packet": form_paths,
    }
    if configured.get("forms_batch_packet"):
        result["forms_batch_packet"] = [
            path for path in configured["forms_batch_packet"] if path in public_doc_paths
        ] or form_paths
    return result


def connection_nodes(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return nodes
    return []


def clip_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def stable_dedupe(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=True) if not isinstance(item, str) else item
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_comment(raw: dict[str, Any], artifact_type: str, artifact_id: str) -> dict[str, Any]:
    author = raw.get("author") or {}
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "author": str(author.get("login") or author.get("name") or raw.get("authorLogin") or "").strip() or None,
        "created_at": raw.get("createdAt") or raw.get("created_at"),
        "updated_at": raw.get("updatedAt") or raw.get("updated_at"),
        "url": raw.get("url"),
        "body": str(raw.get("body") or raw.get("bodyText") or "").strip(),
    }


def normalize_file_entries(raw: Any) -> list[dict[str, Any]]:
    items = connection_nodes(raw)
    results: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            results.append({"path": normalize_path(item), "additions": None, "deletions": None})
            continue
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("name") or "").strip()
        if not path:
            continue
        results.append(
            {
                "path": normalize_path(path),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
            }
        )
    return stable_dedupe(results)


def normalize_review_summary(raw_reviews: Any, review_decision: Any) -> dict[str, Any]:
    reviews = connection_nodes(raw_reviews)
    states: dict[str, int] = {}
    normalized_reviews: list[dict[str, Any]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        state = str(review.get("state") or "").strip() or "UNKNOWN"
        states[state] = states.get(state, 0) + 1
        author = review.get("author") or {}
        normalized_reviews.append(
            {
                "state": state,
                "author": author.get("login") or author.get("name"),
                "submitted_at": review.get("submittedAt"),
                "url": review.get("url"),
                "body_excerpt": clip_text(review.get("body")),
            }
        )
    return {
        "review_decision": review_decision,
        "state_counts": states,
        "latest_reviews": normalized_reviews[-5:],
    }


def digest_comments(comments: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ordered = sorted(
        comments,
        key=lambda item: (
            str(item.get("updated_at") or ""),
            str(item.get("created_at") or ""),
            str(item.get("url") or ""),
        ),
    )
    digests: list[dict[str, Any]] = []
    for item in ordered[-limit:]:
        digests.append(
            {
                "artifact_type": item.get("artifact_type"),
                "artifact_id": item.get("artifact_id"),
                "author": item.get("author"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "url": item.get("url"),
                "body_excerpt": clip_text(item.get("body")),
            }
        )
    return digests


def ensure_gh_auth(repo_root: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "gh not found",
        }
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def require_gh_auth(repo_root: Path) -> dict[str, Any]:
    status = ensure_gh_auth(repo_root)
    if status["ok"]:
        return status
    detail = status["stderr"] or status["stdout"] or "gh auth status failed"
    raise SystemExit(
        "[ERROR] GitHub evidence is required for this run but gh auth is invalid. "
        f"Run `gh auth login` first. Detail: {detail}"
    )


def parse_owner_repo(repo_slug: str) -> tuple[str, str]:
    owner, name = repo_slug.split("/", 1)
    return owner, name


def build_candidate(
    *,
    kind: str,
    label: str,
    source: str,
    base_commit: str | None,
    head_commit: str | None,
    selection_reason: str,
    primary_pr_number: int | None = None,
    primary_pr_url: str | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
    requires_github_evidence: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "source": source,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "selection_reason": selection_reason,
        "primary_pr_number": primary_pr_number,
        "primary_pr_url": primary_pr_url,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "requires_github_evidence": requires_github_evidence,
        "metadata": metadata or {},
    }


def annotate_candidate(candidate: dict[str, Any], *, selected: bool, rejected_reason: str | None = None) -> dict[str, Any]:
    payload = dict(candidate)
    payload["selected"] = selected
    payload["usable"] = selected or rejected_reason is None
    payload["rejected_reason"] = rejected_reason
    return payload


def build_baseline(
    repo_root: Path,
    args: argparse.Namespace,
    state_file: Path,
    identity: dict[str, str],
    head_commit: str,
    branch: str | None,
) -> dict[str, Any]:
    if args.full:
        return {
            "mode": "full",
            "status": "full_requested",
            "base_commit": None,
            "requested_ref": None,
            "state_file": normalize_path(state_file),
            "saved_marker": None,
            "fallback_reason": None,
        }

    if args.since_ref:
        base_commit = git_ref_to_commit(repo_root, args.since_ref)
        return {
            "mode": "since-ref",
            "status": "explicit_ref",
            "base_commit": base_commit,
            "requested_ref": args.since_ref,
            "state_file": normalize_path(state_file),
            "saved_marker": None,
            "fallback_reason": None,
        }

    if not state_file.exists():
        return {
            "mode": "saved-marker-unavailable",
            "status": "missing_saved_marker",
            "base_commit": None,
            "requested_ref": None,
            "state_file": normalize_path(state_file),
            "saved_marker": None,
            "fallback_reason": "missing_saved_marker",
        }

    marker = load_json(state_file)
    marker_commit = str(marker.get("head_commit", "")).strip()
    marker_repo_id = str(marker.get("repo_id", "")).strip()
    marker_repo_slug = str(marker.get("repo_slug", "")).strip()
    marker_branch = str(marker.get("branch", "")).strip() or None
    marker_relevant_ref = marker.get("relevant_ref") or {}
    relevant_base = str(marker_relevant_ref.get("base_commit") or "").strip()
    relevant_head = str(marker_relevant_ref.get("head_commit") or "").strip()
    stale_reason = None

    if marker_repo_id and marker_repo_id != identity["repo_id"]:
        stale_reason = "repo_identity_mismatch"
    elif marker_repo_slug and identity["repo_slug"] and marker_repo_slug != identity["repo_slug"]:
        stale_reason = "repo_slug_mismatch"
    elif not marker_commit:
        stale_reason = "missing_marker_commit"
    elif not commit_exists(repo_root, marker_commit):
        stale_reason = "unreachable_saved_baseline"
    elif not commit_is_ancestor(repo_root, marker_commit, head_commit):
        stale_reason = "non_ancestor_saved_baseline"
    elif marker_branch and branch and marker_branch != branch:
        stale_reason = "branch_changed_since_last_success"
    elif relevant_base and not commit_exists(repo_root, relevant_base):
        stale_reason = "relevant_ref_base_unreachable"
    elif relevant_head and not commit_exists(repo_root, relevant_head):
        stale_reason = "relevant_ref_head_unreachable"
    elif relevant_head and not commit_is_ancestor(repo_root, relevant_head, head_commit):
        stale_reason = "relevant_ref_head_not_ancestor"

    if stale_reason:
        return {
            "mode": "saved-marker-unavailable",
            "status": "saved_marker_stale",
            "base_commit": None,
            "requested_ref": None,
            "state_file": normalize_path(state_file),
            "saved_marker": marker,
            "fallback_reason": stale_reason,
        }

    return {
        "mode": "saved-marker",
        "status": "saved_marker_usable",
        "base_commit": marker_commit,
        "requested_ref": None,
        "state_file": normalize_path(state_file),
        "saved_marker": marker,
        "fallback_reason": None,
    }


def head_merge_pr_candidate(repo_root: Path, head_commit: str) -> dict[str, Any] | None:
    subject = git_commit_subject(repo_root, head_commit)
    match = MERGE_PR_SUBJECT_RE.match(subject)
    if not match:
        return None
    parents = git_commit_parents(repo_root, head_commit)
    if len(parents) < 2:
        return None
    pr_number = int(match.group("number"))
    return build_candidate(
        kind="merged-pr",
        label=f"PR #{pr_number}",
        source="head-merge-commit",
        base_commit=parents[0],
        head_commit=head_commit,
        selection_reason="HEAD is a merge commit for a pull request; use its first-parent range as the relevant unit.",
        primary_pr_number=pr_number,
        head_ref=match.group("head"),
        requires_github_evidence=True,
        metadata={"merge_commit": head_commit},
    )


def latest_merged_pr_candidate_in_range(repo_root: Path, base_commit: str, head_commit: str) -> dict[str, Any] | None:
    if base_commit == head_commit:
        return None
    output = run_git(
        repo_root,
        ["log", "--first-parent", "--merges", "--format=%H%x09%s", f"{base_commit}..{head_commit}"],
        check=False,
    )
    for line in output.splitlines():
        if not line.strip():
            continue
        commit, _, subject = line.partition("\t")
        match = MERGE_PR_SUBJECT_RE.match(subject.strip())
        if not match:
            continue
        parents = git_commit_parents(repo_root, commit)
        if len(parents) < 2:
            continue
        pr_number = int(match.group("number"))
        return build_candidate(
            kind="merged-pr",
            label=f"PR #{pr_number}",
            source="saved-marker-range",
            base_commit=parents[0],
            head_commit=commit,
            selection_reason="The saved-marker range contains a merged pull request; use the latest merged PR as the primary evidence unit.",
            primary_pr_number=pr_number,
            head_ref=match.group("head"),
            requires_github_evidence=True,
            metadata={"merge_commit": commit, "range_base": base_commit},
        )
    return None


def load_current_branch_pr_candidate(
    repo_root: Path,
    repo_slug: str,
    branch: str | None,
    head_commit: str,
) -> dict[str, Any] | None:
    if not branch:
        return None
    require_gh_auth(repo_root)
    try:
        payload = run_gh_json(
            repo_root,
            [
                "pr",
                "view",
                branch,
                "--repo",
                repo_slug,
                "--json",
                "number,title,url,baseRefName,baseRefOid,headRefName,headRefOid,state",
            ],
        )
    except RuntimeError as exc:
        message = str(exc)
        if "no pull requests found" in message.lower():
            return None
        raise

    base_ref = str(payload.get("baseRefName") or "").strip() or None
    head_ref = str(payload.get("headRefName") or "").strip() or branch
    merge_base = None
    for candidate_ref in [
        str(payload.get("baseRefOid") or "").strip(),
        base_ref or "",
        f"origin/{base_ref}" if base_ref else "",
    ]:
        if not candidate_ref:
            continue
        merge_base = git_merge_base(repo_root, candidate_ref, head_commit)
        if merge_base:
            break
    if not merge_base:
        merge_base = git_head_commit(repo_root)

    return build_candidate(
        kind="current-branch-pr",
        label=f"PR #{payload.get('number')}",
        source="current-branch-open-pr",
        base_commit=merge_base,
        head_commit=str(payload.get("headRefOid") or head_commit),
        selection_reason="The current branch has an open pull request; use the PR base/head range as the relevant unit.",
        primary_pr_number=int(payload.get("number")),
        primary_pr_url=str(payload.get("url") or "") or None,
        base_ref=base_ref,
        head_ref=head_ref,
        requires_github_evidence=True,
    )


def merge_base_candidate(
    repo_root: Path,
    branch: str | None,
    head_commit: str,
) -> dict[str, Any] | None:
    tracking = git_tracking_branch(repo_root, branch)
    default_remote = git_default_remote_branch(repo_root)
    candidate_refs = [tracking, default_remote]
    for extra in ("origin/master", "origin/main", "origin/develop", "master", "main", "develop"):
        candidate_refs.append(extra)
    seen: set[str] = set()
    for ref in candidate_refs:
        if not ref or ref in seen:
            continue
        seen.add(ref)
        if not git_ref_exists(repo_root, ref):
            continue
        merge_base = git_merge_base(repo_root, ref, head_commit)
        if not merge_base:
            continue
        return build_candidate(
            kind="git-merge-base",
            label=f"{ref}...HEAD",
            source="git-merge-base",
            base_commit=merge_base,
            head_commit=head_commit,
            selection_reason="No merged PR or open PR was selected; use the current branch versus its upstream/default merge-base range.",
            base_ref=ref,
            requires_github_evidence=False,
        )
    return None


def select_relevant_ref(
    repo_root: Path,
    identity: dict[str, str],
    args: argparse.Namespace,
    baseline: dict[str, Any],
    head_commit: str,
    branch: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []

    if args.full:
        selected = build_candidate(
            kind="full-audit",
            label="full public-doc audit",
            source="explicit-full",
            base_commit=None,
            head_commit=head_commit,
            selection_reason="The caller requested a full audit.",
            requires_github_evidence=False,
        )
        return selected, [annotate_candidate(selected, selected=True)]

    if args.since_ref and baseline.get("base_commit"):
        selected = build_candidate(
            kind="explicit-ref",
            label=args.since_ref,
            source="explicit-since-ref",
            base_commit=baseline["base_commit"],
            head_commit=head_commit,
            selection_reason="The caller supplied --since-ref, which overrides saved state for this run.",
            requires_github_evidence=False,
        )
        return selected, [annotate_candidate(selected, selected=True)]

    if baseline.get("mode") == "saved-marker" and baseline.get("base_commit"):
        merged_candidate = latest_merged_pr_candidate_in_range(repo_root, baseline["base_commit"], head_commit)
        saved_range_candidate = build_candidate(
            kind="saved-marker-range",
            label=f"{baseline['base_commit'][:12]}..{head_commit[:12]}",
            source="saved-marker",
            base_commit=baseline["base_commit"],
            head_commit=head_commit,
            selection_reason="A reusable saved marker exists; use its range unless a newer merged PR or open PR provides a tighter evidence unit.",
            requires_github_evidence=False,
        )
        if merged_candidate:
            candidates.append(annotate_candidate(merged_candidate, selected=True))
            candidates.append(annotate_candidate(saved_range_candidate, selected=False, rejected_reason="superseded_by_latest_merged_pr"))
            return merged_candidate, candidates

        current_pr_candidate = None
        if identity["repo_slug"]:
            current_pr_candidate = load_current_branch_pr_candidate(repo_root, identity["repo_slug"], branch, head_commit)
        if current_pr_candidate:
            candidates.append(annotate_candidate(current_pr_candidate, selected=True))
            candidates.append(annotate_candidate(saved_range_candidate, selected=False, rejected_reason="superseded_by_current_branch_pr"))
            return current_pr_candidate, candidates

        candidates.append(annotate_candidate(saved_range_candidate, selected=True))
        return saved_range_candidate, candidates

    merged_head_candidate = head_merge_pr_candidate(repo_root, head_commit)
    if merged_head_candidate:
        candidates.append(annotate_candidate(merged_head_candidate, selected=True))
        return merged_head_candidate, candidates

    if identity["repo_slug"]:
        current_pr_candidate = load_current_branch_pr_candidate(repo_root, identity["repo_slug"], branch, head_commit)
        if current_pr_candidate:
            candidates.append(annotate_candidate(current_pr_candidate, selected=True))
            return current_pr_candidate, candidates

    merge_base_fallback = merge_base_candidate(repo_root, branch, head_commit)
    if merge_base_fallback:
        candidates.append(annotate_candidate(merge_base_fallback, selected=True))
        return merge_base_fallback, candidates

    full_fallback = build_candidate(
        kind="full-audit",
        label="full public-doc audit",
        source="auto-fallback-full",
        base_commit=None,
        head_commit=head_commit,
        selection_reason="No saved marker, PR-backed unit, or merge-base range was usable; fall back to a full audit.",
        requires_github_evidence=False,
    )
    candidates.append(annotate_candidate(full_fallback, selected=True))
    return full_fallback, candidates


def collect_discussion_refs(text: str, repo_slug: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for match in DISCUSSION_URL_RE.finditer(text or ""):
        if match.group("slug").lower() != repo_slug.lower():
            continue
        refs.append(
            {
                "repo_slug": repo_slug,
                "number": int(match.group("number")),
                "url": f"https://github.com/{repo_slug}/discussions/{match.group('number')}",
            }
        )
    return stable_dedupe(refs)


def packet_hints_from_text(text: str) -> set[str]:
    lower = text.lower()
    packets: set[str] = set()
    for packet_name, keywords in PACKET_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            packets.add(packet_name)
    return packets


def packet_hints_from_paths(
    paths: list[str],
    public_doc_paths: list[str],
    repo_profile: dict[str, Any],
) -> set[str]:
    packets: set[str] = set()
    for path in paths:
        packets.update(packet_for_path(path, public_doc_paths, repo_profile))
    return packets


def build_artifact_summary(title: str | None, body: str | None, comment_digests: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    if title:
        pieces.append(clip_text(title, 100))
    if body:
        pieces.append(clip_text(body, 120))
    if comment_digests:
        pieces.append("latest comment: " + clip_text(comment_digests[-1].get("body_excerpt"), 120))
    return " | ".join(piece for piece in pieces if piece)


def gather_pr_evidence(repo_root: Path, repo_slug: str, pr_number: int) -> dict[str, Any]:
    payload = run_gh_json(
        repo_root,
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo_slug,
            "--json",
            ",".join(
                [
                    "number",
                    "title",
                    "body",
                    "url",
                    "baseRefName",
                    "baseRefOid",
                    "headRefName",
                    "headRefOid",
                    "changedFiles",
                    "files",
                    "closingIssuesReferences",
                    "comments",
                    "latestReviews",
                    "reviewDecision",
                    "mergedAt",
                    "updatedAt",
                    "mergeCommit",
                ]
            ),
        ],
    )
    comments = [
        normalize_comment(item, "pull_request", f"PR #{pr_number}")
        for item in connection_nodes(payload.get("comments"))
        if isinstance(item, dict)
    ]
    comment_digests = digest_comments(comments)
    files = normalize_file_entries(payload.get("files"))
    review_summary = normalize_review_summary(payload.get("latestReviews"), payload.get("reviewDecision"))
    linked_issues = connection_nodes(payload.get("closingIssuesReferences"))
    return {
        "number": payload.get("number"),
        "title": payload.get("title"),
        "body": payload.get("body"),
        "url": payload.get("url"),
        "base_ref": payload.get("baseRefName"),
        "base_oid": payload.get("baseRefOid"),
        "head_ref": payload.get("headRefName"),
        "head_oid": payload.get("headRefOid"),
        "changed_files_count": payload.get("changedFiles"),
        "files": files,
        "linked_issues": linked_issues,
        "comments": comment_digests,
        "review_summary": review_summary,
        "merged_at": payload.get("mergedAt"),
        "updated_at": payload.get("updatedAt"),
    }


def gather_issue_evidence(repo_root: Path, repo_slug: str, issue_number: int) -> dict[str, Any]:
    payload = run_gh_json(
        repo_root,
        [
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo_slug,
            "--json",
            "number,title,body,url,state,labels,comments,updatedAt",
        ],
    )
    comments = [
        normalize_comment(item, "issue", f"Issue #{issue_number}")
        for item in connection_nodes(payload.get("comments"))
        if isinstance(item, dict)
    ]
    labels = []
    for label in connection_nodes(payload.get("labels")):
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
            if name:
                labels.append(name)
        elif isinstance(label, str) and label.strip():
            labels.append(label.strip())
    return {
        "number": payload.get("number"),
        "title": payload.get("title"),
        "body": payload.get("body"),
        "url": payload.get("url"),
        "state": payload.get("state"),
        "labels": labels,
        "updated_at": payload.get("updatedAt"),
        "comments": digest_comments(comments),
    }


def gather_discussion_evidence(repo_root: Path, repo_slug: str, discussion_number: int) -> dict[str, Any]:
    owner, name = parse_owner_repo(repo_slug)
    query = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      number
      title
      body
      url
      updatedAt
      category {
        name
      }
      comments(last: 10) {
        nodes {
          author {
            login
          }
          body
          url
          createdAt
          updatedAt
        }
      }
    }
  }
}
"""
    payload = run_gh_json(
        repo_root,
        [
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={discussion_number}",
            "-f",
            f"query={query}",
        ],
    )
    discussion = (((payload.get("data") or {}).get("repository") or {}).get("discussion") or {})
    comments = [
        normalize_comment(item, "discussion", f"Discussion #{discussion_number}")
        for item in connection_nodes(discussion.get("comments"))
        if isinstance(item, dict)
    ]
    return {
        "number": discussion.get("number"),
        "title": discussion.get("title"),
        "body": discussion.get("body"),
        "url": discussion.get("url"),
        "updated_at": discussion.get("updatedAt"),
        "category": (discussion.get("category") or {}).get("name"),
        "comments": digest_comments(comments),
    }


def build_artifact_entry(
    *,
    artifact_type: str,
    identifier: str,
    title: str | None,
    body: str | None,
    url: str | None,
    comment_digests: list[dict[str, Any]],
    changed_paths: list[str],
    public_doc_paths: list[str],
    repo_profile: dict[str, Any],
) -> dict[str, Any]:
    comment_text = " ".join(str(item.get("body_excerpt") or "") for item in comment_digests)
    packet_hints = packet_hints_from_paths(changed_paths, public_doc_paths, repo_profile)
    packet_hints.update(packet_hints_from_text(" ".join([title or "", body or "", comment_text])))
    return {
        "artifact_type": artifact_type,
        "identifier": identifier,
        "url": url,
        "title": title,
        "changed_paths": changed_paths,
        "packet_hints": sorted(packet_hints),
        "summary": build_artifact_summary(title, body, comment_digests),
        "comment_digests": comment_digests,
    }


def collect_github_evidence(
    repo_root: Path,
    identity: dict[str, str],
    relevant_ref: dict[str, Any],
    public_doc_paths: list[str],
    repo_profile: dict[str, Any],
) -> dict[str, Any]:
    required = bool(relevant_ref.get("requires_github_evidence"))
    evidence = {
        "enabled": False,
        "auth_policy": GITHUB_AUTH_POLICY,
        "required": required,
        "auth_status": None,
        "repo_slug": identity["repo_slug"] or None,
        "primary_pr": None,
        "related_issues": [],
        "related_discussions": [],
        "artifacts": [],
        "comment_digests": [],
        "evidence_urls": [],
        "fetch_errors": [],
        "digest": None,
    }
    if not identity["repo_slug"]:
        if required:
            raise SystemExit(
                "[ERROR] The selected relevant ref requires GitHub evidence, but the repository slug could not be inferred."
            )
        return evidence

    if not evidence["required"]:
        return evidence

    evidence["auth_status"] = require_gh_auth(repo_root)
    pr_number = relevant_ref.get("primary_pr_number")
    if not pr_number:
        raise SystemExit("[ERROR] The selected relevant ref requires GitHub evidence, but no primary PR number was available.")

    pr = gather_pr_evidence(repo_root, identity["repo_slug"], int(pr_number))
    evidence["enabled"] = True
    evidence["primary_pr"] = pr
    if pr.get("url"):
        evidence["evidence_urls"].append(pr.get("url"))

    pr_files = [entry.get("path") for entry in pr.get("files", []) if entry.get("path")]
    pr_artifact = build_artifact_entry(
        artifact_type="pull_request",
        identifier=f"PR #{pr.get('number')}",
        title=pr.get("title"),
        body=pr.get("body"),
        url=pr.get("url"),
        comment_digests=pr.get("comments", []),
        changed_paths=pr_files,
        public_doc_paths=public_doc_paths,
        repo_profile=repo_profile,
    )
    evidence["artifacts"].append(pr_artifact)
    evidence["comment_digests"].extend(pr_artifact["comment_digests"])

    discussion_refs = collect_discussion_refs(
        " ".join(
            filter(
                None,
                [str(pr.get("body") or "")] + [str(item.get("body_excerpt") or "") for item in pr.get("comments", [])],
            )
        ),
        identity["repo_slug"],
    )
    for linked_issue in connection_nodes(pr.get("linked_issues")):
        if not isinstance(linked_issue, dict):
            continue
        issue_number = linked_issue.get("number")
        if issue_number is None:
            continue
        issue = gather_issue_evidence(repo_root, identity["repo_slug"], int(issue_number))
        evidence["related_issues"].append(issue)
        if issue.get("url"):
            evidence["evidence_urls"].append(issue.get("url"))
        issue_artifact = build_artifact_entry(
            artifact_type="issue",
            identifier=f"Issue #{issue.get('number')}",
            title=issue.get("title"),
            body=issue.get("body"),
            url=issue.get("url"),
            comment_digests=issue.get("comments", []),
            changed_paths=[],
            public_doc_paths=public_doc_paths,
            repo_profile=repo_profile,
        )
        evidence["artifacts"].append(issue_artifact)
        evidence["comment_digests"].extend(issue_artifact["comment_digests"])
        discussion_refs.extend(
            collect_discussion_refs(
                " ".join(
                    filter(
                        None,
                        [str(issue.get("body") or "")] + [str(item.get("body_excerpt") or "") for item in issue.get("comments", [])],
                    )
                ),
                identity["repo_slug"],
            )
        )

    for ref in stable_dedupe(discussion_refs):
        try:
            discussion = gather_discussion_evidence(repo_root, identity["repo_slug"], int(ref["number"]))
        except RuntimeError as exc:
            evidence["fetch_errors"].append(
                {
                    "artifact_type": "discussion",
                    "number": ref["number"],
                    "url": ref["url"],
                    "message": str(exc),
                }
            )
            continue
        evidence["related_discussions"].append(discussion)
        if discussion.get("url"):
            evidence["evidence_urls"].append(discussion.get("url"))
        discussion_artifact = build_artifact_entry(
            artifact_type="discussion",
            identifier=f"Discussion #{discussion.get('number')}",
            title=discussion.get("title"),
            body=discussion.get("body"),
            url=discussion.get("url"),
            comment_digests=discussion.get("comments", []),
            changed_paths=[],
            public_doc_paths=public_doc_paths,
            repo_profile=repo_profile,
        )
        evidence["artifacts"].append(discussion_artifact)
        evidence["comment_digests"].extend(discussion_artifact["comment_digests"])

    evidence["comment_digests"] = stable_dedupe(evidence["comment_digests"])
    evidence["evidence_urls"] = [url for url in stable_dedupe([url for url in evidence["evidence_urls"] if url])]
    evidence["digest"] = "sha256:" + sha256_text(
        json.dumps(
            {
                "primary_pr": evidence["primary_pr"],
                "related_issues": evidence["related_issues"],
                "related_discussions": evidence["related_discussions"],
                "artifacts": evidence["artifacts"],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
    )
    return evidence


def build_evidence_summary(github_evidence: dict[str, Any]) -> dict[str, Any]:
    packet_signals: dict[str, list[str]] = {
        "claims_packet": [],
        "reporting_packet": [],
        "workflow_packet": [],
        "forms_batch_packet": [],
    }
    for artifact in github_evidence.get("artifacts", []):
        message = f"{artifact.get('identifier')}: {artifact.get('summary')}".strip()
        for packet_name in artifact.get("packet_hints", []):
            if packet_name in packet_signals and message not in packet_signals[packet_name]:
                packet_signals[packet_name].append(message)
    return {
        "packet_signals": packet_signals,
        "artifact_count": len(github_evidence.get("artifacts", [])),
        "comment_count": len(github_evidence.get("comment_digests", [])),
        "urls": github_evidence.get("evidence_urls", []),
    }


def build_packet_candidates(
    audit_target_paths: list[str],
    public_doc_paths: list[str],
    audit_mode: str,
    github_summary: dict[str, Any],
    repo_profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    review_docs = packet_review_docs(public_doc_paths, repo_profile)
    packets: dict[str, dict[str, Any]] = {
        "claims_packet": {
            "packet_id": "claims_packet",
            "packet_kind": "focused",
            "review_docs": review_docs["claims_packet"],
            "changed_paths": [],
            "direct_doc_changes": [],
            "direct_source_changes": [],
            "activation_reasons": [],
            "active": False,
        },
        "reporting_packet": {
            "packet_id": "reporting_packet",
            "packet_kind": "focused",
            "review_docs": review_docs["reporting_packet"],
            "changed_paths": [],
            "direct_doc_changes": [],
            "direct_source_changes": [],
            "activation_reasons": [],
            "active": False,
        },
        "workflow_packet": {
            "packet_id": "workflow_packet",
            "packet_kind": "focused",
            "review_docs": review_docs["workflow_packet"],
            "changed_paths": [],
            "direct_doc_changes": [],
            "direct_source_changes": [],
            "activation_reasons": [],
            "active": False,
        },
        "forms_batch_packet": {
            "packet_id": "forms_batch_packet",
            "packet_kind": "batch",
            "review_docs": review_docs["forms_batch_packet"],
            "changed_paths": [],
            "direct_doc_changes": [],
            "direct_source_changes": [],
            "activation_reasons": [],
            "active": False,
        },
    }

    for relpath in audit_target_paths:
        packet_names = packet_for_path(relpath, public_doc_paths, repo_profile)
        for packet_name in packet_names:
            packet = packets[packet_name]
            packet["active"] = True
            packet["changed_paths"].append(relpath)
            bucket = "direct_doc_changes" if relpath in public_doc_paths else "direct_source_changes"
            packet[bucket].append(relpath)

    if packets["reporting_packet"]["active"] and packets["forms_batch_packet"]["review_docs"]:
        packets["forms_batch_packet"]["active"] = True
        packets["forms_batch_packet"]["activation_reasons"].append(
            "reporting surfaces changed; related public issue forms should be reviewed."
        )

    for packet_name, packet in packets.items():
        remote_signals = github_summary.get("packet_signals", {}).get(packet_name, [])
        if remote_signals:
            packet["active"] = True
            packet["activation_reasons"].append(
                "GitHub evidence references this docs surface: " + "; ".join(remote_signals[:2])
            )
        if packet["active"] and audit_mode == "full":
            packet["activation_reasons"].append("full audit requested or auto-fallback required.")
        if packet["direct_doc_changes"]:
            packet["activation_reasons"].append(
                "changed public docs: " + ", ".join(packet["direct_doc_changes"][:4])
            )
        if packet["direct_source_changes"]:
            packet["activation_reasons"].append(
                "changed runtime or workflow surfaces: " + ", ".join(packet["direct_source_changes"][:4])
            )
        if not packet["activation_reasons"] and packet["active"]:
            packet["activation_reasons"].append("packet activated by public-doc ownership rules.")
        packet["changed_paths"] = sorted(dict.fromkeys(packet["changed_paths"]))
        packet["direct_doc_changes"] = sorted(dict.fromkeys(packet["direct_doc_changes"]))
        packet["direct_source_changes"] = sorted(dict.fromkeys(packet["direct_source_changes"]))
        packet["review_docs"] = sorted(dict.fromkeys(packet["review_docs"]))

    return packets


def build_context_fingerprint(
    head_commit: str,
    baseline: dict[str, Any],
    relevant_ref: dict[str, Any],
    audit_target_paths: list[str],
    public_doc_inventory: dict[str, dict[str, Any]],
    github_evidence_digest: str | None,
) -> str:
    parts = [
        head_commit,
        baseline.get("mode", ""),
        baseline.get("base_commit") or "",
        relevant_ref.get("kind", ""),
        relevant_ref.get("base_commit") or "",
        relevant_ref.get("head_commit") or "",
        str(relevant_ref.get("primary_pr_number") or ""),
        github_evidence_digest or "",
    ]
    for relpath in sorted(audit_target_paths):
        parts.append(relpath)
    for relpath in sorted(public_doc_inventory):
        entry = public_doc_inventory[relpath]
        parts.append(relpath)
        parts.append(str(entry.get("sha256", "")))
    return "sha256:" + sha256_text("\n".join(parts))


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    profile_path = resolve_profile_path(args.profile, repo_root)
    repo_profile = load_repo_profile(profile_path)
    bindings = repo_profile_bindings(repo_profile)
    publish_path = normalize_path(bindings.get("publish_config_path") or "")
    identity = repo_identity(repo_root)
    state_file = (
        Path(args.state_file).resolve()
        if args.state_file
        else default_state_file(identity["repo_hash"], repo_profile)
    )
    head_commit = git_head_commit(repo_root)
    branch = git_branch(repo_root)
    public_doc_paths = collect_public_doc_paths(repo_root, repo_profile)
    public_doc_inventory = {
        relpath: summarize_file(repo_root, relpath, publish_config_path=publish_path)
        for relpath in public_doc_paths
    }

    baseline = build_baseline(repo_root, args, state_file, identity, head_commit, branch)
    relevant_ref, ref_candidates = select_relevant_ref(repo_root, identity, args, baseline, head_commit, branch)
    effective_base_commit = baseline.get("base_commit") or relevant_ref.get("base_commit")
    audit_mode = "full" if args.full or not effective_base_commit else "ref-range"

    status_paths = collect_status_paths(repo_root)
    diff_paths = collect_diff_paths(repo_root, effective_base_commit) if effective_base_commit else []
    raw_changed_paths = sorted(dict.fromkeys(diff_paths + status_paths))

    github_evidence = collect_github_evidence(repo_root, identity, relevant_ref, public_doc_paths, repo_profile)
    evidence_summary = build_evidence_summary(github_evidence)

    if audit_mode == "full":
        audit_target_paths = sorted(dict.fromkeys(public_doc_paths + raw_changed_paths))
        if not audit_target_paths:
            audit_target_paths = public_doc_paths[:]
    else:
        audit_target_paths = [
            path for path in raw_changed_paths if packet_for_path(path, public_doc_paths, repo_profile)
        ]

    unmapped_changed_paths = [
        path for path in raw_changed_paths if path not in audit_target_paths
    ]
    changed_path_summaries = {
        relpath: summarize_file(repo_root, relpath)
        for relpath in audit_target_paths
        if file_exists(repo_root, relpath)
    }

    setting_path = normalize_path(bindings.get("settings_source_path") or "")
    readme_path = normalize_path(bindings.get("primary_readme_path") or "README.md")
    settings = (
        parse_setting_defaults(read_text_file(repo_root, setting_path))
        if setting_path and file_exists(repo_root, setting_path)
        else {}
    )
    readme_settings = public_doc_inventory.get(readme_path, {}).get("settings_table", {})
    publish_info = public_doc_inventory.get(publish_path, {}).get("publish_configuration", {})

    packet_candidates = build_packet_candidates(
        audit_target_paths,
        public_doc_paths,
        audit_mode,
        evidence_summary,
        repo_profile,
    )
    active_packet_count = sum(1 for packet in packet_candidates.values() if packet["active"])
    doc_changes = sum(1 for path in audit_target_paths if path in public_doc_paths)
    code_changes = max(len(audit_target_paths) - doc_changes, 0)
    generated_count = sum(1 for path in audit_target_paths if is_generated_path(path))
    context_fingerprint = build_context_fingerprint(
        head_commit,
        baseline,
        relevant_ref,
        audit_target_paths,
        public_doc_inventory,
        github_evidence.get("digest"),
    )

    context = {
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "context_id": f"{SKILL_NAME}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": normalize_path(repo_root),
        "repo_name": identity["repo_name"],
        "repo_id": identity["repo_id"],
        "repo_hash": identity["repo_hash"],
        "remote_url": identity["remote_url"] or None,
        "repo_slug": identity["repo_slug"] or None,
        "branch": branch,
        "head_commit": head_commit,
        "repo_profile_name": repo_profile.get("name"),
        "repo_profile_path": profile_path.as_posix(),
        "repo_profile_summary": repo_profile.get("summary"),
        "repo_profile": repo_profile,
        "builder_compatibility": build_builder_compatibility(repo_profile),
        "state_file": normalize_path(state_file),
        "context_fingerprint": context_fingerprint,
        "authority_order": DEFAULT_AUTHORITY_ORDER,
        "stop_conditions": DEFAULT_STOP_CONDITIONS,
        "baseline": baseline,
        "relevant_ref": relevant_ref,
        "ref_candidates": ref_candidates,
        "effective_base_commit": effective_base_commit,
        "audit_mode": audit_mode,
        "git_changes": {
            "status_paths": status_paths,
            "diff_paths_since_base": diff_paths,
            "raw_changed_paths": raw_changed_paths,
        },
        "audit_target_paths": audit_target_paths,
        "unmapped_changed_paths": unmapped_changed_paths,
        "public_doc_paths": public_doc_paths,
        "public_doc_inventory": public_doc_inventory,
        "changed_path_summaries": changed_path_summaries,
        "settings": {
            "source_path": setting_path,
            "defaults": settings,
        },
        "readme": {
            "path": readme_path,
            "settings_table": readme_settings,
            "headings": public_doc_inventory.get(readme_path, {}).get("headings", []),
        },
        "publish_configuration": {
            "path": publish_path,
            "fields": publish_info,
        },
        "github_evidence_required": bool(github_evidence.get("required")),
        "github_evidence": github_evidence,
        "github_evidence_digest": github_evidence.get("digest"),
        "evidence_summary": evidence_summary,
        "packet_candidates": packet_candidates,
        "counts": {
            "changed_files": len(audit_target_paths),
            "task_packet_count": active_packet_count,
            "batch_count": 1 if packet_candidates["forms_batch_packet"]["active"] else 0,
            "active_packet_count": active_packet_count,
            "public_doc_count": len(public_doc_paths),
            "doc_changes": doc_changes,
            "code_changes": code_changes,
            "generated_changes": generated_count,
            "github_artifact_count": evidence_summary.get("artifact_count", 0),
            "github_comment_count": evidence_summary.get("comment_count", 0),
        },
        "override_signals": {
            "high_churn": len(audit_target_paths) > 20,
            "multi_group_core_files": sum(
                1 for name, packet in packet_candidates.items()
                if name != "forms_batch_packet" and packet["direct_source_changes"]
            ) >= 2,
            "generated_not_majority": generated_count > 0 and generated_count < len(audit_target_paths),
            "github_evidence_scattered": evidence_summary.get("artifact_count", 0) >= 3,
        },
        "deterministic_apply_boundaries": {
            "allowed": [
                "settings table default sync",
                "relative link fix",
                "simple public doc list or reference sync",
                "issue-template metadata sync",
            ],
            "blocked": [
                "release status claim rewrite",
                "investigation conclusion rewrite",
                "evidence-strength or experiment-status prose rewrite",
            ],
        },
        "notes": [
            "Collector separates saved-marker reuse from relevant-ref selection so markerless runs can still narrow to a defensible change unit.",
            f"GitHub evidence policy is {GITHUB_AUTH_POLICY}.",
        ],
    }

    if baseline.get("fallback_reason"):
        context["notes"].append(f"Saved baseline was unavailable: {baseline['fallback_reason']}.")
    if relevant_ref.get("selection_reason"):
        context["notes"].append("Selected relevant ref: " + relevant_ref["selection_reason"])
    if github_evidence.get("enabled"):
        context["notes"].append(
            f"Collected GitHub evidence from {evidence_summary.get('artifact_count', 0)} artifact(s) tied to the selected change unit."
        )
    if unmapped_changed_paths:
        context["notes"].append(
            "Some changed paths were outside current public-doc ownership rules: "
            + ", ".join(unmapped_changed_paths[:6])
        )

    if context["builder_compatibility"].get("status") != "current":
        print(format_runtime_warning(context["builder_compatibility"]), file=sys.stderr)
    write_json(Path(args.output).resolve(), context)
    print(json.dumps(context, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
