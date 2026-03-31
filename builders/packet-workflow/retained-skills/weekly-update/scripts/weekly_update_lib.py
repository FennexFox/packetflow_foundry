#!/usr/bin/env python3
"""Shared helpers for the weekly-update skill."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode


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

SKILL_NAME = "weekly-update"
SKILL_VERSION = "0.1.0"
WORKFLOW_FAMILY = "repo-audit"
ARCHETYPE = "plan-validate-apply"
ORCHESTRATOR_PROFILE = "standard"
PRIMARY_GOAL = "Produce a concise, evidence-based weekly update from repository and directly related GitHub evidence."
OUTPUT_SECTIONS = ["PRs", "Rollouts", "Incidents", "Reviews", "Blockers / Risks", "Evidence reviewed"]
PACKET_NAMES = ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"]
PACKET_FILES = ["global_packet.json", *(f"{name}.json" for name in PACKET_NAMES)]
RUNTIME_PACKET_FILES = ["orchestrator.json", *PACKET_FILES]
DEFAULT_PAGE_SIZE = 100
MAX_GH_PAGES = 20
DECISION_READY_PACKETS = True
WORKER_RETURN_CONTRACT = "classification-oriented"
WORKER_OUTPUT_SHAPE = "hierarchical"
AUTHORITY_ORDER = [
    "published GitHub releases and linked release issues",
    "merged PR diffs and git history",
    "directly related review, issue, and workflow-run evidence",
    "structured workflow packets",
    "local last-success state as baseline only",
]
STOP_CONDITIONS = [
    "low confidence",
    "stale snapshot or stale structured context",
    "GitHub evidence is required but gh auth is invalid",
    "ambiguous incident versus blocker classification",
    "missing reporting window baseline when reuse is required",
]
REVIEW_MODE_OVERRIDES = [
    "reporting window includes more than 8 merged PRs or more than 15 relevant issues",
    "release, incident, and review surfaces are all active in the same window",
    "nested branch lineage or workflow-run failures materially expand the evidence graph",
]
ACTUAL_INCIDENT = "actual_incident"
BLOCKER_OR_RISK = "blocker_or_risk"
ARTIFACT_ONLY = "artifact_only"
IGNORE = "ignore"
PROPOSED_CLASSIFICATIONS = [ACTUAL_INCIDENT, BLOCKER_OR_RISK, ARTIFACT_ONLY, IGNORE]
CONFIDENCE_VALUES = ["high", "medium", "low"]
RAW_REREAD_REASONS = [
    "conflicting_signals",
    "missing_failure_evidence",
    "missing_materiality_evidence",
    "schema_mismatch",
    "insufficient_excerpt_quality",
]
COMMON_PATH_CONTRACT = {
    "local_adjudication_basis": [
        "global_packet.json",
        "mapping_packet.json",
        "one focused packet needed for the current decision",
    ],
    "raw_reread_exception_reasons": RAW_REREAD_REASONS,
    "regression_rule": "Canonical common path should not require broad raw rereads.",
}
PACKET_METRIC_FIELDS = [
    "packet_count",
    "packet_size_bytes",
    "largest_packet_bytes",
    "largest_two_packets_bytes",
    "estimated_local_only_tokens",
    "estimated_packet_tokens",
    "estimated_delegation_savings",
]
CANDIDATE_REQUIRED_FIELDS = [
    "candidate_id",
    "source_type",
    "source_id",
    "title",
    "summary",
    "proposed_classification",
    "classification_rationale",
    "materiality_evidence",
    "concrete_failure_evidence",
    "open_ambiguity",
    "confidence",
    "source_refs",
    "excerpt_bundle",
    "raw_reread_reason",
    "packet_membership",
    "risk",
    "recommended_next_step",
    "tests_or_checks",
]
WORKER_FOOTER_FIELDS = [
    "packet_ids",
    "candidate_ids",
    "primary_outcome",
    "overall_confidence",
    "coverage_gaps",
    "overall_risk",
]
PLAN_REQUIRED_FIELDS = [
    "context_id",
    "context_fingerprint",
    "overall_confidence",
    "stop_reasons",
    "allow_marker_update",
    "sections",
]
PREFERRED_WORKER_FAMILIES = {
    "context_findings": ["repo_mapper", "docs_verifier"],
    "candidate_producers": ["evidence_summarizer", "large_diff_auditor", "log_triager"],
    "verifiers": ["docs_verifier"],
}
PACKET_WORKER_MAP = {
    "mapping_packet": ["repo_mapper"],
    "changes_packet": ["large_diff_auditor"],
    "incidents_packet": ["log_triager"],
    "risks_packet": ["evidence_summarizer"],
}
WORKER_SELECTION_GUIDANCE = {
    "repo_mapper": "Use for reporting-window grounding, release linkage, PR lineage, candidate inventory, and packet membership checks.",
    "docs_verifier": "Use only when tracked docs or runbooks are needed to resolve conflicting packet evidence.",
    "evidence_summarizer": "Use for the most narrative-heavy packet or slice when issues, release notes, or review discussion need adjudication-ready compression.",
    "large_diff_auditor": "Use for shipped-change, behavior-change, config-change, and review-followup extraction from the changes packet.",
    "log_triager": "Use for incident, workflow-failure, and blocker-versus-incident evidence in the incidents or risks packet.",
}
WORKER_FAMILY_ORDER = ["context_findings", "candidate_producers", "verifiers"]
DEFAULT_STATE_NAMESPACE = SKILL_NAME
DEFAULT_REVIEW_ACK_MARKERS = ["phase=ack"]
DEFAULT_REVIEW_COMPLETE_MARKERS = ["phase=complete"]
DEFAULT_RELEASE_TITLE_REGEX = r"^\[Release\]\s*(?P<tag>v[0-9A-Za-z._-]+)"
DEFAULT_PRIORITY_MARKERS_REGEX = r"\[(?:P[0-3]|medium|high|low)\]"
CANDIDATE_FIELD_BUNDLES = [
    {
        "name": "identity",
        "description": "Stable candidate identity and source information.",
        "required": True,
        "fields": ["candidate_id", "source_type", "source_id", "title"],
    },
    {
        "name": "proposal",
        "description": "Proposal-grade summary and classification rationale for local adjudication.",
        "required": True,
        "fields": ["summary", "proposed_classification", "classification_rationale"],
    },
    {
        "name": "evidence",
        "description": "Decision-ready supporting evidence, references, and excerpt bundle.",
        "required": True,
        "fields": ["materiality_evidence", "concrete_failure_evidence", "source_refs", "excerpt_bundle"],
    },
    {
        "name": "adjudication",
        "description": "Ambiguity, confidence, reread control, and packet membership for local xHigh adjudication.",
        "required": True,
        "fields": ["open_ambiguity", "confidence", "raw_reread_reason", "packet_membership"],
    },
    {
        "name": "follow_up",
        "description": "Candidate-local risk, next step, and checks.",
        "required": True,
        "fields": ["risk", "recommended_next_step", "tests_or_checks"],
    },
]
DOMAIN_OVERLAY = {
    "proposal_enum_values": PROPOSED_CLASSIFICATIONS,
    "reference_only_candidate_values": [ARTIFACT_ONLY],
    "output_inclusion_rules": {
        "standalone": [ACTUAL_INCIDENT, BLOCKER_OR_RISK],
        "reference_only": [ARTIFACT_ONLY],
        "excluded": [IGNORE],
    },
}
FAILED_WORKFLOW_CONCLUSIONS = {"action_required", "failure", "startup_failure", "timed_out"}
NEUTRAL_WORKFLOW_CONCLUSIONS = {"", "cancelled", "neutral", "skipped", "success"}
TITLE_PREFIX_RE = re.compile(r"^\[(?P<prefix>[^\]]+)\]\s*")
DEFAULT_RELEASE_TITLE_RE = re.compile(DEFAULT_RELEASE_TITLE_REGEX)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*-\s+(?P<value>.+?)\s*$", re.MULTILINE)
ISSUE_REF_RE = re.compile(r"(?<![A-Za-z0-9])#(?P<number>\d+)\b")
DEFAULT_REVIEW_ACK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in DEFAULT_REVIEW_ACK_MARKERS
]
DEFAULT_REVIEW_COMPLETE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in DEFAULT_REVIEW_COMPLETE_MARKERS
]
DEFAULT_PRIORITY_MARKER_RE = re.compile(DEFAULT_PRIORITY_MARKERS_REGEX, re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
CONCRETE_FAILURE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\banomaly\b",
        r"\bblocked\b",
        r"\bbroken\b",
        r"\bcrash(?:ed|es)?\b",
        r"\berror\b",
        r"\bfail(?:ed|s|ure)?\b",
        r"\bincorrect\b",
        r"\bregression\b",
        r"\brepro(?:duced|ducible|duce)?\b",
        r"\bstall(?:ed|ing)?\b",
        r"\bstuck\b",
        r"\bwrong\b",
    ]
]
STRONG_EVIDENCE_FAILURE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [r"\bactive distress\b", r"\berror\b", r"\bfail(?:ed|s|ure)?\b", r"\bregression\b"]
]
PLANNING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [r"\bnext steps\b", r"\bpending\b", r"\bwaiting for\b", r"\bcomparison summary\b"]
]
GENERIC_REVIEW_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [r"^summary by codex", r"^automated review", r"^useful\?\s+react with"]
]
GATE_IMPACT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [r"\bblock(?:er|ing)?\b", r"\bbefore merge\b", r"\bbreak(?:s|ing)?\b", r"\bfail(?:ed|s|ure)?\b", r"\brelease gate\b", r"\bregression\b", r"\bwrong\b"]
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso8601(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run_command(args: list[str], cwd: Path, *, check: bool = True) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{args[0]} not found") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"{args[0]} failed"
        raise RuntimeError(detail)
    return result.stdout


def run_git(repo_root: Path, args: list[str], *, check: bool = True) -> str:
    return run_command(["git", *args], repo_root, check=check)


def run_gh_json(repo_root: Path, args: list[str]) -> Any:
    text = run_command(["gh", *args], repo_root).strip()
    return json.loads(text) if text else {}


def build_api_path(endpoint: str, params: dict[str, Any] | None = None) -> str:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
    return f"{endpoint}?{query}" if query else endpoint


def truncation_gap(label: str, *, max_pages: int = MAX_GH_PAGES) -> str:
    return f"{label} may be truncated after {max_pages} pages."


def page_stop_on_last_timestamp(page_items: list[dict[str, Any]], *, key: str, window_start: datetime) -> bool:
    if not page_items:
        return True
    last_value = str(page_items[-1].get(key) or "")
    last_timestamp = parse_iso8601(last_value)
    return bool(last_timestamp and last_timestamp < window_start)


def paginate_gh_api(
    repo_root: Path,
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    collection_key: str | None = None,
    max_pages: int = MAX_GH_PAGES,
    stop_when: Any | None = None,
    label: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    base_params = {"per_page": DEFAULT_PAGE_SIZE}
    base_params.update(params or {})
    truncated = False
    for page in range(1, max_pages + 1):
        payload = run_gh_json(repo_root, ["api", build_api_path(endpoint, {**base_params, "page": page})])
        page_items = payload.get(collection_key) if collection_key and isinstance(payload, dict) else payload
        if not isinstance(page_items, list) or not page_items:
            break
        items.extend(page_items)
        if stop_when and stop_when(page_items):
            break
        if len(page_items) < int(base_params["per_page"]):
            break
        if page == max_pages:
            truncated = True
    if truncated:
        warnings.append(truncation_gap(label or endpoint, max_pages=max_pages))
    return items, warnings


def resolve_repo_root(repo_root: str) -> Path:
    requested = Path(repo_root).resolve()
    if not requested.exists():
        raise SystemExit(f"[ERROR] Missing repo root: {requested}")
    return Path(run_git(requested, ["rev-parse", "--show-toplevel"]).strip()).resolve()


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


def resolve_profile_path(profile_path: str | None = None, repo_root: Path | None = None) -> Path:
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
        if resolved.exists():
            return resolved
    searched = ", ".join(path.as_posix() for path in resolved_candidates)
    raise SystemExit(f"[ERROR] Missing repo profile: {searched}")


def load_repo_profile(path: Path) -> dict[str, Any]:
    payload = load_json(path)
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


def compute_repo_hash(repo_root: Path) -> str:
    return hashlib.sha256(str(repo_root).lower().encode("utf-8")).hexdigest()[:16]


def default_state_file(repo_hash: str, *, namespace: str = DEFAULT_STATE_NAMESPACE) -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    safe_namespace = str(namespace or DEFAULT_STATE_NAMESPACE).strip() or DEFAULT_STATE_NAMESPACE
    return home / ".codex" / "state" / safe_namespace / f"{repo_hash}.json"


def weekly_update_profile_data(repo_profile: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(repo_profile, dict):
        return {}
    extra = repo_profile.get("extra")
    if not isinstance(extra, dict):
        return {}
    payload = extra.get("weekly_update")
    return dict(payload) if isinstance(payload, dict) else {}


def string_list_or_default(value: Any, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return normalized or list(default)


def weekly_update_runtime_settings(repo_profile: dict[str, Any] | None) -> dict[str, Any]:
    payload = weekly_update_profile_data(repo_profile)
    review_markers = payload.get("review_markers")
    review_markers = review_markers if isinstance(review_markers, dict) else {}
    release_issue = payload.get("release_issue")
    release_issue = release_issue if isinstance(release_issue, dict) else {}
    priority_markers = payload.get("priority_markers")
    priority_markers = priority_markers if isinstance(priority_markers, dict) else {}
    state = payload.get("state")
    state = state if isinstance(state, dict) else {}
    release_title_regex = str(
        release_issue.get("title_regex") or DEFAULT_RELEASE_TITLE_REGEX
    ).strip() or DEFAULT_RELEASE_TITLE_REGEX
    priority_markers_regex = str(
        priority_markers.get("regex") or DEFAULT_PRIORITY_MARKERS_REGEX
    ).strip() or DEFAULT_PRIORITY_MARKERS_REGEX
    ack_markers = string_list_or_default(
        review_markers.get("acknowledged"), DEFAULT_REVIEW_ACK_MARKERS
    )
    resolved_markers = string_list_or_default(
        review_markers.get("resolved"), DEFAULT_REVIEW_COMPLETE_MARKERS
    )
    state_namespace = str(
        state.get("namespace") or DEFAULT_STATE_NAMESPACE
    ).strip() or DEFAULT_STATE_NAMESPACE
    return {
        "state_namespace": state_namespace,
        "release_title_regex": release_title_regex,
        "release_title_re": re.compile(release_title_regex),
        "review_ack_markers": ack_markers,
        "review_ack_patterns": [
            re.compile(pattern, re.IGNORECASE) for pattern in ack_markers
        ],
        "review_complete_markers": resolved_markers,
        "review_complete_patterns": [
            re.compile(pattern, re.IGNORECASE) for pattern in resolved_markers
        ],
        "priority_markers_regex": priority_markers_regex,
        "priority_marker_re": re.compile(priority_markers_regex, re.IGNORECASE),
    }


def load_state_marker(state_file: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not state_file.exists():
        return None, []
    try:
        payload = load_json(state_file)
    except Exception as exc:  # noqa: BLE001
        return None, [f"State marker is unreadable: {exc}"]
    if not payload.get("window_end_utc") and not payload.get("completed_at_utc"):
        return None, ["State marker is missing `window_end_utc` and `completed_at_utc`."]
    return payload, []


def select_reporting_window(*, now_utc: datetime, window_days: int, state_marker: dict[str, Any] | None) -> dict[str, Any]:
    marker_end = parse_iso8601(str((state_marker or {}).get("window_end_utc") or (state_marker or {}).get("completed_at_utc") or ""))
    if marker_end is not None and marker_end < now_utc:
        start_utc = marker_end
        source = "state_marker"
        marker_reused = True
    else:
        start_utc = now_utc - timedelta(days=window_days)
        source = "last_7_days" if window_days == 7 else "explicit_window_days"
        marker_reused = False
    return {
        "start_utc": isoformat_utc(start_utc),
        "end_utc": isoformat_utc(now_utc),
        "source": source,
        "window_days": window_days,
        "marker_reused": marker_reused,
        "span_hours": round((now_utc - start_utc).total_seconds() / 3600, 2),
    }


def sha256_json(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def estimate_tokens_from_bytes(byte_count: int) -> int:
    if byte_count <= 0:
        return 0
    return max(1, int(round(byte_count / 4.0)))


def normalize_text(text: str) -> str:
    cleaned = MARKDOWN_IMAGE_RE.sub(" ", text or "")
    cleaned = MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = MARKDOWN_CODE_RE.sub(r"\1", cleaned)
    cleaned = HTML_TAG_RE.sub(" ", cleaned)
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def first_meaningful_line(text: str) -> str:
    for raw_line in (text or "").splitlines():
        line = normalize_text(raw_line).strip(" -*")
        if line and not line.lower().startswith("useful? react with"):
            return line
    return ""


def short_markdown_summary(text: str, *, fallback: str, limit: int = 220) -> str:
    candidate = first_meaningful_line(text) or normalize_text(text) or fallback
    return candidate if len(candidate) <= limit else candidate[: limit - 3].rstrip() + "..."


def normalized_timestamp(value: Any) -> str:
    parsed = parse_iso8601(str(value or ""))
    return isoformat_utc(parsed) if parsed is not None else str(value or "")


def stable_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def empty_plan_sections() -> dict[str, list[Any]]:
    return {section: [] for section in OUTPUT_SECTIONS}


def extract_markdown_sections(markdown: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(markdown or ""))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1).strip().lower()] = markdown[start:end].strip()
    return sections


def extract_section_bullets(markdown: str, headings: Iterable[str]) -> list[str]:
    sections = extract_markdown_sections(markdown)
    bullets: list[str] = []
    for heading in headings:
        section = sections.get(heading.strip().lower(), "")
        bullets.extend(normalize_text(match.group("value")) for match in BULLET_RE.finditer(section))
    return [bullet for bullet in bullets if bullet]


def extract_issue_numbers_from_text(text: str) -> list[int]:
    return sorted({int(match.group("number")) for match in ISSUE_REF_RE.finditer(text or "")})


def classify_changed_paths(paths: Iterable[str]) -> dict[str, list[str]]:
    groups = {"runtime": [], "automation": [], "docs": [], "tests": [], "config": [], "other": []}
    for raw_path in paths:
        path = str(raw_path).replace("\\", "/").strip()
        lower = path.lower()
        if not path:
            continue
        if "/tests/" in lower or lower.endswith(("_test.py", ".tests.cs", ".spec.ts")):
            groups["tests"].append(path)
        elif lower.startswith(".github/scripts/") or lower.startswith(".github/workflows/"):
            groups["automation"].append(path)
        elif lower.endswith(".md"):
            groups["docs"].append(path)
        elif lower.endswith((".json", ".toml", ".xml", ".yml", ".yaml", ".csproj", ".props", ".targets")):
            groups["config"].append(path)
        elif lower.endswith((".cs", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java")):
            groups["runtime"].append(path)
        else:
            groups["other"].append(path)
    return groups


def title_prefix(title: str) -> str:
    match = TITLE_PREFIX_RE.match(title.strip())
    return match.group("prefix").strip().lower() if match else ""


def extract_release_tag(
    title: str, *, release_title_re: re.Pattern[str] | None = None
) -> str | None:
    match = (release_title_re or DEFAULT_RELEASE_TITLE_RE).match(title.strip())
    return match.group("tag") if match else None


def label_names(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels") or []
    values: list[str] = []
    for label in labels:
        raw = label if isinstance(label, str) else label.get("name")
        value = str(raw or "").strip().lower()
        if value:
            values.append(value)
    return sorted(set(values))


def window_contains(raw_timestamp: str | None, window_start: datetime, window_end: datetime) -> bool:
    parsed = parse_iso8601(raw_timestamp)
    return bool(parsed and window_start <= parsed <= window_end)


def compute_materiality_reasons(
    item: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
    created_key: str = "createdAt",
    updated_key: str = "updatedAt",
    merged_key: str | None = None,
    linked_from_pr: bool = False,
    matched_release: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if window_contains(str(item.get(created_key) or ""), window_start, window_end):
        reasons.append("created_in_window")
    if window_contains(str(item.get(updated_key) or ""), window_start, window_end):
        reasons.append("updated_in_window")
    if merged_key and window_contains(str(item.get(merged_key) or ""), window_start, window_end):
        reasons.append("merged_in_window")
    if linked_from_pr:
        reasons.append("linked_from_top_level_pr")
    if matched_release:
        reasons.append("matched_active_release")
    return reasons


def has_any_pattern(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    normalized = normalize_text(text).lower()
    return any(pattern.search(normalized) for pattern in patterns)


def canonical_ref(kind: str, ref: str, url: str | None = None) -> dict[str, str]:
    payload = {"kind": kind, "ref": ref}
    if url:
        payload["url"] = url
    return payload


def make_excerpt(text: str | None, *, source_ref: str, source_type: str, why_selected: str) -> dict[str, str] | None:
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    return {"text": normalized, "source_ref": source_ref, "source_type": source_type, "why_selected": why_selected}


def excerpt_bundle(*, failure_text: str | None, materiality_text: str | None, ambiguity_text: str | None, source_ref: str, source_type: str) -> dict[str, Any]:
    return {
        "failure_excerpt": make_excerpt(failure_text, source_ref=source_ref, source_type=source_type, why_selected="Most direct failure or regression excerpt."),
        "materiality_excerpt": make_excerpt(materiality_text, source_ref=source_ref, source_type=source_type, why_selected="Most direct weekly materiality excerpt."),
        "ambiguity_excerpt": make_excerpt(ambiguity_text, source_ref=source_ref, source_type=source_type, why_selected="Most direct remaining ambiguity excerpt."),
    }


def confidence_from_signals(*, materiality_present: bool, failure_present: bool, raw_reread_reason: str | None, open_ambiguity: str) -> str:
    if raw_reread_reason:
        return "low"
    if materiality_present and (failure_present or not open_ambiguity.strip()):
        return "high"
    if materiality_present:
        return "medium"
    return "low"


def metadata_excerpt(created_at: str | None, updated_at: str | None, merged_at: str | None = None) -> str:
    parts: list[str] = []
    if merged_at:
        parts.append(f"Merged at {merged_at}.")
    if created_at:
        parts.append(f"Created at {created_at}.")
    if updated_at and updated_at != created_at:
        parts.append(f"Updated at {updated_at}.")
    return " ".join(parts)


def verify_gh_auth(repo_root: Path) -> None:
    try:
        run_command(["gh", "auth", "status"], repo_root)
    except RuntimeError as exc:
        raise SystemExit(f"[ERROR] GitHub evidence is required but gh auth is invalid: {exc}") from exc


def get_repo_metadata(repo_root: Path) -> dict[str, str]:
    payload = run_gh_json(repo_root, ["repo", "view", "--json", "nameWithOwner,defaultBranchRef,url"])
    repo_slug = str(payload.get("nameWithOwner") or "").strip()
    default_branch = str((payload.get("defaultBranchRef") or {}).get("name") or "").strip()
    repo_url = str(payload.get("url") or "").strip()
    if not repo_slug or not default_branch:
        raise SystemExit("[ERROR] Unable to resolve repository slug or default branch from gh.")
    return {"repo_slug": repo_slug, "default_branch": default_branch, "repo_url": repo_url}


def get_branch_state(repo_root: Path) -> dict[str, str]:
    return {
        "current_branch": run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "head_sha": run_git(repo_root, ["rev-parse", "HEAD"]).strip(),
    }


def list_releases(repo_root: Path, repo_slug: str, *, window_start: datetime, window_end: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    payload, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/releases",
        stop_when=lambda page_items: page_stop_on_last_timestamp(page_items, key="published_at", window_start=window_start),
        label="releases",
    )
    releases: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if item.get("draft") or not item.get("published_at"):
            continue
        published_at = parse_iso8601(str(item.get("published_at") or ""))
        if published_at and window_start <= published_at <= window_end:
            releases.append({
                "tag_name": str(item.get("tag_name") or ""),
                "name": str(item.get("name") or ""),
                "url": str(item.get("html_url") or ""),
                "published_at": isoformat_utc(published_at),
                "body": str(item.get("body") or ""),
            })
    return sorted(releases, key=lambda item: item["published_at"]), warnings


def list_issues(repo_root: Path, repo_slug: str) -> tuple[list[dict[str, Any]], list[str]]:
    payload, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/issues",
        params={"state": "all", "sort": "updated", "direction": "desc"},
        label="issues",
    )
    issues: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if item.get("pull_request"):
            continue
        issues.append({
            "number": int(item.get("number") or 0),
            "title": str(item.get("title") or ""),
            "url": str(item.get("html_url") or item.get("url") or ""),
            "state": str(item.get("state") or "").upper(),
            "labels": item.get("labels") or [],
            "createdAt": normalized_timestamp(item.get("created_at")),
            "updatedAt": normalized_timestamp(item.get("updated_at")),
            "body": str(item.get("body") or ""),
        })
    return issues, warnings


def list_merged_pr_summaries(repo_root: Path, repo_slug: str, *, window_start: datetime, window_end: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    payload, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/pulls",
        params={"state": "closed", "sort": "updated", "direction": "desc"},
        stop_when=lambda page_items: page_stop_on_last_timestamp(page_items, key="updated_at", window_start=window_start),
        label="merged PR summaries",
    )
    prs: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        merged_at = parse_iso8601(str(item.get("merged_at") or ""))
        if merged_at and window_start <= merged_at <= window_end:
            prs.append({
                "number": int(item.get("number") or 0),
                "title": str(item.get("title") or ""),
                "url": str(item.get("html_url") or item.get("url") or ""),
                "mergedAt": isoformat_utc(merged_at),
                "baseRefName": str((item.get("base") or {}).get("ref") or ""),
                "headRefName": str((item.get("head") or {}).get("ref") or ""),
            })
    return sorted(prs, key=lambda item: str(item.get("mergedAt") or "")), warnings


def fetch_pr_detail(repo_root: Path, repo_slug: str, pr_number: int) -> tuple[dict[str, Any], list[str]]:
    pr = run_gh_json(repo_root, ["api", f"repos/{repo_slug}/pulls/{pr_number}"])
    files, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/pulls/{pr_number}/files",
        label=f"PR #{pr_number} files",
    )
    body = str(pr.get("body") or "")
    paths = [str(file_item.get("filename") or "") for file_item in (files if isinstance(files, list) else [])]
    return {
        "number": int(pr.get("number") or pr_number),
        "title": str(pr.get("title") or ""),
        "url": str(pr.get("html_url") or ""),
        "body": body,
        "base_ref_name": str((pr.get("base") or {}).get("ref") or ""),
        "head_ref_name": str((pr.get("head") or {}).get("ref") or ""),
        "merged_at": normalized_timestamp(pr.get("merged_at")),
        "merge_commit_sha": str(pr.get("merge_commit_sha") or ""),
        "head_sha": str((pr.get("head") or {}).get("sha") or ""),
        "linked_issue_numbers": extract_issue_numbers_from_text(body),
        "files": [{"path": path} for path in paths if path],
        "changed_file_groups": classify_changed_paths(paths),
        "shipped_change_bullets": extract_section_bullets(body, ["What changed", "Change summary"]) or [short_markdown_summary(body, fallback=str(pr.get("title") or ""))],
        "risk_bullets": extract_section_bullets(body, ["Risk / Rollback", "Risk", "Risks"]),
        "validation_bullets": extract_section_bullets(body, ["Validation", "Testing"]),
    }, warnings


def fetch_review_comments(repo_root: Path, repo_slug: str, pr_number: int) -> tuple[list[dict[str, Any]], list[str]]:
    payload, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/pulls/{pr_number}/comments",
        label=f"PR #{pr_number} review comments",
    )
    comments: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        comments.append({
            "id": int(item.get("id") or 0),
            "body": str(item.get("body") or ""),
            "created_at": normalized_timestamp(item.get("created_at")),
            "updated_at": normalized_timestamp(item.get("updated_at")),
            "in_reply_to_id": item.get("in_reply_to_id"),
            "path": item.get("path"),
            "html_url": str(item.get("html_url") or item.get("url") or ""),
            "user": item.get("user") or {},
        })
    return comments, warnings


def list_workflow_runs(repo_root: Path, repo_slug: str, *, window_start: datetime, window_end: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    payload, warnings = paginate_gh_api(
        repo_root,
        f"repos/{repo_slug}/actions/runs",
        collection_key="workflow_runs",
        label="workflow runs",
    )
    runs: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        created_at = normalized_timestamp(item.get("created_at"))
        updated_at = normalized_timestamp(item.get("updated_at"))
        if window_contains(created_at, window_start, window_end) or window_contains(updated_at, window_start, window_end):
            runs.append({
                "databaseId": int(item.get("id") or item.get("database_id") or 0),
                "workflowName": str(item.get("name") or item.get("display_title") or ""),
                "status": str(item.get("status") or ""),
                "conclusion": str(item.get("conclusion") or ""),
                "event": str(item.get("event") or ""),
                "headBranch": str(item.get("head_branch") or ""),
                "headSha": str(item.get("head_sha") or ""),
                "createdAt": created_at,
                "updatedAt": updated_at,
                "url": str(item.get("html_url") or item.get("url") or ""),
            })
    return runs, warnings


def split_top_level_prs(merged_prs: list[dict[str, Any]], default_branch: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    top_level, nested = [], []
    for pr in merged_prs:
        (top_level if str(pr.get("base_ref_name") or pr.get("baseRefName") or "") == default_branch else nested).append(pr)
    return top_level, nested


def build_pr_lineage(merged_prs: list[dict[str, Any]], default_branch: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    ordered = sorted(merged_prs, key=lambda item: str(item.get("merged_at") or item.get("mergedAt") or ""))
    top_level, nested = split_top_level_prs(ordered, default_branch)
    parent_by_child: dict[int, int] = {}
    by_number = {int(pr["number"]): pr for pr in ordered}
    for pr in nested:
        base_ref = str(pr.get("base_ref_name") or pr.get("baseRefName") or "")
        merged_at = str(pr.get("merged_at") or pr.get("mergedAt") or "")
        parent = next((candidate for candidate in ordered if int(candidate["number"]) != int(pr["number"]) and str(candidate.get("head_ref_name") or candidate.get("headRefName") or "") == base_ref and str(candidate.get("merged_at") or candidate.get("mergedAt") or "") > merged_at), None)
        if parent is not None:
            parent_by_child[int(pr["number"])] = int(parent["number"])
    lineage: dict[str, dict[str, Any]] = {}
    absorbed: dict[int, list[int]] = {}
    for pr in nested:
        number = int(pr["number"])
        chain: list[int] = []
        current = number
        while current in parent_by_child and parent_by_child[current] not in chain:
            current = parent_by_child[current]
            chain.append(current)
        root = current if str(by_number.get(current, {}).get("base_ref_name") or by_number.get(current, {}).get("baseRefName") or "") == default_branch else None
        lineage[str(number)] = {"candidate_pr": number, "absorbed_by": parent_by_child.get(number), "root_top_level_pr": root, "chain": chain}
        if root is not None:
            absorbed.setdefault(root, []).append(number)
    top_level = [{**pr, "absorbed_nested_pr_numbers": sorted(absorbed.get(int(pr["number"]), []))} for pr in top_level]
    return top_level, nested, lineage


def build_issue_linkage_set(prs: Iterable[dict[str, Any]]) -> set[int]:
    linked: set[int] = set()
    for pr in prs:
        linked.update(int(number) for number in pr.get("linked_issue_numbers") or [])
    return linked


def link_releases_to_issues(
    releases: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    release_title_re: re.Pattern[str] | None = None,
) -> dict[str, list[int]]:
    lookup: dict[str, list[int]] = {}
    for issue in issues:
        tag = extract_release_tag(
            str(issue.get("title") or ""), release_title_re=release_title_re
        )
        if tag:
            lookup.setdefault(tag, []).append(int(issue["number"]))
    return {release["tag_name"]: sorted(lookup.get(release["tag_name"], [])) for release in releases}


def classify_issue(
    issue: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
    linked_issue_numbers: set[int],
    active_release_tags: set[str],
    release_title_re: re.Pattern[str] | None = None,
) -> dict[str, Any]:
    number = int(issue.get("number"))
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "")
    labels = label_names(issue)
    prefix = title_prefix(title)
    matched_release_tag = extract_release_tag(title, release_title_re=release_title_re)
    materiality_reasons = compute_materiality_reasons(issue, window_start=window_start, window_end=window_end, linked_from_pr=number in linked_issue_numbers, matched_release=matched_release_tag in active_release_tags if matched_release_tag else False)
    weekly_material = bool(materiality_reasons)
    concrete_failure = has_any_pattern(f"{title}\n{body}", CONCRETE_FAILURE_PATTERNS)
    normalized_issue_text = normalize_text(f"{title}\n{body}").lower()
    if any(token in normalized_issue_text for token in ("no reproduced signal yet", "no failure signal", "not reproduced yet")):
        concrete_failure = False
    strong_failure = has_any_pattern(f"{title}\n{body}", STRONG_EVIDENCE_FAILURE_PATTERNS)
    if any(token in normalized_issue_text for token in ("does not add a new failure signal", "artifact collection only", "reusable but does not add")):
        strong_failure = False
    classification = IGNORE
    rule = "outside_reporting_window"
    is_release_issue = prefix == "release" or "release" in labels
    is_bug = prefix == "bug" or "bug" in labels
    is_investigation = prefix in {"investigation", "software investigation"} or "investigation" in labels
    is_evidence = prefix in {"software evidence", "raw log"}
    is_perf = prefix == "performance telemetry" or "performance" in labels
    is_compatibility = "compatibility" in labels
    if is_release_issue:
        classification = BLOCKER_OR_RISK if issue.get("state") == "OPEN" and (weekly_material or matched_release_tag in active_release_tags) else ARTIFACT_ONLY if weekly_material and matched_release_tag in active_release_tags else IGNORE
        rule = "open_release_issue" if classification == BLOCKER_OR_RISK else "linked_release_issue" if classification == ARTIFACT_ONLY else rule
    elif is_bug and weekly_material:
        classification, rule = ACTUAL_INCIDENT, "bug_issue"
    elif is_investigation:
        if weekly_material and (concrete_failure or is_compatibility):
            classification, rule = ACTUAL_INCIDENT, "investigation_with_concrete_failure"
        elif weekly_material or issue.get("state") == "OPEN":
            classification, rule = BLOCKER_OR_RISK, "investigation_tracker"
    elif is_evidence:
        classification, rule = (ACTUAL_INCIDENT, "evidence_with_failure_signal") if weekly_material and strong_failure else (ARTIFACT_ONLY, "evidence_artifact") if weekly_material else (IGNORE, rule)
    elif is_perf:
        classification, rule = (ACTUAL_INCIDENT, "performance_regression") if weekly_material and strong_failure else (ARTIFACT_ONLY, "performance_artifact") if weekly_material else (IGNORE, rule)
    elif is_compatibility and weekly_material:
        classification, rule = (ACTUAL_INCIDENT, "compatibility_with_failure_signal") if concrete_failure else (BLOCKER_OR_RISK, "compatibility_tracker")
    elif weekly_material and any(label in labels for label in ("needs-decision", "needs-repro")):
        classification, rule = BLOCKER_OR_RISK, "tracking_label"
    summary = short_markdown_summary(body, fallback=title)
    rationale_bits = [f"Rule `{rule}` matched."] if classification != IGNORE else []
    if weekly_material:
        rationale_bits.append("The issue changed during the reporting window or linked directly to shipped work.")
    if concrete_failure:
        rationale_bits.append("The title or body includes concrete failure or repro language.")
    return {
        "number": number,
        "title": title,
        "url": issue.get("url"),
        "classification": classification,
        "classification_rationale": " ".join(rationale_bits),
        "summary": summary,
        "materiality_reasons": materiality_reasons,
        "weekly_material": weekly_material,
        "concrete_failure": concrete_failure,
        "matched_release_tag": matched_release_tag,
        "labels": labels,
        "rule": rule,
        "state": str(issue.get("state") or "").upper(),
    }


def is_generic_review_noise(body: str) -> bool:
    normalized = normalize_text(body)
    return not normalized or any(pattern.search(normalized.lower()) for pattern in GENERIC_REVIEW_NOISE_PATTERNS)


def extract_review_findings(
    pr_number: int,
    pr_url: str,
    review_comments: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    review_ack_patterns: list[re.Pattern[str]] | None = None,
    review_complete_patterns: list[re.Pattern[str]] | None = None,
    priority_marker_re: re.Pattern[str] | None = None,
) -> list[dict[str, Any]]:
    ack_patterns = review_ack_patterns or DEFAULT_REVIEW_ACK_PATTERNS
    complete_patterns = review_complete_patterns or DEFAULT_REVIEW_COMPLETE_PATTERNS
    gate_priority_pattern = priority_marker_re or DEFAULT_PRIORITY_MARKER_RE
    replies_by_root: dict[int, list[dict[str, Any]]] = {}
    for comment in review_comments:
        if comment.get("in_reply_to_id") is not None:
            replies_by_root.setdefault(int(comment["in_reply_to_id"]), []).append(comment)
    findings: list[dict[str, Any]] = []
    for comment in review_comments:
        if comment.get("in_reply_to_id") is not None:
            continue
        body = str(comment.get("body") or "").strip()
        author = str((comment.get("user") or {}).get("login") or comment.get("author") or "").lower()
        if author.endswith("[bot]") or normalize_text(body).lower() in {"looks good to me.", "lgtm"} or is_generic_review_noise(body):
            continue
        materiality_reasons = []
        created_at = str(comment.get("created_at") or "")
        updated_at = str(comment.get("updated_at") or "")
        if window_contains(created_at, window_start, window_end):
            materiality_reasons.append("review_comment_in_window")
        if window_contains(updated_at, window_start, window_end) and updated_at != created_at:
            materiality_reasons.append("review_reply_in_window")
        if not materiality_reasons:
            continue
        replies = replies_by_root.get(int(comment["id"]), [])
        status = (
            "resolved"
            if any(
                pattern.search(str(reply.get("body") or ""))
                for reply in replies
                for pattern in complete_patterns
            )
            else "acknowledged"
            if any(
                pattern.search(str(reply.get("body") or ""))
                for reply in replies
                for pattern in ack_patterns
            )
            else "unresolved"
        )
        summary = short_markdown_summary(body, fallback=f"Review finding on PR #{pr_number}")
        findings.append({
            "id": f"review-pr{pr_number}-comment{comment['id']}",
            "pr_number": pr_number,
            "pr_url": pr_url,
            "comment_id": int(comment["id"]),
            "html_url": comment.get("html_url"),
            "summary": summary,
            "raw_body": body,
            "status": status,
            "gate_impact": bool(gate_priority_pattern.search(body) or has_any_pattern(f"{body}\n{summary}", GATE_IMPACT_PATTERNS)),
            "materiality_reasons": materiality_reasons,
            "created_at": created_at,
            "updated_at": updated_at,
            "path": comment.get("path"),
        })
    return findings


def classify_workflow_run(run: dict[str, Any], *, window_start: datetime, window_end: datetime) -> dict[str, Any] | None:
    conclusion = str(run.get("conclusion") or "").lower()
    if conclusion in NEUTRAL_WORKFLOW_CONCLUSIONS or conclusion not in FAILED_WORKFLOW_CONCLUSIONS:
        return None
    materiality_reasons = compute_materiality_reasons(run, window_start=window_start, window_end=window_end, created_key="createdAt", updated_key="updatedAt")
    if not materiality_reasons:
        return None
    return {"database_id": int(run["databaseId"]), "workflow_name": str(run.get("workflowName") or ""), "summary": f"{run.get('workflowName')} concluded with {conclusion}.", "url": run.get("url"), "created_at": run.get("createdAt"), "updated_at": run.get("updatedAt"), "materiality_reasons": materiality_reasons}


def candidate_base(**kwargs: Any) -> dict[str, Any]:
    candidate = dict(kwargs)
    for field in CANDIDATE_REQUIRED_FIELDS:
        candidate.setdefault(field, [] if field in {"materiality_evidence", "concrete_failure_evidence", "source_refs", "packet_membership", "tests_or_checks"} else "" if field in {"summary", "classification_rationale", "open_ambiguity", "risk", "recommended_next_step"} else None)
    return candidate


def build_context_fingerprint(context: dict[str, Any]) -> str:
    payload = {
        "repo_slug": context.get("repo_slug"),
        "default_branch": context.get("default_branch"),
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_weekly_update": weekly_update_profile_data(
            context.get("repo_profile")
        ),
        "reporting_window": context.get("reporting_window"),
        "release_tags": [release.get("tag_name") for release in context.get("releases", [])],
        "top_level_pr_numbers": [pr.get("number") for pr in context.get("top_level_prs", [])],
        "nested_pr_numbers": [pr.get("number") for pr in context.get("nested_prs", [])],
        "candidate_ids": [candidate.get("candidate_id") for candidate in context.get("candidate_inventory", [])],
    }
    return sha256_json(payload)





def build_candidate_inventory(context: dict[str, Any], releases: list[dict[str, Any]], top_level_prs: list[dict[str, Any]], issues: list[dict[str, Any]], classified_issues: list[dict[str, Any]], review_findings: list[dict[str, Any]], workflow_failures: list[dict[str, Any]], release_issue_linkage: dict[str, list[int]]) -> list[dict[str, Any]]:
    issue_lookup = {int(issue["number"]): issue for issue in issues}
    review_by_pr: dict[int, list[dict[str, Any]]] = {}
    inventory: list[dict[str, Any]] = []
    for finding in review_findings:
        review_by_pr.setdefault(int(finding["pr_number"]), []).append(finding)
    for release in releases:
        tag = release["tag_name"]
        inventory.append(candidate_base(
            candidate_id=f"release-{tag}", source_type="release", source_id=tag, title=release.get("name") or tag,
            summary=f"Published release {tag}.", proposed_classification=IGNORE, classification_rationale="Release candidates feed the Rollouts section directly.",
            materiality_evidence=[f"published_at={release['published_at']}"], concrete_failure_evidence=[], open_ambiguity="", confidence="high",
            source_refs=[canonical_ref("release", f"release/{tag}", release.get("url"))],
            excerpt_bundle=excerpt_bundle(failure_text=None, materiality_text=f"Release {tag} was published at {release['published_at']}.", ambiguity_text=None, source_ref=f"release/{tag}", source_type="release"),
            raw_reread_reason=None, packet_membership=["mapping_packet"], risk="", recommended_next_step="", tests_or_checks=[], section_hint="Rollouts", linked_issue_numbers=release_issue_linkage.get(tag, []),
        ))
    for pr in top_level_prs:
        risk_text = " ".join(pr.get("risk_bullets") or [])
        review_ids = [finding["id"] for finding in review_by_pr.get(int(pr["number"]), [])]
        inventory.append(candidate_base(
            candidate_id=f"pr-{pr['number']}", source_type="pr", source_id=f"#{pr['number']}", title=pr["title"],
            summary=short_markdown_summary(pr["body"], fallback=pr["title"]), proposed_classification=IGNORE, classification_rationale="Top-level merged PRs feed the PRs section directly.",
            materiality_evidence=[f"merged_at={pr['merged_at']}", f"base_ref={pr['base_ref_name']}"], concrete_failure_evidence=[], open_ambiguity=risk_text, confidence="high",
            source_refs=[canonical_ref("pr", f"pr/#{pr['number']}", pr.get("url"))],
            excerpt_bundle=excerpt_bundle(failure_text=None, materiality_text=f"PR #{pr['number']} merged to {pr['base_ref_name']} at {pr['merged_at']}.", ambiguity_text=risk_text, source_ref=f"pr/#{pr['number']}", source_type="pr"),
            raw_reread_reason=None, packet_membership=["mapping_packet", "changes_packet"], risk=risk_text, recommended_next_step=(pr.get("risk_bullets") or [""])[0], tests_or_checks=list(pr.get("validation_bullets") or []),
            section_hint="PRs", shipped_change_bullets=list(pr.get("shipped_change_bullets") or []), review_followups=[], review_candidate_items=review_ids, changed_path_groups=pr.get("changed_file_groups") or {}, absorbed_nested_pr_numbers=list(pr.get("absorbed_nested_pr_numbers") or []),
        ))
    for classified in classified_issues:
        issue = issue_lookup[int(classified["number"])]
        failure_text = short_markdown_summary(issue.get("body") or "", fallback=classified["title"]) if classified["concrete_failure"] else None
        ambiguity_text = "Tracker remains open and still affects release or scheduling decisions." if classified["classification"] == BLOCKER_OR_RISK and classified["state"] == "OPEN" else ""
        raw_reread_reason = "missing_failure_evidence" if classified["classification"] == ACTUAL_INCIDENT and not failure_text else None
        section_hint = "Incidents" if classified["classification"] == ACTUAL_INCIDENT else "Blockers / Risks" if classified["classification"] == BLOCKER_OR_RISK else "Evidence reviewed" if classified["classification"] == ARTIFACT_ONLY else "Ignore"
        packet_membership = ["mapping_packet"] + (["incidents_packet"] if classified["classification"] == ACTUAL_INCIDENT else ["risks_packet"] if classified["classification"] in {BLOCKER_OR_RISK, ARTIFACT_ONLY} else [])
        inventory.append(candidate_base(
            candidate_id=f"issue-{classified['number']}", source_type="issue", source_id=f"#{classified['number']}", title=classified["title"], summary=classified["summary"],
            proposed_classification=classified["classification"], classification_rationale=classified["classification_rationale"], materiality_evidence=list(classified["materiality_reasons"]),
            concrete_failure_evidence=[failure_text] if failure_text else [], open_ambiguity=ambiguity_text,
            confidence=confidence_from_signals(materiality_present=classified["weekly_material"], failure_present=classified["concrete_failure"], raw_reread_reason=raw_reread_reason, open_ambiguity=ambiguity_text),
            source_refs=[canonical_ref("issue", f"issue/#{classified['number']}", classified.get("url"))],
            excerpt_bundle=excerpt_bundle(failure_text=failure_text, materiality_text=metadata_excerpt(issue.get("createdAt"), issue.get("updatedAt")), ambiguity_text=ambiguity_text, source_ref=f"issue/#{classified['number']}", source_type="issue"),
            raw_reread_reason=raw_reread_reason, packet_membership=packet_membership,
            risk="Open blocker or release-risk tracker remains active." if classified["classification"] == BLOCKER_OR_RISK else "Incident evidence affected validation or delivery during the week." if classified["classification"] == ACTUAL_INCIDENT else "",
            recommended_next_step="Resolve or explicitly downgrade the tracker before the next weekly report." if classified["classification"] == BLOCKER_OR_RISK and classified["state"] == "OPEN" else "",
            tests_or_checks=[], section_hint=section_hint, classification_rule=classified["rule"],
        ))
    for finding in review_findings:
        proposed = BLOCKER_OR_RISK if finding["status"] != "resolved" and finding["gate_impact"] else IGNORE
        packets = ["mapping_packet", "changes_packet"] + (["risks_packet"] if proposed == BLOCKER_OR_RISK else [])
        inventory.append(candidate_base(
            candidate_id=finding["id"], source_type="review_finding", source_id=str(finding["comment_id"]), title=f"PR #{finding['pr_number']} review finding", summary=finding["summary"],
            proposed_classification=proposed, classification_rationale="Unresolved review finding still carries merge or release-gate risk." if proposed == BLOCKER_OR_RISK else "Review finding is included for Reviews synthesis only.",
            materiality_evidence=list(finding["materiality_reasons"]), concrete_failure_evidence=[finding["summary"]] if finding["gate_impact"] else [],
            open_ambiguity="" if finding["status"] == "resolved" else "Review thread is not fully closed.", confidence="high" if finding["gate_impact"] and finding["status"] == "resolved" else "medium",
            source_refs=[canonical_ref("review", f"review/pr{finding['pr_number']}-comment{finding['comment_id']}", finding.get("html_url")), canonical_ref("pr", f"pr/#{finding['pr_number']}", finding.get("pr_url"))],
            excerpt_bundle=excerpt_bundle(failure_text=finding["summary"] if finding["gate_impact"] else None, materiality_text=metadata_excerpt(finding.get("created_at"), finding.get("updated_at")), ambiguity_text="" if finding["status"] == "resolved" else "Review thread is not fully closed.", source_ref=f"review/pr{finding['pr_number']}-comment{finding['comment_id']}", source_type="review_finding"),
            raw_reread_reason=None, packet_membership=packets, risk="Unresolved review finding may still block merge or release." if proposed == BLOCKER_OR_RISK else "",
            recommended_next_step="Close the thread or document why it is intentionally deferred." if finding["status"] != "resolved" else "", tests_or_checks=[],
            section_hint="Reviews", review_status=finding["status"], gate_impact=finding["gate_impact"], pr_number=finding["pr_number"],
        ))
    for run in workflow_failures:
        inventory.append(candidate_base(
            candidate_id=f"run-{run['database_id']}", source_type="workflow_run", source_id=str(run["database_id"]), title=run["workflow_name"], summary=run["summary"],
            proposed_classification=ACTUAL_INCIDENT, classification_rationale="The workflow run failed during the reporting window and materially affected validation evidence.",
            materiality_evidence=list(run["materiality_reasons"]), concrete_failure_evidence=[run["summary"]], open_ambiguity="", confidence="high",
            source_refs=[canonical_ref("run", f"run/{run['database_id']}", run.get("url"))],
            excerpt_bundle=excerpt_bundle(failure_text=run["summary"], materiality_text=metadata_excerpt(run.get("created_at"), run.get("updated_at")), ambiguity_text=None, source_ref=f"run/{run['database_id']}", source_type="workflow_run"),
            raw_reread_reason=None, packet_membership=["mapping_packet", "incidents_packet"], risk="Failed workflow run affected validation or release evidence.",
            recommended_next_step="Confirm remediation or rerun outcome before reusing this evidence.", tests_or_checks=[], section_hint="Incidents",
        ))
    return inventory


def collect_context(
    *,
    repo_root: str,
    profile: str | None = None,
    state_file: str | None = None,
    window_days: int = 7,
    now_utc: str | None = None,
) -> dict[str, Any]:
    repo_path = resolve_repo_root(repo_root)
    profile_path = resolve_profile_path(profile, repo_root=repo_path)
    repo_profile = load_repo_profile(profile_path)
    runtime_settings = weekly_update_runtime_settings(repo_profile)
    verify_gh_auth(repo_path)
    repo_meta = get_repo_metadata(repo_path)
    branch_state = get_branch_state(repo_path)
    repo_hash = compute_repo_hash(repo_path)
    resolved_state_file = (
        Path(state_file).resolve()
        if state_file
        else default_state_file(
            repo_hash, namespace=runtime_settings["state_namespace"]
        )
    )
    marker, marker_warnings = load_state_marker(resolved_state_file)
    current_now = parse_iso8601(now_utc) or utc_now()
    reporting_window = select_reporting_window(now_utc=current_now, window_days=window_days, state_marker=marker)
    window_start = parse_iso8601(reporting_window["start_utc"])
    window_end = parse_iso8601(reporting_window["end_utc"])
    assert window_start is not None and window_end is not None
    source_gaps = list(marker_warnings)
    releases, release_warnings = list_releases(repo_path, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)
    issues, issue_warnings = list_issues(repo_path, repo_meta["repo_slug"])
    pr_summaries, pr_summary_warnings = list_merged_pr_summaries(repo_path, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)
    source_gaps.extend(release_warnings)
    source_gaps.extend(issue_warnings)
    source_gaps.extend(pr_summary_warnings)
    merged_prs: list[dict[str, Any]] = []
    for summary in pr_summaries:
        detail, detail_warnings = fetch_pr_detail(repo_path, repo_meta["repo_slug"], int(summary["number"]))
        merged_prs.append(detail)
        source_gaps.extend(detail_warnings)
    top_level_prs, nested_prs, pr_lineage = build_pr_lineage(merged_prs, repo_meta["default_branch"])
    release_issue_linkage = link_releases_to_issues(
        releases,
        issues,
        release_title_re=runtime_settings["release_title_re"],
    )
    linked_issue_numbers = build_issue_linkage_set(top_level_prs)
    active_release_tags = {release["tag_name"] for release in releases}
    classified_issues = [
        classified
        for classified in (
            classify_issue(
                issue,
                window_start=window_start,
                window_end=window_end,
                linked_issue_numbers=linked_issue_numbers,
                active_release_tags=active_release_tags,
                release_title_re=runtime_settings["release_title_re"],
            )
            for issue in issues
        )
        if classified["classification"] != IGNORE
    ]
    review_findings: list[dict[str, Any]] = []
    for pr in top_level_prs:
        review_comments, review_warnings = fetch_review_comments(repo_path, repo_meta["repo_slug"], int(pr["number"]))
        source_gaps.extend(review_warnings)
        review_findings.extend(
            extract_review_findings(
                int(pr["number"]),
                str(pr.get("url") or ""),
                review_comments,
                window_start=window_start,
                window_end=window_end,
                review_ack_patterns=runtime_settings["review_ack_patterns"],
                review_complete_patterns=runtime_settings["review_complete_patterns"],
                priority_marker_re=runtime_settings["priority_marker_re"],
            )
        )
    workflow_runs, workflow_warnings = list_workflow_runs(repo_path, repo_meta["repo_slug"], window_start=window_start, window_end=window_end)
    source_gaps.extend(workflow_warnings)
    workflow_failures = [classified for classified in (classify_workflow_run(run, window_start=window_start, window_end=window_end) for run in workflow_runs) if classified is not None]
    context = {
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "repo_root": repo_path.as_posix(),
        "repo_hash": repo_hash,
        "repo_slug": repo_meta["repo_slug"],
        "repo_url": repo_meta["repo_url"],
        "default_branch": repo_meta["default_branch"],
        "current_branch": branch_state["current_branch"],
        "head_sha": branch_state["head_sha"],
        "repo_profile_name": repo_profile.get("name"),
        "repo_profile_path": profile_path.as_posix(),
        "repo_profile_summary": repo_profile.get("summary"),
        "repo_profile": repo_profile,
        "builder_compatibility": build_builder_compatibility(repo_profile),
        "state_namespace": runtime_settings["state_namespace"],
        "state_file": resolved_state_file.as_posix(),
        "state_marker": marker,
        "reporting_window": reporting_window,
        "collected_at": isoformat_utc(current_now),
        "authority_order": AUTHORITY_ORDER,
        "stop_conditions": STOP_CONDITIONS,
        "releases": releases,
        "release_issue_linkage": release_issue_linkage,
        "top_level_prs": top_level_prs,
        "nested_prs": nested_prs,
        "pr_lineage": pr_lineage,
        "classified_issues": classified_issues,
        "review_findings": review_findings,
        "workflow_failures": workflow_failures,
        "source_gaps": stable_unique(source_gaps),
        "notes": [f"Loaded repo profile from {profile_path.as_posix()}."],
    }
    context["candidate_inventory"] = build_candidate_inventory(context, releases, top_level_prs, issues, classified_issues, review_findings, workflow_failures, release_issue_linkage)
    context["counts"] = {
        "releases": len(releases),
        "top_level_prs": len(top_level_prs),
        "nested_prs": len(nested_prs),
        "selected_issues": len(classified_issues),
        "review_findings": len(review_findings),
        "workflow_failures": len(workflow_failures),
        "actual_incident_items": sum(1 for candidate in context["candidate_inventory"] if candidate["proposed_classification"] == ACTUAL_INCIDENT),
        "changed_files": sum(len(pr.get("files") or []) for pr in merged_prs),
        "task_packet_count": len(PACKET_NAMES),
        "batch_count": 0,
    }
    context["override_signals"] = {
        "high_churn": context["counts"]["top_level_prs"] >= 6 or context["counts"]["selected_issues"] >= 10,
        "multi_surface_active": bool(context["counts"]["releases"] and context["counts"]["actual_incident_items"] and context["counts"]["review_findings"]),
        "nested_lineage_complexity": bool(context["counts"]["nested_prs"] and context["counts"]["workflow_failures"]),
    }
    context["context_fingerprint"] = build_context_fingerprint(context)
    context["context_id"] = f"{SKILL_NAME}:{current_now.strftime('%Y%m%dT%H%M%SZ')}:{repo_hash}"
    return context


def emit_builder_compatibility_warning(compatibility: dict[str, Any]) -> None:
    if compatibility.get("status") == "current":
        return
    print(format_runtime_warning(compatibility), file=sys.stderr)


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    errors = [f"Candidate {candidate.get('candidate_id')} is missing required field `{field}`." for field in CANDIDATE_REQUIRED_FIELDS if field not in candidate]
    if "evidence_files_or_links" in candidate:
        errors.append(f"Candidate {candidate.get('candidate_id')} still uses forbidden field `evidence_files_or_links`.")
    if candidate.get("proposed_classification") not in PROPOSED_CLASSIFICATIONS:
        errors.append(f"Candidate {candidate.get('candidate_id')} has invalid proposed_classification.")
    if candidate.get("confidence") not in CONFIDENCE_VALUES:
        errors.append(f"Candidate {candidate.get('candidate_id')} has invalid confidence.")
    if candidate.get("raw_reread_reason") is not None and candidate.get("raw_reread_reason") not in RAW_REREAD_REASONS:
        errors.append(f"Candidate {candidate.get('candidate_id')} has invalid raw_reread_reason.")
    if not isinstance(candidate.get("source_refs"), list) or not candidate.get("source_refs"):
        errors.append(f"Candidate {candidate.get('candidate_id')} is missing canonical source_refs.")
    return errors


def lint_context(context: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = [f"Collected {len(context.get('candidate_inventory') or [])} candidates."]
    for candidate in context.get("candidate_inventory") or []:
        errors.extend(validate_candidate(candidate))
        if candidate.get("raw_reread_reason"):
            warnings.append(f"Candidate {candidate['candidate_id']} requires raw reread: {candidate['raw_reread_reason']}.")
        if candidate.get("proposed_classification") == ARTIFACT_ONLY and candidate.get("section_hint") == "Blockers / Risks":
            errors.append(f"artifact_only candidate {candidate['candidate_id']} cannot target Blockers / Risks directly.")
    if context.get("reporting_window", {}).get("source") == "state_marker" and float(context.get("reporting_window", {}).get("span_hours") or 0) > 14 * 24:
        warnings.append("Reporting window spans more than 14 days; this is a catch-up window.")
    warnings.extend(str(item) for item in context.get("source_gaps") or [])
    return {"findings": {"errors": errors, "warnings": warnings, "info": info}, "override_signals": context.get("override_signals") or {}, "can_proceed": not errors}


def select_review_mode(context: dict[str, Any], lint_report: dict[str, Any]) -> str:
    counts = context.get("counts") or {}
    relevant_candidates = sum(1 for candidate in context.get("candidate_inventory") or [] if candidate.get("section_hint") in {"Incidents", "Reviews", "Blockers / Risks"})
    overrides = {}
    overrides.update(context.get("override_signals") or {})
    overrides.update(lint_report.get("override_signals") or {})
    if int(counts.get("top_level_prs") or 0) <= 2 and relevant_candidates <= 4 and int(counts.get("releases") or 0) == 0 and int(counts.get("workflow_failures") or 0) == 0:
        return "local-only"
    if int(counts.get("top_level_prs") or 0) >= 6 or relevant_candidates >= 10 or any(bool(value) for value in overrides.values()):
        return "broad-delegation"
    return "targeted-delegation"


def build_packets(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    review_mode = select_review_mode(context, lint_report)
    candidate_lookup = {candidate["candidate_id"]: candidate for candidate in context.get("candidate_inventory") or []}
    pr_ids = [candidate["candidate_id"] for candidate in context.get("candidate_inventory") or [] if candidate.get("section_hint") == "PRs"]
    incident_ids = [candidate["candidate_id"] for candidate in context.get("candidate_inventory") or [] if candidate["proposed_classification"] == ACTUAL_INCIDENT or candidate.get("section_hint") == "Incidents"]
    risk_ids = [
        candidate["candidate_id"]
        for candidate in context.get("candidate_inventory") or []
        if candidate["proposed_classification"] in {BLOCKER_OR_RISK, ARTIFACT_ONLY}
        or (candidate.get("section_hint") == "Reviews" and candidate["proposed_classification"] == BLOCKER_OR_RISK)
    ]
    workers = routed_workers_for_review_mode(review_mode)
    optional_workers = derived_optional_workers(workers)
    worker_selection_guidance = {
        "routing_authority": "packet_worker_map",
        "notes": "worker_selection_guidance is explanatory only; packet_worker_map is the concrete routing source.",
        "agent_type_guidance": WORKER_SELECTION_GUIDANCE,
    }
    global_packet = {
        "skill_name": SKILL_NAME,
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "primary_goal": PRIMARY_GOAL,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "repo_profile": context.get("repo_profile"),
        "reporting_window": context.get("reporting_window"),
        "output_sections": OUTPUT_SECTIONS,
        "authority_order": AUTHORITY_ORDER,
        "stop_conditions": STOP_CONDITIONS,
        "review_mode": review_mode,
        "review_mode_overrides": REVIEW_MODE_OVERRIDES,
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "candidate_field_bundles": CANDIDATE_FIELD_BUNDLES,
        "worker_footer_fields": WORKER_FOOTER_FIELDS,
        "reread_reason_values": [None, *RAW_REREAD_REASONS],
        "domain_overlay": DOMAIN_OVERLAY,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": PACKET_WORKER_MAP,
        "worker_selection_guidance": worker_selection_guidance,
        "source_gaps": context.get("source_gaps") or [],
        "candidate_schema": {"required_fields": CANDIDATE_REQUIRED_FIELDS, "proposed_classification_values": PROPOSED_CLASSIFICATIONS, "confidence_values": CONFIDENCE_VALUES, "raw_reread_reason_values": [None, *RAW_REREAD_REASONS], "source_refs_rule": "canonical citation list only; do not use evidence_files_or_links", "artifact_only_rule": "artifact_only candidates are reference-only and do not appear as standalone final section items"},
        "worker_output_contract": {
            "worker_output_shape": WORKER_OUTPUT_SHAPE,
            "candidates_container": "candidates",
            "footer_container": "footer",
            "candidate_level_fields": CANDIDATE_REQUIRED_FIELDS,
            "worker_footer_fields": WORKER_FOOTER_FIELDS,
            "candidate_ids_order_rule": "candidate_ids must follow candidates[] stable discovery order exactly",
        },
        "reviews_rules": {"resolved_review_findings": "Reviews only", "unresolved_gate_impact_findings": "Reviews and Blockers / Risks may both include them", "excluded_noise": "generic notice, bot noise, and empty self-review"},
        "apply_contract": {"plan_file": "weekly-update-plan.json", "reads_only": ["overall_confidence", "stop_reasons", "allow_marker_update"]},
    }
    mapping_packet = {
        "packet_id": "mapping_packet",
        "reporting_window": context.get("reporting_window"),
        "default_branch": context.get("default_branch"),
        "release_issue_linkage": context.get("release_issue_linkage"),
        "top_level_pr_numbers": [pr["number"] for pr in context.get("top_level_prs") or []],
        "nested_pr_numbers": [pr["number"] for pr in context.get("nested_prs") or []],
        "pr_lineage": context.get("pr_lineage"),
        "candidate_inventory_index": [{"candidate_id": candidate["candidate_id"], "source_type": candidate["source_type"], "source_id": candidate["source_id"], "section_hint": candidate.get("section_hint"), "proposed_classification": candidate["proposed_classification"], "confidence": candidate["confidence"], "packet_membership": candidate["packet_membership"], "raw_reread_reason": candidate["raw_reread_reason"], "source_refs": candidate["source_refs"]} for candidate in context.get("candidate_inventory") or []],
        "raw_reread_candidate_ids": [candidate["candidate_id"] for candidate in context.get("candidate_inventory") or [] if candidate.get("raw_reread_reason") is not None],
        "packet_worker_map": PACKET_WORKER_MAP,
        "worker_selection_guidance": worker_selection_guidance,
    }
    changes_candidates = [{**candidate_lookup[candidate_id], "review_followups": [candidate_lookup[review_id]["summary"] for review_id in candidate_lookup[candidate_id].get("review_candidate_items") or [] if review_id in candidate_lookup]} for candidate_id in pr_ids]
    changes_packet = focused_packet_contract("changes_packet", changes_candidates)
    changes_packet["candidate_ids"] = pr_ids
    incidents_packet = focused_packet_contract("incidents_packet", [candidate_lookup[candidate_id] for candidate_id in incident_ids])
    incidents_packet["candidate_ids"] = incident_ids
    risks_packet = focused_packet_contract("risks_packet", [candidate_lookup[candidate_id] for candidate_id in risk_ids])
    risks_packet["candidate_ids"] = risk_ids
    risks_packet["artifact_reference_candidate_ids"] = [candidate_id for candidate_id in risk_ids if candidate_lookup[candidate_id]["proposed_classification"] == ARTIFACT_ONLY]
    orchestrator = {
        "skill_name": SKILL_NAME,
        "workflow_family": WORKFLOW_FAMILY,
        "archetype": ARCHETYPE,
        "orchestrator_profile": ORCHESTRATOR_PROFILE,
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "repo_profile_summary": context.get("repo_profile_summary"),
        "review_mode": review_mode,
        "decision_ready_packets": DECISION_READY_PACKETS,
        "worker_return_contract": WORKER_RETURN_CONTRACT,
        "worker_output_shape": WORKER_OUTPUT_SHAPE,
        "preferred_worker_families": PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": PACKET_WORKER_MAP,
        "worker_selection_guidance": worker_selection_guidance,
        "recommended_worker_count": len(workers),
        "recommended_workers": workers,
        "optional_workers": optional_workers,
        "local_responsibilities": ["final adjudication", "section inclusion and exclusion", "exception-path raw reread only when needed", "final wording", "state marker update gate"],
        "shared_packet": "global_packet.json",
        "selected_packets": PACKET_NAMES,
        "common_path_contract": COMMON_PATH_CONTRACT,
        "analysis_targets": {"candidate_count": len(context.get("candidate_inventory") or []), "batch_count": 0},
        "review_mode_overrides": REVIEW_MODE_OVERRIDES,
    }
    return {"orchestrator.json": orchestrator, "global_packet.json": global_packet, "mapping_packet.json": mapping_packet, "changes_packet.json": changes_packet, "incidents_packet.json": incidents_packet, "risks_packet.json": risks_packet}


def count_candidates_by_proposed_classification(candidates: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {value: 0 for value in PROPOSED_CLASSIFICATIONS}
    for candidate in candidates:
        classification = str(candidate.get("proposed_classification") or "").strip()
        if classification in counts:
            counts[classification] += 1
    return counts


def count_raw_reread_reasons(candidates: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {value: 0 for value in RAW_REREAD_REASONS}
    for candidate in candidates:
        reason = str(candidate.get("raw_reread_reason") or "").strip()
        if reason in counts:
            counts[reason] += 1
    return {reason: count for reason, count in counts.items() if count > 0}


def compute_packet_metrics(packet_payloads: dict[str, Any], *, raw_local_sources: dict[str, Any]) -> dict[str, int]:
    packet_sizes = {name: json_bytes(payload) for name, payload in packet_payloads.items()}
    total_packet_bytes = sum(packet_sizes.values())
    largest_sizes = sorted(packet_sizes.values(), reverse=True)
    focused_packet_files = ["changes_packet.json", "incidents_packet.json", "risks_packet.json"]
    common_path_bytes = packet_sizes.get("global_packet.json", 0) + packet_sizes.get("mapping_packet.json", 0)
    common_path_bytes += max((packet_sizes.get(name, 0) for name in focused_packet_files), default=0)
    local_only_bytes = sum(json_bytes(payload) for payload in raw_local_sources.values())
    estimated_local_only_tokens = estimate_tokens_from_bytes(local_only_bytes)
    estimated_packet_tokens = estimate_tokens_from_bytes(common_path_bytes)
    return {
        "packet_count": len(packet_payloads),
        "packet_size_bytes": total_packet_bytes,
        "largest_packet_bytes": largest_sizes[0] if largest_sizes else 0,
        "largest_two_packets_bytes": sum(largest_sizes[:2]),
        "estimated_local_only_tokens": estimated_local_only_tokens,
        "estimated_packet_tokens": estimated_packet_tokens,
        "estimated_delegation_savings": max(0, estimated_local_only_tokens - estimated_packet_tokens),
    }


def build_packet_artifacts(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, Any]:
    packets = build_packets(context, lint_report)
    candidates = list(context.get("candidate_inventory") or [])
    packet_metrics = compute_packet_metrics(
        packets,
        raw_local_sources={"context": context, "lint": lint_report},
    )
    raw_reread_reason_counts = count_raw_reread_reasons(candidates)
    build_result = {
        "repo_profile_name": context.get("repo_profile_name"),
        "repo_profile_path": context.get("repo_profile_path"),
        "review_mode": packets["orchestrator.json"].get("review_mode"),
        "selected_packets": list(packets["orchestrator.json"].get("selected_packets") or []),
        "recommended_worker_count": packets["orchestrator.json"].get("recommended_worker_count"),
        "recommended_workers": list(packets["orchestrator.json"].get("recommended_workers") or []),
        "optional_workers": list(packets["orchestrator.json"].get("optional_workers") or []),
        "packet_metrics": packet_metrics,
        "candidate_counts_by_proposed_classification": count_candidates_by_proposed_classification(candidates),
        "raw_reread_reason_counts": raw_reread_reason_counts,
        "coverage_gap_count": len(context.get("source_gaps") or []),
        "common_path_sufficient": not raw_reread_reason_counts,
        "raw_reread_count": sum(raw_reread_reason_counts.values()),
    }
    return {"packets": packets, "packet_metrics": packet_metrics, "build_result": build_result}


def aggregate_plan_confidence(plan: dict[str, Any], context: dict[str, Any]) -> str:
    if plan.get("overall_confidence") in CONFIDENCE_VALUES:
        return str(plan["overall_confidence"])
    candidate_confidences = [candidate.get("confidence") for candidate in context.get("candidate_inventory") or []]
    return "low" if "low" in candidate_confidences else "medium" if "medium" in candidate_confidences else "high"


def unresolved_reread_candidate_ids(plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
    explicit = plan.get("unresolved_raw_reread_candidate_ids")
    if isinstance(explicit, list):
        return [str(item) for item in explicit]
    return [candidate["candidate_id"] for candidate in context.get("candidate_inventory") or [] if candidate.get("raw_reread_reason") is not None]


def apply_gate_summary(plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_confidence": aggregate_plan_confidence(plan, context),
        "unresolved_raw_reread_candidate_ids": stable_unique(unresolved_reread_candidate_ids(plan, context)),
        "stop_reasons": stable_unique(str(item) for item in (plan.get("stop_reasons") or [])),
        "allow_marker_update": bool(plan.get("allow_marker_update")),
    }


def section_items(section_payload: Any) -> list[Any]:
    if isinstance(section_payload, list):
        return section_payload
    if isinstance(section_payload, dict) and isinstance(section_payload.get("items"), list):
        return list(section_payload["items"])
    return []


def iter_plan_section_candidate_ids(plan: dict[str, Any]) -> list[tuple[str, str]]:
    section_refs: list[tuple[str, str]] = []
    sections = plan.get("sections")
    if not isinstance(sections, dict):
        return section_refs
    for section_name, payload in sections.items():
        for item in section_items(payload):
            if isinstance(item, dict):
                candidate_id = item.get("candidate_id")
                if isinstance(candidate_id, str) and candidate_id.strip():
                    section_refs.append((section_name, candidate_id.strip()))
                candidate_ids = item.get("candidate_ids")
                if isinstance(candidate_ids, list):
                    section_refs.extend((section_name, str(value).strip()) for value in candidate_ids if str(value).strip())
    return section_refs


def dedupe_stable_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def derived_optional_workers(recommended_workers: list[dict[str, str]]) -> list[str]:
    recommended_types = {str(worker.get("agent_type") or "").strip() for worker in recommended_workers if str(worker.get("agent_type") or "").strip()}
    surfaced = []
    for family_name in WORKER_FAMILY_ORDER:
        surfaced.extend(PREFERRED_WORKER_FAMILIES.get(family_name, []))
    return [worker_type for worker_type in dedupe_stable_strings(surfaced) if worker_type not in recommended_types]


def routed_workers_for_review_mode(review_mode: str) -> list[dict[str, str]]:
    active_packets = [] if review_mode == "local-only" else ["mapping_packet", "changes_packet"] if review_mode == "targeted-delegation" else PACKET_NAMES
    workers: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    instructions = {
        "mapping_packet": "Confirm the evidence map and packet membership.",
        "changes_packet": "Review shipped changes and review follow-ups only.",
        "incidents_packet": "Review incident and workflow candidates only.",
        "risks_packet": "Condense blocker, review, and artifact references.",
    }
    for packet_name in active_packets:
        for agent_type in PACKET_WORKER_MAP.get(packet_name, []):
            pair = (agent_type, f"{packet_name}.json")
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            workers.append({"agent_type": agent_type, "packet": f"{packet_name}.json", "instruction": instructions.get(packet_name, "Read the assigned packet only.")})
    return workers


def focused_packet_contract(packet_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "packet_id": packet_id,
        "candidates": candidates,
        "footer": {
            "packet_ids": [packet_id],
            "candidate_ids": [candidate.get("candidate_id") for candidate in candidates],
            "primary_outcome": "",
            "overall_confidence": "",
            "coverage_gaps": [],
            "overall_risk": "",
        },
        "candidate_template": {
            "required_fields": CANDIDATE_REQUIRED_FIELDS,
            "field_bundles": CANDIDATE_FIELD_BUNDLES,
        },
        "worker_footer_fields": WORKER_FOOTER_FIELDS,
        "reread_reason_values": [None, *RAW_REREAD_REASONS],
        "domain_overlay": DOMAIN_OVERLAY,
    }


def validate_weekly_update_plan(context: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    missing_fields = [field for field in PLAN_REQUIRED_FIELDS if field not in plan]
    if missing_fields:
        errors.extend(f"weekly-update-plan.json is missing required field `{field}`." for field in missing_fields)
    if "overall_confidence" in plan and plan.get("overall_confidence") not in CONFIDENCE_VALUES:
        errors.append("weekly-update-plan.json has invalid `overall_confidence`.")
    if "stop_reasons" in plan and not isinstance(plan.get("stop_reasons"), list):
        errors.append("weekly-update-plan.json field `stop_reasons` must be a list.")
    if "allow_marker_update" in plan and not isinstance(plan.get("allow_marker_update"), bool):
        errors.append("weekly-update-plan.json field `allow_marker_update` must be a bool.")
    if "sections" in plan and not isinstance(plan.get("sections"), dict):
        errors.append("weekly-update-plan.json field `sections` must be an object keyed by final section name.")
    section_candidate_refs = iter_plan_section_candidate_ids(plan)
    sections = plan.get("sections")
    if isinstance(sections, dict):
        section_names = list(sections.keys())
        missing_sections = [section for section in OUTPUT_SECTIONS if section not in sections]
        unexpected_sections = [section for section in section_names if section not in OUTPUT_SECTIONS]
        if missing_sections:
            errors.append(f"weekly-update-plan.json is missing section keys: {', '.join(missing_sections)}.")
        if unexpected_sections:
            errors.append(f"weekly-update-plan.json has unexpected section keys: {', '.join(unexpected_sections)}.")
        if section_names and section_names != OUTPUT_SECTIONS:
            warnings.append("weekly-update-plan.json section order does not match the locked output order.")
        for section_name, payload in sections.items():
            if not isinstance(payload, (list, dict)):
                errors.append(f"Section `{section_name}` must be a list or an object with `items`.")
            elif isinstance(payload, dict) and "items" in payload and not isinstance(payload.get("items"), list):
                errors.append(f"Section `{section_name}` object must use a list-valued `items` field.")
    gate = apply_gate_summary(plan, context)
    if str(plan.get("context_id") or "") != str(context.get("context_id") or ""):
        errors.append("weekly-update-plan.json `context_id` does not match the collected context.")
    if str(plan.get("context_fingerprint") or "") != str(context.get("context_fingerprint") or ""):
        errors.append("weekly-update-plan.json `context_fingerprint` does not match the collected context.")
    if gate["allow_marker_update"] and gate["unresolved_raw_reread_candidate_ids"]:
        errors.append("allow_marker_update=true but unresolved raw reread candidates remain.")
    if gate["allow_marker_update"] and gate["overall_confidence"] == "low":
        errors.append("allow_marker_update=true is not permitted when overall_confidence=low.")
    candidate_lookup = {candidate["candidate_id"]: candidate for candidate in context.get("candidate_inventory") or []}
    artifact_only_refs: list[str] = []
    unknown_refs: list[str] = []
    for section_name, candidate_id in section_candidate_refs:
        candidate = candidate_lookup.get(candidate_id)
        if candidate is None:
            unknown_refs.append(candidate_id)
            continue
        if candidate.get("proposed_classification") == ARTIFACT_ONLY:
            artifact_only_refs.append(f"{section_name}:{candidate_id}")
    if artifact_only_refs:
        errors.append(
            "artifact_only candidates cannot appear as direct section items: "
            + ", ".join(artifact_only_refs)
            + "."
        )
    if unknown_refs:
        warnings.append("Section candidate references were not present in the collected context: " + ", ".join(stable_unique(unknown_refs)) + ".")
    info.append(f"Validated weekly-update plan against {len(candidate_lookup)} collected candidates.")
    return {
        "valid": not errors,
        "required_fields": PLAN_REQUIRED_FIELDS,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "overall_confidence": gate["overall_confidence"],
        "allow_marker_update": gate["allow_marker_update"],
        "stop_reasons": gate["stop_reasons"],
        "unresolved_raw_reread_candidate_ids": gate["unresolved_raw_reread_candidate_ids"],
        "artifact_only_section_candidate_ids": artifact_only_refs,
    }


def apply_plan(*, context: dict[str, Any], plan: dict[str, Any], state_file: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    repo_hash = str(context.get("repo_hash") or compute_repo_hash(Path(context["repo_root"])))
    resolved_state_file = (
        Path(state_file).resolve()
        if state_file
        else default_state_file(
            repo_hash,
            namespace=str(context.get("state_namespace") or DEFAULT_STATE_NAMESPACE),
        )
    )
    gate = apply_gate_summary(plan, context)
    overall_confidence = gate["overall_confidence"]
    unresolved = list(gate["unresolved_raw_reread_candidate_ids"])
    stop_reasons = list(gate["stop_reasons"])
    allow_marker_update = gate["allow_marker_update"]
    if unresolved and "unresolved raw reread exceptions remain" not in stop_reasons:
        stop_reasons.append("unresolved raw reread exceptions remain")
    if overall_confidence == "low" and "low confidence" not in stop_reasons:
        stop_reasons.append("low confidence")
    if not allow_marker_update and "allow_marker_update=false" not in stop_reasons:
        stop_reasons.append("allow_marker_update=false")
    marker_update_written = False
    marker_payload = {"repo_slug": context.get("repo_slug"), "window_start_utc": context.get("reporting_window", {}).get("start_utc"), "window_end_utc": context.get("reporting_window", {}).get("end_utc"), "completed_at_utc": isoformat_utc(utc_now()), "primary_ref_digest": str(context.get("head_sha") or "")[:12], "evidence_fingerprint": str(plan.get("context_fingerprint") or context.get("context_fingerprint") or "")}
    if not dry_run and allow_marker_update and overall_confidence != "low" and not unresolved and not stop_reasons:
        write_json(resolved_state_file, marker_payload)
        marker_update_written = True
    return {"skill_name": SKILL_NAME, "context_id": context.get("context_id"), "dry_run": dry_run, "apply_succeeded": True, "mutation_type": "state-marker" if marker_update_written else "none", "message": f"Wrote weekly-update state marker to {resolved_state_file}." if marker_update_written else "Did not update the weekly-update state marker.", "stop_reasons": stop_reasons, "overall_confidence": overall_confidence, "allow_marker_update": allow_marker_update, "marker_update_attempted": not dry_run and allow_marker_update, "marker_update_written": marker_update_written, "unresolved_raw_reread_candidate_ids": unresolved, "primary_artifact": str(resolved_state_file) if marker_update_written else None, "secondary_artifacts": [], "mutations": ([{"kind": "state-marker", "path": str(resolved_state_file)}] if marker_update_written else []), "fingerprint_match": str(plan.get("context_id") or context.get("context_id") or "") == str(context.get("context_id") or "") and str(plan.get("context_fingerprint") or context.get("context_fingerprint") or "") == str(context.get("context_fingerprint") or ""), "result_status": "dry-run" if dry_run else "completed"}




