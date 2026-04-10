#!/usr/bin/env python3
"""Shared evaluation-log helpers for packet-workflow retained skills."""

from __future__ import annotations

import argparse
import inspect
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "3.0"
SKILL_FAMILY = "repo-packet-workflow"
DEFAULT_FORMULA_VERSION = "3.0"
DEFAULT_MAIN_MODEL = "gpt-5.4"
DEFAULT_MAIN_REASONING_EFFORT = "xhigh"
DEFAULT_PRICING_SNAPSHOT_ID = "openai-2026-04-09"
DEFAULT_SPAWN_PLAN_SCHEMA_VERSION = "1.0"
ALLOWED_EXECUTION_CLASSES = {"required", "optional", "post_draft_qa"}
ALLOWED_SPAWN_STAGES = {"initial_parallel", "post_draft"}
ALLOWED_SPAWN_TRIGGERS = {
    "conflicting_worker_findings",
    "coverage_gap_after_synthesis",
    "high_risk_mutation_surface",
    "manual_local_escalation",
}
ALLOWED_ROW_KINDS = {"planned", "unplanned"}
ALLOWED_PLANNED_LEDGER_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "spawn_failed",
    "planned_not_run",
    "started",
}
ALLOWED_UNPLANNED_LEDGER_STATUSES = {
    "unplanned_completed",
    "unplanned_failed",
    "unplanned_cancelled",
    "unplanned_started",
}
ALLOWED_ACTUAL_STATUSES = {
    *ALLOWED_PLANNED_LEDGER_STATUSES,
    *ALLOWED_UNPLANNED_LEDGER_STATUSES,
}
PLANNED_EXECUTED_STATUSES = {"completed", "failed", "cancelled"}
UNPLANNED_STATUSES = set(ALLOWED_UNPLANNED_LEDGER_STATUSES)
ALLOWED_SPAWN_RESOLUTIONS = {
    "spawned",
    "local_fallback",
    "spawn_failed",
    "not_activated",
}
NONTERMINAL_ACTUAL_STATUSES = {"started", "unplanned_started"}


BuildBaseLogFn = Callable[
    [Path, dict[str, Any], dict[str, Any], dict[str, Any] | None],
    dict[str, Any],
]
ApplyPhaseUpdateFn = Callable[[dict[str, Any], str, dict[str, Any], float | None], None]


def foundry_root_dir() -> Path:
    return Path(__file__).resolve().parents[4]


def pricing_snapshot_path() -> Path:
    return (
        foundry_root_dir()
        / "core"
        / "defaults"
        / "packet-workflow"
        / "model-pricing.json"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime | None = None) -> str:
    return (value or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unknown"


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return None


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return None


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def stable_dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if key == "notes" and isinstance(value, list):
            base.setdefault("notes", [])
            base["notes"].extend(str(item) for item in value if str(item).strip())
            continue
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def parse_frontmatter(skill_root: Path) -> dict[str, str]:
    skill_md = skill_root / "SKILL.md"
    if not skill_md.is_file():
        return {"name": skill_root.name, "description": ""}
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"name": skill_root.name, "description": ""}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"name": skill_root.name, "description": ""}
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    metadata.setdefault("name", skill_root.name)
    metadata.setdefault("description", "")
    return metadata


def infer_archetype(skill_root: Path) -> str:
    script_dir = skill_root / "scripts"
    names = {path.name for path in script_dir.glob("*.py")}
    has_validate = any(name.startswith("validate_") for name in names)
    has_apply = any(name.startswith("apply_") for name in names) or "create_release_issue.py" in names
    if has_validate and has_apply:
        return "plan-validate-apply"
    if has_apply:
        return "audit-and-apply"
    return "audit-only"


def skill_identity(script_path: Path, *, skill_version: str = "unversioned") -> dict[str, str]:
    skill_root = script_path.resolve().parents[1]
    frontmatter = parse_frontmatter(skill_root)
    return {
        "name": frontmatter.get("name", skill_root.name),
        "family": SKILL_FAMILY,
        "archetype": infer_archetype(skill_root),
        "skill_version": skill_version,
        "skill_root": str(skill_root),
    }


def find_repo_name(context: dict[str, Any]) -> str | None:
    for key in ("repo_slug", "repo_name"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    pr = context.get("pr", {})
    url = str(pr.get("url") or "")
    match = re.search(r"github\.com/(?P<slug>[^/]+/[^/]+)/pull/\d+", url)
    return match.group("slug") if match else None


def default_find_branch(context: dict[str, Any]) -> str | None:
    branch = str(context.get("branch") or "").strip()
    if branch:
        return branch
    branch_state = context.get("branch_state") or {}
    branch = str(branch_state.get("branch") or "").strip()
    if branch:
        return branch
    pr = context.get("pr", {})
    return str(pr.get("headRefName") or "").strip() or None


def default_find_head_sha(context: dict[str, Any]) -> str | None:
    for key in ("head_sha", "head_commit"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    pr = context.get("pr", {})
    return str(pr.get("headRefOid") or "").strip() or None


def default_find_base_ref(context: dict[str, Any]) -> str | None:
    for key in ("base_ref", "base_tag", "base_commit"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    pr = context.get("pr", {})
    return str(pr.get("baseRefName") or "").strip() or None


def default_packet_files(orchestrator: dict[str, Any]) -> list[str]:
    explicit = [
        str(item)
        for item in orchestrator.get("packet_files", [])
        if str(item).strip()
    ]
    if explicit:
        return explicit
    packet_order = [
        str(item)
        for item in orchestrator.get("packet_order", [])
        if str(item).strip()
    ]
    if packet_order:
        return packet_order
    derived: list[str] = []
    shared_packet = str(orchestrator.get("shared_packet") or "").strip()
    if shared_packet:
        derived.append(shared_packet)
    shared_local_packet = str(orchestrator.get("shared_local_packet") or "").strip()
    if shared_local_packet:
        derived.append(shared_local_packet)
    for item in orchestrator.get("selected_packets", []):
        name = str(item or "").strip()
        if not name:
            continue
        derived.append(name if name.endswith(".json") else f"{name}.json")
    return stable_dedupe(derived)


def item_packet_count(
    orchestrator: dict[str, Any],
    *,
    packet_files_fn: Callable[[dict[str, Any]], list[str]] = default_packet_files,
) -> int:
    shared = {"global_packet.json", "rules_packet.json", "orchestrator.json"}
    count = 0
    for name in packet_files_fn(orchestrator):
        lowered = name.lower()
        if (
            lowered in shared
            or "batch-packet" in lowered
            or "candidate-batch" in lowered
            or lowered.startswith("batch-")
        ):
            continue
        count += 1
    return count


def batch_packet_count(
    orchestrator: dict[str, Any],
    *,
    packet_files_fn: Callable[[dict[str, Any]], list[str]] = default_packet_files,
) -> int:
    return sum(
        1
        for name in packet_files_fn(orchestrator)
        if "batch-packet" in name.lower()
        or "candidate-batch" in name.lower()
        or name.lower().startswith("batch-")
    )


def active_area_count(context: dict[str, Any], orchestrator: dict[str, Any]) -> int:
    for key in ("active_areas", "active_groups"):
        value = orchestrator.get(key)
        if isinstance(value, list):
            return len(value)
    counts = context.get("counts", {})
    detected = safe_int(counts.get("active_areas"))
    return detected or 0


def changed_file_count(context: dict[str, Any], orchestrator: dict[str, Any]) -> int:
    if isinstance(context.get("changed_files"), list):
        return len(context["changed_files"])
    if isinstance(context.get("files"), list):
        return len(context["files"])
    counts = context.get("counts", {})
    if safe_int(counts.get("changed_files")) is not None:
        return int(counts["changed_files"])
    diff_summary = orchestrator.get("diff_summary", {})
    return safe_int(diff_summary.get("changed_file_count")) or 0


def untracked_file_count(context: dict[str, Any]) -> int:
    if isinstance(context.get("files"), list):
        return sum(
            1
            for entry in context["files"]
            if str(entry.get("change_kind") or "") == "untracked"
        )
    return safe_int(context.get("untracked_files")) or 0


def diff_churn(orchestrator: dict[str, Any], context: dict[str, Any]) -> int:
    diff_summary = orchestrator.get("diff_summary", {})
    totals = diff_summary.get("diff_stat_totals") or {}
    if safe_int(totals.get("churn")) is not None:
        return int(totals["churn"])
    totals = context.get("diff_stat_totals") or {}
    return safe_int(totals.get("churn")) or 0


def normalize_override_signals(payload: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()
    raw = payload.get("override_signals")
    if isinstance(raw, dict):
        for key, value in raw.items():
            reason = str(key).strip()
            if bool(value) and reason and reason not in seen:
                seen.add(reason)
                signals.append(reason)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                reason = str(item.get("reason") or "").strip()
            else:
                reason = str(item or "").strip()
            if reason and reason not in seen:
                seen.add(reason)
                signals.append(reason)
    for key in ("review_mode_overrides", "review_overrides", "applied_override_signals"):
        for item in payload.get(key, []):
            if isinstance(item, dict):
                reason = str(item.get("reason") or "").strip()
            else:
                reason = str(item or "").strip()
            if reason and reason not in seen:
                seen.add(reason)
                signals.append(reason)
    return signals


def count_messages(findings: dict[str, Any], *keys: str) -> list[str]:
    messages: list[str] = []
    for key in keys:
        value = findings.get(key)
        if isinstance(value, list):
            messages.extend(str(item) for item in value if str(item).strip())
    return messages


def summarize_findings(lint_report: dict[str, Any] | None) -> dict[str, Any]:
    if lint_report is None:
        findings = {}
    elif "findings" in lint_report and isinstance(lint_report.get("findings"), dict):
        findings = lint_report["findings"]
    else:
        findings = lint_report
    messages = count_messages(findings, "errors", "warnings", "info", "infos")
    unsupported = [
        message for message in messages if "unsupported claim" in message.lower()
    ]
    evidence = [
        message
        for message in messages
        if any(
            token in message.lower()
            for token in ("evidence", "tested", "testing", "verification", "command")
        )
    ]
    template = [
        message
        for message in messages
        if any(
            token in message.lower()
            for token in (
                "template",
                "section",
                "placeholder",
                "blank bullet",
                "body contains",
            )
        )
    ]
    return {
        "messages": messages,
        "unsupported_claims_found": len(unsupported),
        "evidence_gaps_found": len(evidence),
        "template_violations_found": len(template),
    }


def derive_run_id(
    skill_name: str,
    context: dict[str, Any],
    *,
    find_head_sha_fn: Callable[[dict[str, Any]], str | None] = default_find_head_sha,
) -> tuple[str, str]:
    timestamp = isoformat_utc()
    ref = (
        find_head_sha_fn(context)
        or context.get("context_id")
        or context.get("run_id")
        or "nohead"
    )
    return f"{timestamp}__{skill_name}__{slugify(str(ref))[:16]}", timestamp


def safe_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "-", value).strip(" .")
    return sanitized or "evaluation-log"


def default_output_path(repo_root: Any, skill_name: str, run_id: str) -> Path:
    repo_root_text = str(repo_root) if repo_root is not None else ""
    repo_path = Path(repo_root_text) if repo_root_text else Path(".").resolve()
    return (
        repo_path
        / ".codex"
        / "tmp"
        / "evaluation_logs"
        / skill_name
        / f"{safe_filename(run_id)}.json"
    )


def json_bytes(payload: Any) -> int:
    return len(
        (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    )


def estimate_tokens_from_bytes(byte_count: int | None) -> int | None:
    if byte_count is None:
        return None
    if byte_count <= 0:
        return 0
    return max(1, (byte_count + 3) // 4)


def pricing_snapshot() -> dict[str, Any]:
    try:
        payload = load_json(pricing_snapshot_path())
        if isinstance(payload, dict):
            return payload
    except FileNotFoundError:
        pass
    return {
        "schema_version": "1.0",
        "snapshot_id": DEFAULT_PRICING_SNAPSHOT_ID,
        "models": [],
    }


def pricing_snapshot_id() -> str:
    return str(pricing_snapshot().get("snapshot_id") or DEFAULT_PRICING_SNAPSHOT_ID)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def json_fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def orchestrator_fingerprint(payload: dict[str, Any]) -> str:
    filtered = {
        key: value
        for key, value in payload.items()
        if key != "orchestrator_fingerprint"
    }
    return json_fingerprint(filtered)


def mirrored_orchestrator_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "actual_workers",
            "planned_workers",
            "spawn_activation",
            "global_packet_used",
            "raw_reread_required",
            "override_signals",
        }
    }


def packet_list_from_worker(worker: dict[str, Any]) -> list[str]:
    packets = worker.get("packets")
    if isinstance(packets, list):
        values = [str(item).strip() for item in packets if str(item).strip()]
    else:
        packet = str(worker.get("packet") or "").strip()
        values = [packet] if packet else []
    normalized = []
    for value in values:
        normalized.append(value if value.endswith(".json") else f"{value}.json")
    return stable_dedupe(sorted(normalized))


def canonical_worker_identity_tuple(
    worker: dict[str, Any],
) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        str(worker.get("name") or "").strip(),
        str(worker.get("agent_type") or "").strip(),
        str(worker.get("model") or "").strip(),
        str(worker.get("reasoning_effort") or "").strip(),
        tuple(packet_list_from_worker(worker)),
    )


def planned_worker_id(worker: dict[str, Any]) -> str:
    packets = packet_list_from_worker(worker)
    digest = short_hash(
        canonical_json(
            {
                "model": str(worker.get("model") or "").strip(),
                "reasoning_effort": str(worker.get("reasoning_effort") or "").strip(),
                "sorted_packets": packets,
            }
        )
    )
    return (
        f"planned:{slugify(worker.get('name'))}:"
        f"{slugify(worker.get('agent_type'))}:{digest}"
    )


def normalize_planned_worker(
    worker: dict[str, Any],
    *,
    default_name: str | None = None,
    default_model: str = "gpt-5.4-mini",
    default_reasoning_effort: str = "medium",
) -> dict[str, Any]:
    packets = packet_list_from_worker(worker)
    agent_type = str(worker.get("agent_type") or "").strip()
    name = str(worker.get("name") or default_name or "").strip()
    if not name and agent_type and packets:
        name = f"{Path(packets[0]).stem}-{agent_type}"
    if not name and agent_type:
        name = agent_type
    normalized = {
        "name": name,
        "agent_type": agent_type,
        "model": str(worker.get("model") or default_model).strip(),
        "reasoning_effort": str(
            worker.get("reasoning_effort") or default_reasoning_effort
        ).strip(),
        "packets": packets,
        "responsibility": (
            str(worker.get("responsibility") or worker.get("instruction") or "").strip()
            or None
        ),
    }
    if not normalized["name"]:
        raise ValueError("planned worker requires `name`")
    if not normalized["agent_type"]:
        raise ValueError(f"planned worker `{normalized['name']}` requires `agent_type`")
    normalized["worker_id"] = planned_worker_id(normalized)
    return normalized


def normalize_planned_workers_payload(
    workers: Any,
    *,
    default_model: str = "gpt-5.4-mini",
    default_reasoning_effort: str = "medium",
) -> tuple[dict[str, Any], list[str]]:
    items = workers if isinstance(workers, list) else []
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_identity: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    seen_names: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        default_name = None
        packets = packet_list_from_worker(item)
        if packets and item.get("agent_type"):
            default_name = f"{Path(packets[0]).stem}-{item.get('agent_type')}"
        worker = normalize_planned_worker(
            item,
            default_name=default_name,
            default_model=default_model,
            default_reasoning_effort=default_reasoning_effort,
        )
        identity = canonical_worker_identity_tuple(worker)
        if identity in seen_identity:
            raise ValueError(
                "Duplicate planned worker identity tuple at index "
                f"{index}: {worker['name']} / {worker['agent_type']}"
            )
        seen_identity.add(identity)
        if worker["name"] in seen_names:
            warnings.append(
                f"Duplicate planned worker name allowed with warning only: {worker['name']}"
            )
        seen_names.add(worker["name"])
        normalized.append(worker)
    return (
        {
            "count": len(normalized),
            "roles": stable_dedupe([worker["agent_type"] for worker in normalized]),
            "workers": normalized,
        },
        warnings,
    )


def packet_size_breakdown(packet_metrics: dict[str, Any]) -> dict[str, int]:
    direct_breakdown = packet_metrics.get("packet_size_breakdown")
    if isinstance(direct_breakdown, dict):
        return {
            str(key): int(value)
            for key, value in direct_breakdown.items()
            if safe_int(value) is not None
        }
    breakdown = packet_metrics.get("packet_size_by_file")
    if isinstance(breakdown, dict):
        return {
            str(key): int(value)
            for key, value in breakdown.items()
            if safe_int(value) is not None
        }
    packet_sizes = packet_metrics.get("packet_size_bytes")
    if isinstance(packet_sizes, dict):
        return {
            str(key): int(value)
            for key, value in packet_sizes.items()
            if safe_int(value) is not None and str(key).endswith(".json")
        }
    return {}


def normalize_packet_sizing(packet_metrics: dict[str, Any] | None) -> dict[str, Any]:
    metrics = packet_metrics if isinstance(packet_metrics, dict) else {}
    packet_size_bytes = metrics.get("packet_size_bytes")
    packet_size_total = safe_int(packet_size_bytes)
    return {
        "packet_count": safe_int(metrics.get("packet_count")),
        "packet_size_bytes": packet_size_total,
        "largest_packet_bytes": safe_int(metrics.get("largest_packet_bytes")),
        "largest_two_packets_bytes": safe_int(metrics.get("largest_two_packets_bytes")),
        "packet_size_breakdown": packet_size_breakdown(metrics) or None,
    }


def packet_compaction_metrics(packet_metrics: dict[str, Any] | None) -> dict[str, int | None]:
    metrics = packet_metrics if isinstance(packet_metrics, dict) else {}
    local_only_tokens = safe_int(metrics.get("local_only_tokens"))
    if local_only_tokens is None:
        local_only_tokens = safe_int(metrics.get("estimated_local_only_tokens"))
    packet_tokens = safe_int(metrics.get("packet_tokens"))
    if packet_tokens is None:
        packet_tokens = safe_int(metrics.get("estimated_packet_tokens"))
    savings_tokens = safe_int(metrics.get("savings_tokens"))
    if savings_tokens is None:
        savings_tokens = safe_int(metrics.get("estimated_delegation_savings"))
    if (
        savings_tokens is None
        and local_only_tokens is not None
        and packet_tokens is not None
    ):
        savings_tokens = max(0, local_only_tokens - packet_tokens)
    return {
        "local_only_tokens": local_only_tokens,
        "packet_tokens": packet_tokens,
        "savings_tokens": savings_tokens,
    }


def find_pricing_entry(model_name: Any) -> dict[str, Any] | None:
    model = str(model_name or "").strip()
    if not model:
        return None
    snapshot = pricing_snapshot()
    for item in snapshot.get("models", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("canonical_model_id") or "").strip() == model:
            return item
        aliases = [str(alias).strip() for alias in item.get("aliases", [])]
        if model in aliases:
            return item
    return None


def cost_from_tokens(
    *,
    model_name: Any,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None,
) -> dict[str, Any]:
    entry = find_pricing_entry(model_name)
    if entry is None:
        return {
            "input_cost_nanousd": None,
            "cached_input_cost_nanousd": None,
            "output_cost_nanousd": None,
            "reasoning_cost_nanousd": None,
            "total_cost_nanousd": None,
            "cost_provenance": "unavailable",
        }
    total_input = input_tokens or 0
    cached_input = cached_input_tokens or 0
    uncached_input = max(0, total_input - cached_input)
    cached_rate = safe_int(entry.get("cached_input_nanousd_per_token"))
    if cached_input and cached_rate is None:
        return {
            "input_cost_nanousd": None,
            "cached_input_cost_nanousd": None,
            "output_cost_nanousd": None,
            "reasoning_cost_nanousd": None,
            "total_cost_nanousd": None,
            "cost_provenance": "unavailable",
        }
    input_rate = safe_int(entry.get("input_nanousd_per_token")) or 0
    output_rate = safe_int(entry.get("output_nanousd_per_token")) or 0
    reasoning_rate = safe_int(entry.get("reasoning_nanousd_per_token")) or output_rate
    input_cost = uncached_input * input_rate if input_tokens is not None else None
    cached_cost = (
        cached_input * cached_rate
        if cached_input_tokens is not None and cached_rate is not None
        else (0 if cached_input_tokens == 0 else None)
    )
    output_cost = (output_tokens or 0) * output_rate if output_tokens is not None else None
    reasoning_cost = (
        (reasoning_tokens or 0) * reasoning_rate
        if reasoning_tokens is not None
        else None
    )
    components = [
        value
        for value in (input_cost, cached_cost, output_cost, reasoning_cost)
        if value is not None
    ]
    total_cost = sum(components) if components else None
    return {
        "input_cost_nanousd": input_cost,
        "cached_input_cost_nanousd": cached_cost,
        "output_cost_nanousd": output_cost,
        "reasoning_cost_nanousd": reasoning_cost,
        "total_cost_nanousd": total_cost,
        "cost_provenance": "measured" if total_cost is not None else "unavailable",
    }


def actor_with_costs(
    actor: dict[str, Any],
    *,
    default_model: str | None = None,
    default_reasoning_effort: str | None = None,
    default_identity_provenance: str | None = None,
) -> dict[str, Any]:
    normalized = dict(actor)
    if default_model and not str(normalized.get("model") or "").strip():
        normalized["model"] = default_model
    if (
        default_reasoning_effort
        and not str(normalized.get("reasoning_effort") or "").strip()
    ):
        normalized["reasoning_effort"] = default_reasoning_effort
    if default_identity_provenance and not normalized.get("identity_provenance"):
        normalized["identity_provenance"] = default_identity_provenance
    normalized.setdefault("input_tokens", None)
    normalized.setdefault("cached_input_tokens", None)
    normalized.setdefault("output_tokens", None)
    normalized.setdefault("reasoning_tokens", None)
    normalized.update(
        cost_from_tokens(
            model_name=normalized.get("model"),
            input_tokens=safe_int(normalized.get("input_tokens")),
            cached_input_tokens=safe_int(normalized.get("cached_input_tokens")),
            output_tokens=safe_int(normalized.get("output_tokens")),
            reasoning_tokens=safe_int(normalized.get("reasoning_tokens")),
        )
    )
    return normalized


def packet_compaction_efficiency(
    packet_metrics: dict[str, Any] | None,
    *,
    main_model_name: str = DEFAULT_MAIN_MODEL,
) -> dict[str, Any]:
    compaction = packet_compaction_metrics(packet_metrics)
    local_only_tokens = compaction.get("local_only_tokens")
    packet_tokens = compaction.get("packet_tokens")
    savings_tokens = compaction.get("savings_tokens")
    price = find_pricing_entry(main_model_name)
    input_rate = safe_int((price or {}).get("input_nanousd_per_token"))
    main_model_input_cost = (
        savings_tokens * input_rate
        if savings_tokens is not None and input_rate is not None
        else None
    )
    provenance = (
        "estimated"
        if local_only_tokens is not None and packet_tokens is not None
        else "unavailable"
    )
    return {
        "local_only_tokens": local_only_tokens,
        "packet_tokens": packet_tokens,
        "savings_tokens": savings_tokens,
        "main_model_input_cost_nanousd": main_model_input_cost,
        "provenance": provenance,
        "pricing_snapshot_id": pricing_snapshot_id(),
    }


def estimated_delegation_gross_from_planned_workers(
    planned_workers: dict[str, Any] | None,
    packet_metrics: dict[str, Any] | None,
    *,
    main_model_name: str,
) -> tuple[int | None, str]:
    workers = (
        ((planned_workers or {}).get("workers") or [])
        if isinstance(planned_workers, dict)
        else []
    )
    breakdown = packet_size_breakdown(packet_metrics or {})
    if not workers or not breakdown:
        return None, "unavailable"
    entry = find_pricing_entry(main_model_name)
    input_rate = safe_int((entry or {}).get("input_nanousd_per_token"))
    if input_rate is None:
        return None, "unavailable"
    total_tokens = 0
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        for packet_name in packet_list_from_worker(worker):
            if packet_name in breakdown:
                total_tokens += estimate_tokens_from_bytes(breakdown[packet_name]) or 0
    if total_tokens <= 0:
        return None, "unavailable"
    return total_tokens * input_rate, "estimated"


def total_actor_cost(actor: dict[str, Any]) -> int | None:
    return safe_int(actor.get("total_cost_nanousd"))


def main_model_repriced_cost_for_actor(
    actor: dict[str, Any],
    main_model_name: Any,
) -> int | None:
    repriced = cost_from_tokens(
        model_name=main_model_name,
        input_tokens=safe_int(actor.get("input_tokens")),
        cached_input_tokens=safe_int(actor.get("cached_input_tokens")),
        output_tokens=safe_int(actor.get("output_tokens")),
        reasoning_tokens=safe_int(actor.get("reasoning_tokens")),
    )
    return safe_int(repriced.get("total_cost_nanousd"))


def delegation_efficiency(
    *,
    planned_workers: dict[str, Any] | None,
    packet_metrics: dict[str, Any] | None,
    main_model: dict[str, Any],
    subagents: list[dict[str, Any]],
) -> dict[str, Any]:
    gross_avoided: int | None = None
    gross_provenance = "unavailable"
    main_model_name = main_model.get("model")
    if subagents:
        values = [
            main_model_repriced_cost_for_actor(actor, main_model_name)
            for actor in subagents
            if isinstance(actor, dict)
        ]
        measured = [value for value in values if value is not None]
        if measured:
            gross_avoided = sum(measured)
            gross_provenance = "measured"
    if gross_avoided is None:
        gross_avoided, gross_provenance = estimated_delegation_gross_from_planned_workers(
            planned_workers,
            packet_metrics,
            main_model_name=str(main_model_name or DEFAULT_MAIN_MODEL),
        )

    overhead_values = [
        total_actor_cost(actor) for actor in subagents if isinstance(actor, dict)
    ]
    measured_overhead = [value for value in overhead_values if value is not None]
    overhead = sum(measured_overhead) if measured_overhead else None
    overhead_provenance = "measured" if overhead is not None else "unavailable"
    if (
        gross_avoided is not None
        and overhead is not None
        and gross_provenance == "measured"
    ):
        net = gross_avoided - overhead
        net_provenance = "measured"
    else:
        net = None
        net_provenance = "unavailable"
    return {
        "gross_avoided_main_cost_nanousd": gross_avoided,
        "delegation_overhead_cost_nanousd": overhead,
        "net_savings_cost_nanousd": net,
        "gross_avoided_provenance": gross_provenance,
        "overhead_provenance": overhead_provenance,
        "net_provenance": net_provenance,
        "pricing_snapshot_id": pricing_snapshot_id(),
    }


def combined_efficiency(
    packet_compaction: dict[str, Any],
    model_tier_delegation: dict[str, Any],
) -> dict[str, Any]:
    packet_cost = safe_int(packet_compaction.get("main_model_input_cost_nanousd"))
    delegation_cost = safe_int(
        model_tier_delegation.get("net_savings_cost_nanousd")
    )
    total_net = (
        packet_cost + delegation_cost
        if packet_cost is not None and delegation_cost is not None
        else None
    )
    return {
        "packet_compaction_cost_nanousd": packet_cost,
        "delegation_net_cost_nanousd": delegation_cost,
        "total_net_cost_nanousd": total_net,
        "component_provenance": {
            "packet_compaction": packet_compaction.get("provenance"),
            "delegation_net": model_tier_delegation.get("net_provenance"),
        },
    }


def build_efficiency_payload(
    packet_metrics: dict[str, Any] | None,
    *,
    planned_workers: dict[str, Any] | None = None,
    main_model: dict[str, Any] | None = None,
    subagents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_main = actor_with_costs(
        main_model or {},
        default_model=DEFAULT_MAIN_MODEL,
        default_reasoning_effort=DEFAULT_MAIN_REASONING_EFFORT,
        default_identity_provenance="assumed_default",
    )
    resolved_subagents = [
        actor_with_costs(actor)
        for actor in (subagents or [])
        if isinstance(actor, dict)
    ]
    packet_compaction = packet_compaction_efficiency(
        packet_metrics,
        main_model_name=str(resolved_main.get("model") or DEFAULT_MAIN_MODEL),
    )
    model_tier = delegation_efficiency(
        planned_workers=planned_workers,
        packet_metrics=packet_metrics,
        main_model=resolved_main,
        subagents=resolved_subagents,
    )
    return {
        "packet_compaction": packet_compaction,
        "model_tier_delegation": model_tier,
        "combined": combined_efficiency(packet_compaction, model_tier),
    }


def empty_planned_workers() -> dict[str, Any]:
    return {"count": 0, "roles": [], "workers": []}


def default_spawn_retry_policy() -> dict[str, Any]:
    return {
        "required_spawn_retries": 1,
        "optional_spawn_retries": 0,
        "post_draft_qa_spawn_retries": 1,
        "substitute_worker_on_failure": False,
    }


def empty_spawn_activation_summary() -> dict[str, Any]:
    return {
        "attempted_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "local_fallback_count": 0,
        "not_activated_count": 0,
    }


def empty_spawn_activation() -> dict[str, Any]:
    return {
        "activated_worker_ids": [],
        "skipped_worker_ids": [],
        "local_fallback_worker_ids": [],
        "trigger_events": [],
        "summary": empty_spawn_activation_summary(),
        "workers": [],
        "drift_events": [],
    }


def empty_spawn_plan() -> dict[str, Any]:
    return {
        "schema_version": DEFAULT_SPAWN_PLAN_SCHEMA_VERSION,
        "routing_authority": "packet_worker_map",
        "default_spawn_enabled": False,
        "default_spawn_blockers": [],
        "retry_policy": default_spawn_retry_policy(),
        "workers": [],
    }


def default_activation_triggers(execution_class: str) -> list[str]:
    if execution_class == "post_draft_qa":
        return [
            "conflicting_worker_findings",
            "coverage_gap_after_synthesis",
            "high_risk_mutation_surface",
            "manual_local_escalation",
        ]
    if execution_class == "optional":
        return ["manual_local_escalation"]
    return []


def execution_defaults(
    execution_class: str,
    stage: str,
) -> tuple[bool, bool]:
    if execution_class == "required" and stage == "initial_parallel":
        return True, True
    if execution_class == "optional" and stage == "initial_parallel":
        return False, False
    if execution_class == "post_draft_qa":
        return True, False
    return False, False


def normalize_spawn_trigger_list(
    value: Any,
    *,
    execution_class: str,
) -> list[str]:
    triggers = stable_dedupe(list_of_strings(value))
    if not triggers:
        triggers = default_activation_triggers(execution_class)
    return [trigger for trigger in triggers if trigger in ALLOWED_SPAWN_TRIGGERS]


def legacy_optional_worker_to_dict(worker: Any, *, index: int) -> dict[str, Any] | None:
    if isinstance(worker, dict):
        return dict(worker)
    agent_type = str(worker or "").strip()
    if not agent_type:
        return None
    return {
        "name": f"optional-{slugify(agent_type)}-{index}",
        "agent_type": agent_type,
        "packets": ["global_packet.json"],
        "reasoning_effort": "medium",
        "model": "gpt-5.4-mini",
        "responsibility": None,
        "execution_class": "optional",
        "stage": "initial_parallel",
    }


def infer_optional_execution_class(worker: dict[str, Any]) -> str:
    explicit = str(worker.get("execution_class") or "").strip()
    if explicit in ALLOWED_EXECUTION_CLASSES:
        return explicit
    stage = str(worker.get("stage") or "").strip()
    if stage == "post_draft":
        return "post_draft_qa"
    signal_text = " ".join(
        str(worker.get(key) or "")
        for key in ("name", "responsibility", "when")
    ).lower()
    if any(
        token in signal_text
        for token in ("qa", "cross-check", "coverage", "compare", "unsupported")
    ):
        return "post_draft_qa"
    return "optional"


def normalize_spawn_plan_worker(
    worker: dict[str, Any],
    *,
    default_execution_class: str = "required",
    default_model: str = "gpt-5.4-mini",
    default_reasoning_effort: str = "medium",
) -> dict[str, Any]:
    normalized = normalize_planned_worker(
        worker,
        default_model=default_model,
        default_reasoning_effort=default_reasoning_effort,
    )
    execution_class = str(
        worker.get("execution_class") or default_execution_class
    ).strip()
    if execution_class not in ALLOWED_EXECUTION_CLASSES:
        execution_class = default_execution_class
    default_stage = "post_draft" if execution_class == "post_draft_qa" else "initial_parallel"
    stage = str(worker.get("stage") or default_stage).strip()
    if stage not in ALLOWED_SPAWN_STAGES:
        stage = default_stage
    default_blocking, default_spawn = execution_defaults(execution_class, stage)
    blocking = to_bool(worker.get("blocking"))
    if blocking is None:
        blocking = default_blocking
    spawn_by_default = to_bool(worker.get("default_spawn"))
    if spawn_by_default is None:
        spawn_by_default = default_spawn
    normalized["execution_class"] = execution_class
    normalized["stage"] = stage
    normalized["blocking"] = bool(blocking)
    normalized["default_spawn"] = bool(spawn_by_default)
    normalized["activation_triggers"] = normalize_spawn_trigger_list(
        worker.get("activation_triggers"),
        execution_class=execution_class,
    )
    return normalized


def spawn_plan_enabled_and_blockers(
    *,
    review_mode: Any = None,
    common_path_sufficient: Any = None,
    explicit_local_only_safety_gate: Any = None,
    workers: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if str(review_mode or "").strip() == "local-only":
        blockers.append("review_mode=local-only")
    if common_path_sufficient is False:
        blockers.append("common_path_sufficient=false")
    if to_bool(explicit_local_only_safety_gate):
        blockers.append("explicit_local_only_safety_gate")
    enabled = not blockers and any(
        bool(worker.get("default_spawn")) for worker in (workers or [])
    )
    return enabled, blockers


def normalize_retry_policy(value: Any) -> dict[str, Any]:
    normalized = default_spawn_retry_policy()
    if not isinstance(value, dict):
        return normalized
    for key in (
        "required_spawn_retries",
        "optional_spawn_retries",
        "post_draft_qa_spawn_retries",
    ):
        count = safe_int(value.get(key))
        if count is not None and count >= 0:
            normalized[key] = count
    substitute = to_bool(value.get("substitute_worker_on_failure"))
    if substitute is not None:
        normalized["substitute_worker_on_failure"] = substitute
    return normalized


def normalize_spawn_plan_payload(
    spawn_plan: Any,
    *,
    review_mode: Any = None,
    common_path_sufficient: Any = None,
    explicit_local_only_safety_gate: Any = None,
) -> tuple[dict[str, Any], list[str]]:
    payload = spawn_plan if isinstance(spawn_plan, dict) else {}
    warnings = list_of_strings(payload.get("warnings"))
    workers = payload.get("workers")
    items = workers if isinstance(workers, list) else []
    normalized_workers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_identity: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    seen_names: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        worker = normalize_spawn_plan_worker(item)
        identity = canonical_worker_identity_tuple(worker)
        if identity in seen_identity:
            raise ValueError(
                "Duplicate spawn-plan worker identity tuple at index "
                f"{index}: {worker['name']} / {worker['agent_type']}"
            )
        seen_identity.add(identity)
        if worker["worker_id"] in seen_ids:
            raise ValueError(
                f"Duplicate spawn-plan worker_id at index {index}: {worker['worker_id']}"
            )
        seen_ids.add(worker["worker_id"])
        if worker["name"] in seen_names:
            warnings.append(
                f"Duplicate spawn worker name allowed with warning only: {worker['name']}"
            )
        seen_names.add(worker["name"])
        normalized_workers.append(worker)
    enabled, blockers = spawn_plan_enabled_and_blockers(
        review_mode=review_mode,
        common_path_sufficient=common_path_sufficient,
        explicit_local_only_safety_gate=explicit_local_only_safety_gate,
        workers=normalized_workers,
    )
    default_spawn_enabled = to_bool(payload.get("default_spawn_enabled"))
    if default_spawn_enabled is None:
        default_spawn_enabled = enabled
    normalized_blockers = stable_dedupe(
        list_of_strings(payload.get("default_spawn_blockers")) or blockers
    )
    return (
        {
            "schema_version": (
                str(payload.get("schema_version") or DEFAULT_SPAWN_PLAN_SCHEMA_VERSION).strip()
                or DEFAULT_SPAWN_PLAN_SCHEMA_VERSION
            ),
            "routing_authority": "packet_worker_map",
            "default_spawn_enabled": bool(default_spawn_enabled),
            "default_spawn_blockers": normalized_blockers,
            "retry_policy": normalize_retry_policy(payload.get("retry_policy")),
            "workers": normalized_workers,
        },
        warnings,
    )


def build_spawn_plan(
    *,
    review_mode: Any,
    required_workers: list[dict[str, Any]] | None = None,
    optional_workers: list[dict[str, Any]] | None = None,
    post_draft_qa_workers: list[dict[str, Any]] | None = None,
    common_path_sufficient: bool = True,
    explicit_local_only_safety_gate: bool = False,
    retry_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    combined: list[dict[str, Any]] = []
    for worker in required_workers or []:
        if not isinstance(worker, dict):
            continue
        combined.append(
            {
                **worker,
                "execution_class": "required",
                "stage": "initial_parallel",
                "blocking": True,
                "default_spawn": True,
                "activation_triggers": [],
            }
        )
    for worker in optional_workers or []:
        optional = worker if isinstance(worker, dict) else legacy_optional_worker_to_dict(worker, index=len(combined) + 1)
        if not isinstance(optional, dict):
            continue
        execution_class = infer_optional_execution_class(optional)
        combined.append(
            {
                **optional,
                "execution_class": execution_class,
                "stage": optional.get("stage")
                or ("post_draft" if execution_class == "post_draft_qa" else "initial_parallel"),
            }
        )
    for worker in post_draft_qa_workers or []:
        if not isinstance(worker, dict):
            continue
        combined.append(
            {
                **worker,
                "execution_class": "post_draft_qa",
                "stage": "post_draft",
                "blocking": True,
                "default_spawn": False,
            }
        )
    normalized, _warnings = normalize_spawn_plan_payload(
        {
            "schema_version": DEFAULT_SPAWN_PLAN_SCHEMA_VERSION,
            "routing_authority": "packet_worker_map",
            "retry_policy": retry_policy or default_spawn_retry_policy(),
            "workers": combined,
        },
        review_mode=review_mode,
        common_path_sufficient=common_path_sufficient,
        explicit_local_only_safety_gate=explicit_local_only_safety_gate,
    )
    return normalized


def default_planned_workers_from_spawn_plan(
    spawn_plan: dict[str, Any],
) -> dict[str, Any]:
    workers = [
        worker
        for worker in spawn_plan.get("workers", [])
        if isinstance(worker, dict)
        and bool(spawn_plan.get("default_spawn_enabled"))
        and bool(worker.get("default_spawn"))
    ]
    return {
        "count": len(workers),
        "roles": stable_dedupe(
            [str(worker.get("agent_type") or "").strip() for worker in workers]
        ),
        "workers": workers,
    }


def has_spawn_plan_workers(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    workers = value.get("workers")
    return isinstance(workers, list) and any(isinstance(item, dict) for item in workers)


def has_legacy_worker_payload(payload: dict[str, Any]) -> bool:
    planned = payload.get("planned_workers")
    if isinstance(planned, dict):
        workers = planned.get("workers")
        if isinstance(workers, list) and any(isinstance(item, dict) for item in workers):
            return True
    for key in ("recommended_workers", "optional_workers"):
        workers = payload.get(key)
        if isinstance(workers, list) and any(
            isinstance(item, dict) or str(item or "").strip() for item in workers
        ):
            return True
    return False


def spawn_plan_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    common_path_sufficient = to_bool(payload.get("common_path_sufficient"))
    spawn_plan = payload.get("spawn_plan")
    if isinstance(spawn_plan, dict) and (
        has_spawn_plan_workers(spawn_plan) or not has_legacy_worker_payload(payload)
    ):
        return normalize_spawn_plan_payload(
            spawn_plan,
            review_mode=payload.get("review_mode"),
            common_path_sufficient=common_path_sufficient,
            explicit_local_only_safety_gate=payload.get("explicit_local_only_safety_gate"),
        )
    spawn_plan_preview = payload.get("spawn_plan_preview")
    if isinstance(spawn_plan_preview, dict) and (
        has_spawn_plan_workers(spawn_plan_preview) or not has_legacy_worker_payload(payload)
    ):
        return normalize_spawn_plan_payload(
            spawn_plan_preview,
            review_mode=payload.get("review_mode"),
            common_path_sufficient=common_path_sufficient,
            explicit_local_only_safety_gate=payload.get("explicit_local_only_safety_gate"),
        )
    legacy_required = []
    if isinstance(payload.get("planned_workers"), dict):
        legacy_required = (payload.get("planned_workers") or {}).get("workers") or []
    elif isinstance(payload.get("recommended_workers"), list):
        legacy_required = payload.get("recommended_workers") or []
    legacy_optional = payload.get("optional_workers") or []
    return (
        build_spawn_plan(
            review_mode=payload.get("review_mode"),
            required_workers=[
                item for item in legacy_required if isinstance(item, dict)
            ],
            optional_workers=list(legacy_optional)
            if isinstance(legacy_optional, list)
            else [],
            common_path_sufficient=common_path_sufficient is not False,
            explicit_local_only_safety_gate=bool(
                to_bool(payload.get("explicit_local_only_safety_gate"))
            ),
        ),
        [],
    )


def planned_workers_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    spawn_plan, warnings = spawn_plan_from_payload(payload)
    return default_planned_workers_from_spawn_plan(spawn_plan), warnings


def build_result_packet_metrics(result: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(result.get("packet_metrics"), dict):
        return result["packet_metrics"]
    packet_sizing = result.get("packet_sizing")
    efficiency = result.get("efficiency")
    if isinstance(packet_sizing, dict):
        packet_compaction = {}
        if isinstance(efficiency, dict):
            packet_compaction = efficiency.get("packet_compaction") or {}
        return {
            "packet_count": packet_sizing.get("packet_count"),
            "packet_size_bytes": packet_sizing.get("packet_size_bytes"),
            "largest_packet_bytes": packet_sizing.get("largest_packet_bytes"),
            "largest_two_packets_bytes": packet_sizing.get("largest_two_packets_bytes"),
            "packet_size_breakdown": packet_sizing.get("packet_size_breakdown"),
            "estimated_local_only_tokens": packet_compaction.get("local_only_tokens"),
            "estimated_packet_tokens": packet_compaction.get("packet_tokens"),
            "estimated_delegation_savings": packet_compaction.get("savings_tokens"),
        }
    return None


LEGACY_BUILD_RESULT_FIELDS = {
    "recommended_worker_count",
    "recommended_workers",
    "optional_worker_count",
    "optional_workers",
    "planned_workers",
    "packet_metrics",
    "packet_metrics_file",
    "packet_count",
    "local_only_tokens",
    "packet_tokens",
    "savings_tokens",
    "largest_packet_bytes",
    "largest_two_packets_bytes",
    "estimated_local_only_tokens",
    "estimated_packet_tokens",
    "estimated_delegation_savings",
    "packet_size_bytes",
}


def normalize_build_result(
    result: dict[str, Any],
    *,
    packet_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(result)
    spawn_plan_preview, warnings = spawn_plan_from_payload(normalized)
    normalized["spawn_plan_preview"] = spawn_plan_preview
    if warnings:
        normalized["spawn_plan_preview"]["warnings"] = warnings

    resolved_packet_metrics = packet_metrics or build_result_packet_metrics(normalized)
    if isinstance(normalized.get("packet_sizing"), dict):
        normalized["packet_sizing"] = normalized["packet_sizing"]
    elif resolved_packet_metrics is not None:
        normalized["packet_sizing"] = normalize_packet_sizing(resolved_packet_metrics)
    else:
        normalized["packet_sizing"] = normalize_packet_sizing(None)

    if isinstance(normalized.get("efficiency"), dict):
        normalized["efficiency"] = normalized["efficiency"]
    else:
        normalized["efficiency"] = build_efficiency_payload(
            resolved_packet_metrics,
            planned_workers=default_planned_workers_from_spawn_plan(
                normalized["spawn_plan_preview"]
            ),
        )

    for field in LEGACY_BUILD_RESULT_FIELDS:
        normalized.pop(field, None)
    return normalized


def empty_actual_summary() -> dict[str, Any]:
    return {
        "materialized_count": 0,
        "planned_row_count": 0,
        "unplanned_row_count": 0,
        "executed_count": 0,
        "completed_count": 0,
        "failed_count": 0,
        "cancelled_count": 0,
        "spawn_failed_count": 0,
        "planned_not_run_count": 0,
        "capture_complete": None,
        "capture_incomplete_reason": None,
    }


def default_measurement() -> dict[str, Any]:
    return {
        "latency_source": "unavailable",
        "quality_source": "unavailable",
    }


def build_base_log(
    script_path: Path,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
    *,
    skill_specific_data_fn: Callable[
        [str, dict[str, Any], dict[str, Any], dict[str, Any] | None],
        dict[str, Any],
    ],
    find_branch_fn: Callable[[dict[str, Any]], str | None] = default_find_branch,
    find_head_sha_fn: Callable[[dict[str, Any]], str | None] = default_find_head_sha,
    find_base_ref_fn: Callable[[dict[str, Any]], str | None] = default_find_base_ref,
    packet_files_fn: Callable[[dict[str, Any]], list[str]] = default_packet_files,
    skill_version: str = "unversioned",
) -> dict[str, Any]:
    identity = skill_identity(script_path, skill_version=skill_version)
    skill_name = identity["name"]
    run_id, timestamp = derive_run_id(
        skill_name,
        context,
        find_head_sha_fn=find_head_sha_fn,
    )
    lint_summary = summarize_findings(lint_report)
    spawn_plan, warnings = spawn_plan_from_payload(orchestrator)
    resolved_orchestrator_fingerprint = str(
        orchestrator.get("orchestrator_fingerprint")
        or orchestrator_fingerprint(orchestrator)
    ).strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "skill": {
            "name": skill_name,
            "family": identity["family"],
            "archetype": identity["archetype"],
            "skill_version": identity["skill_version"],
        },
        "repo": {
            "repo_name": find_repo_name(context),
            "repo_root": context.get("repo_root"),
            "branch": find_branch_fn(context),
            "head_sha": find_head_sha_fn(context),
            "base_ref": find_base_ref_fn(context),
        },
        "request": {
            "mode_requested": "default",
            "mutation_allowed": identity["archetype"] != "audit-only",
            "dry_run_requested": False,
            "user_intent_summary": None,
            "input_scope": "all-default",
        },
        "input_size": {
            "changed_files": changed_file_count(context, orchestrator),
            "untracked_files": untracked_file_count(context),
            "candidate_batches": (
                safe_int((orchestrator.get("analysis_targets") or {}).get("batch_count"))
                or 0
            ),
            "split_file_packets": sum(
                1 for name in packet_files_fn(orchestrator) if "split-file" in name.lower()
            ),
            "active_areas": active_area_count(context, orchestrator),
            "diff_churn_lines": diff_churn(orchestrator, context),
        },
        "orchestration": {
            "review_mode": orchestrator.get("review_mode"),
            "review_mode_baseline": orchestrator.get("review_mode_baseline"),
            "review_mode_adjustments": list_of_strings(
                orchestrator.get("review_mode_adjustments")
            ),
            "override_signals": normalize_override_signals(orchestrator),
            "orchestrator_fingerprint": resolved_orchestrator_fingerprint,
            "spawn_plan": spawn_plan,
            "spawn_activation": empty_spawn_activation(),
            "planned_workers": empty_planned_workers(),
            "actual_workers": {
                "summary": empty_actual_summary(),
                "workers": [],
            },
            "batch_packets_used": batch_packet_count(
                orchestrator,
                packet_files_fn=packet_files_fn,
            ),
            "item_packets_used": item_packet_count(
                orchestrator,
                packet_files_fn=packet_files_fn,
            ),
            "global_packet_used": (
                "global_packet.json" in packet_files_fn(orchestrator)
                or orchestrator.get("shared_packet") == "global_packet.json"
            ),
            "rules_packet_used": "rules_packet.json" in packet_files_fn(orchestrator),
            "raw_reread_required": False,
            "raw_reread_reason": None,
            "low_confidence_stop": False,
            "stop_reasons": [],
        },
        "measurement": default_measurement(),
        "tokens": {
            "main_model": actor_with_costs(
                {},
                default_model=DEFAULT_MAIN_MODEL,
                default_reasoning_effort=DEFAULT_MAIN_REASONING_EFFORT,
                default_identity_provenance="assumed_default",
            ),
            "subagents": [],
            "total_input_tokens": None,
            "total_cached_input_tokens": None,
            "total_output_tokens": None,
            "total_reasoning_tokens": None,
            "total_cost_nanousd": None,
            "main_model_cost_share": None,
        },
        "latency": {
            "collector_seconds": None,
            "linter_seconds": None,
            "packet_builder_seconds": None,
            "model_seconds": None,
            "validator_seconds": None,
            "apply_seconds": None,
            "total_seconds": None,
        },
        "packet_sizing": {
            "packet_count": None,
            "packet_size_bytes": None,
            "largest_packet_bytes": None,
            "largest_two_packets_bytes": None,
            "packet_size_breakdown": None,
        },
        "efficiency": build_efficiency_payload(None),
        "quality": {
            "result_status": "initialized",
            "first_pass_usable": None,
            "human_post_edit_required": None,
            "human_post_edit_severity": "unknown",
            "rerun_count": 0,
            "unsupported_claims_found": lint_summary["unsupported_claims_found"],
            "evidence_gaps_found": lint_summary["evidence_gaps_found"],
            "template_violations_found": lint_summary["template_violations_found"],
            "final_output_changed_after_review": None,
        },
        "safety": {
            "validation_run": False,
            "validation_passed": None,
            "fingerprint_match": None,
            "ambiguous_hunk_match": False,
            "marker_conflict_detected": False,
            "rollback_needed": False,
            "active_git_operation_detected": False,
            "apply_attempted": False,
            "apply_succeeded": None,
            "mutation_type": None,
        },
        "outputs": {
            "primary_artifact": None,
            "secondary_artifacts": [],
            "mutations": [],
        },
        "scoring": {
            "formula_version": DEFAULT_FORMULA_VERSION,
            "efficiency_score": None,
            "quality_score": None,
            "safety_score": None,
            "overall_score": None,
        },
        "notes": warnings,
        "skill_specific": {
            "schema_name": skill_name,
            "schema_version": SCHEMA_VERSION,
            "data": skill_specific_data_fn(
                skill_name,
                context,
                orchestrator,
                lint_report,
            ),
        },
    }


def update_latency(
    log: dict[str, Any],
    phase: str,
    duration: float | None,
    *,
    phase_label: str | None = None,
) -> None:
    if duration is None:
        return
    latency = log.setdefault("latency", {})
    key_map = {
        "build": "packet_builder_seconds",
        "lint": "linter_seconds",
        "validate": "validator_seconds",
        "apply": "apply_seconds",
    }
    key = key_map.get(phase)
    if key is None:
        return
    if phase_label:
        latency[f"{key}_{phase_label}"] = round(duration, 3)
        existing = safe_float(latency.get(key)) or 0.0
        latency[key] = round(existing + duration, 3)
    else:
        latency[key] = round(duration, 3)
    log.setdefault("measurement", default_measurement())
    log["measurement"]["latency_source"] = "measured"


def merge_stop_reasons(orchestration: dict[str, Any], stop_reasons: Any) -> None:
    reasons = list(orchestration.get("stop_reasons") or [])
    for reason in stop_reasons or []:
        text = str(reason).strip()
        if text and text not in reasons:
            reasons.append(text)
    orchestration["stop_reasons"] = reasons
    orchestration["low_confidence_stop"] = any(
        "low confidence" in str(reason).lower() for reason in reasons
    )


def apply_common_build_update(
    log: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    orchestration = log.setdefault("orchestration", {})
    if result.get("review_mode"):
        orchestration["review_mode"] = result.get("review_mode")
    if result.get("review_mode_baseline"):
        orchestration["review_mode_baseline"] = result.get("review_mode_baseline")
    review_mode_adjustments = list_of_strings(result.get("review_mode_adjustments"))
    if review_mode_adjustments:
        orchestration["review_mode_adjustments"] = review_mode_adjustments
    override_signals = normalize_override_signals(result)
    if override_signals:
        orchestration["override_signals"] = override_signals
    spawn_plan, warnings = spawn_plan_from_payload(result)
    if any(
        key in result
        for key in (
            "spawn_plan_preview",
            "spawn_plan",
            "planned_workers",
            "recommended_workers",
            "recommended_worker_count",
        )
    ):
        orchestration["spawn_plan"] = spawn_plan
        orchestration["planned_workers"] = empty_planned_workers()
    if warnings:
        log.setdefault("notes", []).extend(warnings)
    packet_metrics = build_result_packet_metrics(result)
    if isinstance(result.get("packet_sizing"), dict):
        log["packet_sizing"] = result["packet_sizing"]
    elif packet_metrics is not None:
        log["packet_sizing"] = normalize_packet_sizing(packet_metrics)
    if isinstance(result.get("efficiency"), dict):
        log["efficiency"] = result["efficiency"]
    elif packet_metrics is not None:
        log["efficiency"] = build_efficiency_payload(
            packet_metrics,
            planned_workers=default_planned_workers_from_spawn_plan(
                orchestration.get("spawn_plan") or empty_spawn_plan()
            ),
            main_model=(log.get("tokens") or {}).get("main_model"),
            subagents=(log.get("tokens") or {}).get("subagents") or [],
        )
    return packet_metrics


def apply_common_phase_update(
    log: dict[str, Any],
    phase: str,
    result: dict[str, Any],
    duration: float | None,
    *,
    phase_label: str | None = None,
) -> dict[str, Any] | None:
    update_latency(log, phase, duration, phase_label=phase_label)
    if phase == "build":
        return apply_common_build_update(log, result)

    if phase == "lint":
        lint_like = result.get("findings", result)
        lint_summary = summarize_findings(
            lint_like
            if isinstance(lint_like, dict) and "findings" in lint_like
            else {"findings": lint_like}
        )
        quality = log.setdefault("quality", {})
        quality["unsupported_claims_found"] = lint_summary["unsupported_claims_found"]
        quality["evidence_gaps_found"] = lint_summary["evidence_gaps_found"]
        quality["template_violations_found"] = lint_summary["template_violations_found"]
        log.setdefault("measurement", default_measurement())["quality_source"] = "estimated"
        return None

    if phase == "validate":
        safety = log.setdefault("safety", {})
        orchestration = log.setdefault("orchestration", {})
        safety["validation_run"] = True
        validation_passed = None
        if "validation_passed" in result:
            validation_passed = to_bool(result.get("validation_passed"))
        elif "valid" in result:
            validation_passed = to_bool(result.get("valid"))
        elif "ok" in result:
            validation_passed = to_bool(result.get("ok"))
        elif "can_apply" in result and "errors" in result:
            validation_passed = to_bool(result.get("can_apply")) and not bool(
                result.get("errors")
            )
        safety["validation_passed"] = validation_passed
        if "fingerprint_match" in result:
            safety["fingerprint_match"] = to_bool(result.get("fingerprint_match"))
        if "ambiguous_hunk_match" in result:
            safety["ambiguous_hunk_match"] = to_bool(result.get("ambiguous_hunk_match"))
        merge_stop_reasons(orchestration, result.get("stop_reasons") or [])
        return None

    if phase == "apply":
        safety = log.setdefault("safety", {})
        quality = log.setdefault("quality", {})
        outputs = log.setdefault("outputs", {})
        orchestration = log.setdefault("orchestration", {})
        dry_run = to_bool(result.get("dry_run"))
        apply_attempted = not bool(dry_run)
        safety["apply_attempted"] = apply_attempted
        apply_succeeded = None
        for key in ("apply_succeeded", "success", "ok", "applied"):
            if key in result:
                apply_succeeded = to_bool(result.get(key))
                break
        if apply_attempted:
            safety["apply_succeeded"] = apply_succeeded
        if "fingerprint_match" in result:
            safety["fingerprint_match"] = to_bool(result.get("fingerprint_match"))
        if "ambiguous_hunk_match" in result:
            safety["ambiguous_hunk_match"] = to_bool(result.get("ambiguous_hunk_match"))
        if "rollback_needed" in result:
            safety["rollback_needed"] = to_bool(result.get("rollback_needed"))
        mutation_type = result.get("mutation_type")
        mutations = result.get("mutations")
        if not mutation_type and isinstance(mutations, list) and mutations:
            first = mutations[0]
            if isinstance(first, dict):
                mutation_type = first.get("kind")
        if mutation_type:
            safety["mutation_type"] = mutation_type
        if isinstance(mutations, list):
            outputs["mutations"] = mutations
        if result.get("primary_artifact"):
            outputs["primary_artifact"] = result.get("primary_artifact")
        secondary = result.get("secondary_artifacts")
        if isinstance(secondary, list):
            outputs["secondary_artifacts"] = secondary
        merge_stop_reasons(orchestration, result.get("stop_reasons") or [])
        if dry_run:
            quality["result_status"] = "dry-run"
        elif apply_succeeded is True:
            quality["result_status"] = "completed"
        elif result.get("stop_reasons"):
            quality["result_status"] = "stopped"
        elif apply_attempted:
            quality["result_status"] = "failed"
        return None
    return None


def normalize_main_model(tokens: dict[str, Any]) -> dict[str, Any]:
    main_model = tokens.get("main_model")
    if not isinstance(main_model, dict):
        main_model = {}
    return actor_with_costs(
        main_model,
        default_model=DEFAULT_MAIN_MODEL,
        default_reasoning_effort=DEFAULT_MAIN_REASONING_EFFORT,
        default_identity_provenance="assumed_default",
    )


def normalize_subagents(tokens: dict[str, Any]) -> list[dict[str, Any]]:
    subagents = tokens.get("subagents")
    if not isinstance(subagents, list):
        return []
    return [actor_with_costs(actor) for actor in subagents if isinstance(actor, dict)]


def normalize_tokens(log: dict[str, Any]) -> None:
    tokens = log.setdefault("tokens", {})
    main_model = normalize_main_model(tokens)
    subagents = normalize_subagents(tokens)
    tokens["main_model"] = main_model
    tokens["subagents"] = subagents

    def sum_tokens(key: str, items: list[dict[str, Any]]) -> int:
        return sum(safe_int(item.get(key)) or 0 for item in items)

    total_input = (safe_int(main_model.get("input_tokens")) or 0) + sum_tokens(
        "input_tokens",
        subagents,
    )
    total_cached_input = (
        safe_int(main_model.get("cached_input_tokens")) or 0
    ) + sum_tokens("cached_input_tokens", subagents)
    total_output = (safe_int(main_model.get("output_tokens")) or 0) + sum_tokens(
        "output_tokens",
        subagents,
    )
    total_reasoning = (
        safe_int(main_model.get("reasoning_tokens")) or 0
    ) + sum_tokens("reasoning_tokens", subagents)
    main_cost = safe_int(main_model.get("total_cost_nanousd"))
    sub_cost = sum((safe_int(agent.get("total_cost_nanousd")) or 0) for agent in subagents)
    total_cost = None
    if main_cost is not None or any(
        safe_int(agent.get("total_cost_nanousd")) is not None for agent in subagents
    ):
        total_cost = (main_cost or 0) + sub_cost
    tokens["total_input_tokens"] = total_input or None
    tokens["total_cached_input_tokens"] = total_cached_input or None
    tokens["total_output_tokens"] = total_output or None
    tokens["total_reasoning_tokens"] = total_reasoning or None
    tokens["total_cost_nanousd"] = total_cost
    if total_cost and main_cost is not None:
        tokens["main_model_cost_share"] = round(main_cost / total_cost, 3)
    else:
        tokens["main_model_cost_share"] = None


def unplanned_status(status: str) -> str:
    if status in ALLOWED_UNPLANNED_LEDGER_STATUSES:
        return status
    if status == "started":
        return "unplanned_started"
    if status in {"completed", "failed", "cancelled"}:
        return f"unplanned_{status}"
    return "unplanned_completed"


def planned_status(status: str) -> str:
    if status.startswith("unplanned_"):
        status = status[len("unplanned_") :]
    if status in ALLOWED_PLANNED_LEDGER_STATUSES:
        return status
    if status in PLANNED_EXECUTED_STATUSES:
        return status
    return "completed"


def normalize_actual_worker_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["input_tokens"] = safe_int(normalized.get("input_tokens"))
    normalized["cached_input_tokens"] = safe_int(normalized.get("cached_input_tokens"))
    normalized["output_tokens"] = safe_int(normalized.get("output_tokens"))
    normalized["reasoning_tokens"] = safe_int(normalized.get("reasoning_tokens"))
    row_kind = str(normalized.get("row_kind") or "").strip()
    normalized["row_kind"] = row_kind if row_kind in ALLOWED_ROW_KINDS else None
    return normalized


def actual_worker_fallback_tuple(
    row: dict[str, Any],
) -> tuple[str, str, str, str, tuple[str, ...]]:
    packets = row.get("packets")
    if not isinstance(packets, list):
        packets = []
    return (
        str(row.get("name") or "").strip(),
        str(row.get("agent_type") or "").strip(),
        str(row.get("model") or "").strip(),
        str(row.get("reasoning_effort") or "").strip(),
        tuple(sorted(str(item).strip() for item in packets if str(item).strip())),
    )


def build_planned_lookup(
    planned_workers: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]],
]:
    by_id: dict[str, dict[str, Any]] = {}
    by_tuple: dict[tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for worker in planned_workers.get("workers", []):
        if not isinstance(worker, dict):
            continue
        worker_id = str(worker.get("worker_id") or "").strip()
        if worker_id:
            by_id[worker_id] = worker
        identity = canonical_worker_identity_tuple(worker)
        by_tuple.setdefault(identity, []).append(worker)
    return by_id, by_tuple


def normalize_spawn_activation_worker(
    row: dict[str, Any],
    *,
    worker_id: str,
    planned_worker_id: str | None,
    default_stage: str,
) -> dict[str, Any]:
    normalized = {
        "worker_id": worker_id,
        "planned_worker_id": planned_worker_id,
        "stage": (
            str(row.get("stage") or default_stage).strip()
            if str(row.get("stage") or default_stage).strip() in ALLOWED_SPAWN_STAGES
            else default_stage
        ),
        "spawn_attempted": to_bool(row.get("spawn_attempted")),
        "spawn_succeeded": to_bool(row.get("spawn_succeeded")),
        "spawn_failed": to_bool(row.get("spawn_failed")),
        "attempt_count": safe_int(row.get("attempt_count")),
        "failure_kind": str(row.get("failure_kind") or "").strip() or None,
        "fallback_reason": str(row.get("fallback_reason") or "").strip() or None,
        "resolved_as": str(row.get("resolved_as") or "").strip() or None,
    }
    if normalized["spawn_succeeded"] is None and normalized["resolved_as"] == "spawned":
        normalized["spawn_succeeded"] = True
    if normalized["spawn_failed"] is None and normalized["resolved_as"] in {"local_fallback", "spawn_failed"}:
        normalized["spawn_failed"] = True
    resolved_as = normalized["resolved_as"]
    if resolved_as not in ALLOWED_SPAWN_RESOLUTIONS:
        if normalized["spawn_succeeded"]:
            resolved_as = "spawned"
        elif normalized["fallback_reason"]:
            resolved_as = "local_fallback"
        elif normalized["spawn_failed"]:
            resolved_as = "spawn_failed"
        else:
            resolved_as = "not_activated"
    normalized["resolved_as"] = resolved_as
    if normalized["spawn_attempted"] is None:
        normalized["spawn_attempted"] = (
            bool(normalized["attempt_count"])
            or bool(normalized["spawn_succeeded"])
            or bool(normalized["spawn_failed"])
            or resolved_as in {"spawned", "local_fallback", "spawn_failed"}
        )
    if normalized["attempt_count"] is None:
        normalized["attempt_count"] = 1 if normalized["spawn_attempted"] else 0
    normalized["spawn_attempted"] = bool(normalized["spawn_attempted"])
    normalized["spawn_succeeded"] = bool(normalized["spawn_succeeded"])
    normalized["spawn_failed"] = bool(normalized["spawn_failed"])
    return normalized


def normalize_spawn_activation(log: dict[str, Any]) -> None:
    orchestration = log.setdefault("orchestration", {})
    spawn_plan = orchestration.get("spawn_plan")
    if not isinstance(spawn_plan, dict):
        spawn_plan = empty_spawn_plan()
        orchestration["spawn_plan"] = spawn_plan
    activation = orchestration.get("spawn_activation")
    if not isinstance(activation, dict):
        activation = empty_spawn_activation()
        orchestration["spawn_activation"] = activation
    summary = activation.get("summary")
    if not isinstance(summary, dict):
        summary = empty_spawn_activation_summary()
    else:
        merged_summary = empty_spawn_activation_summary()
        merged_summary.update(summary)
        summary = merged_summary
    activation["activated_worker_ids"] = stable_dedupe(
        list_of_strings(activation.get("activated_worker_ids"))
    )
    activation["skipped_worker_ids"] = stable_dedupe(
        list_of_strings(activation.get("skipped_worker_ids"))
    )
    activation["local_fallback_worker_ids"] = stable_dedupe(
        list_of_strings(activation.get("local_fallback_worker_ids"))
    )
    trigger_events = activation.get("trigger_events")
    activation["trigger_events"] = (
        [item for item in trigger_events if isinstance(item, dict)]
        if isinstance(trigger_events, list)
        else []
    )
    drift_events = activation.get("drift_events")
    activation["drift_events"] = (
        [item for item in drift_events if isinstance(item, dict)]
        if isinstance(drift_events, list)
        else []
    )
    workers = activation.get("workers")
    incoming_rows = workers if isinstance(workers, list) else []
    by_id = {
        str(worker.get("worker_id") or "").strip(): worker
        for worker in spawn_plan.get("workers", [])
        if isinstance(worker, dict) and str(worker.get("worker_id") or "").strip()
    }
    normalized_rows: list[dict[str, Any]] = []
    seen_worker_ids: set[str] = set()

    def synthesize_list_only_row(
        worker_id: str,
        *,
        resolved_as: str,
    ) -> None:
        plan_worker = by_id.get(worker_id)
        if not plan_worker or worker_id in seen_worker_ids:
            return
        seed: dict[str, Any]
        if resolved_as == "spawned":
            seed = {
                "resolved_as": "spawned",
                "spawn_attempted": True,
                "spawn_succeeded": True,
            }
        elif resolved_as == "local_fallback":
            seed = {
                "resolved_as": "local_fallback",
                "spawn_attempted": True,
                "spawn_failed": True,
            }
        else:
            seed = {
                "resolved_as": "not_activated",
                "spawn_attempted": False,
                "spawn_succeeded": False,
                "spawn_failed": False,
            }
        seen_worker_ids.add(worker_id)
        normalized_rows.append(
            normalize_spawn_activation_worker(
                seed,
                worker_id=worker_id,
                planned_worker_id=worker_id,
                default_stage=str(plan_worker.get("stage") or "initial_parallel"),
            )
        )

    for row in incoming_rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(
            row.get("planned_worker_id") or row.get("worker_id") or ""
        ).strip()
        plan_worker = by_id.get(candidate_id)
        if not plan_worker:
            continue
        planned_worker_id = str(plan_worker.get("worker_id") or "").strip()
        if planned_worker_id in seen_worker_ids:
            continue
        seen_worker_ids.add(planned_worker_id)
        worker_id = str(row.get("worker_id") or planned_worker_id).strip() or planned_worker_id
        normalized_rows.append(
            normalize_spawn_activation_worker(
                row,
                worker_id=worker_id,
                planned_worker_id=planned_worker_id,
                default_stage=str(plan_worker.get("stage") or "initial_parallel"),
            )
        )

    for worker_id in activation["local_fallback_worker_ids"]:
        synthesize_list_only_row(worker_id, resolved_as="local_fallback")
    for worker_id in activation["activated_worker_ids"]:
        synthesize_list_only_row(worker_id, resolved_as="spawned")
    for worker_id in activation["skipped_worker_ids"]:
        synthesize_list_only_row(worker_id, resolved_as="not_activated")

    default_spawn_enabled = bool(spawn_plan.get("default_spawn_enabled"))
    for worker in spawn_plan.get("workers", []):
        if not isinstance(worker, dict):
            continue
        worker_id = str(worker.get("worker_id") or "").strip()
        if not worker_id or worker_id in seen_worker_ids:
            continue
        if worker_id in activation["activated_worker_ids"]:
            continue
        if worker_id in activation["skipped_worker_ids"]:
            continue
        if worker_id in activation["local_fallback_worker_ids"]:
            continue
        if default_spawn_enabled and bool(worker.get("default_spawn")):
            continue
        normalized_rows.append(
            normalize_spawn_activation_worker(
                {},
                worker_id=worker_id,
                planned_worker_id=worker_id,
                default_stage=str(worker.get("stage") or "initial_parallel"),
            )
        )

    summary["attempted_count"] = sum(
        1 for row in normalized_rows if row["spawn_attempted"]
    )
    summary["succeeded_count"] = sum(
        1 for row in normalized_rows if row["resolved_as"] == "spawned"
    )
    summary["failed_count"] = sum(
        1 for row in normalized_rows if row["resolved_as"] in {"local_fallback", "spawn_failed"}
    )
    summary["local_fallback_count"] = sum(
        1 for row in normalized_rows if row["resolved_as"] == "local_fallback"
    )
    summary["not_activated_count"] = sum(
        1 for row in normalized_rows if row["resolved_as"] == "not_activated"
    )
    activation["summary"] = summary
    activation["workers"] = normalized_rows


def incoming_planned_worker_ids(
    log: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> set[str]:
    orchestration = log.get("orchestration", {})
    rows = ((orchestration.get("actual_workers") or {}).get("workers") or [])
    if not isinstance(rows, list):
        return set()
    expected_fingerprint = str(orchestration.get("orchestrator_fingerprint") or "").strip()
    expected_schema = str(
        ((orchestration.get("spawn_plan") or {}).get("schema_version") or "")
    ).strip()
    ids: set[str] = set()
    notes = log.setdefault("notes", [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        planned_worker_id = str(row.get("planned_worker_id") or "").strip()
        if not planned_worker_id or planned_worker_id not in by_id:
            continue
        row_fingerprint = str(row.get("orchestrator_fingerprint") or "").strip()
        row_schema = str(row.get("spawn_plan_schema_version") or "").strip()
        if row_fingerprint and expected_fingerprint and row_fingerprint != expected_fingerprint:
            notes.append(
                "Stale orchestrator_fingerprint on worker result; recorded as unplanned execution."
            )
            continue
        if row_schema and expected_schema and row_schema != expected_schema:
            notes.append(
                "Stale spawn_plan_schema_version on worker result; recorded as unplanned execution."
            )
            continue
        ids.add(planned_worker_id)
    return ids


def resolve_planned_workers(log: dict[str, Any]) -> None:
    orchestration = log.setdefault("orchestration", {})
    spawn_plan = orchestration.get("spawn_plan")
    if not isinstance(spawn_plan, dict):
        spawn_plan = empty_spawn_plan()
        orchestration["spawn_plan"] = spawn_plan
    activation = orchestration.get("spawn_activation")
    if not isinstance(activation, dict):
        activation = empty_spawn_activation()
        orchestration["spawn_activation"] = activation
    workers = [
        worker
        for worker in spawn_plan.get("workers", [])
        if isinstance(worker, dict)
    ]
    if not workers:
        orchestration["planned_workers"] = empty_planned_workers()
        return
    worker_by_id = {
        str(worker.get("worker_id") or "").strip(): worker
        for worker in workers
        if str(worker.get("worker_id") or "").strip()
    }
    resolved_ids: set[str] = set()
    if bool(spawn_plan.get("default_spawn_enabled")):
        resolved_ids.update(
            str(worker.get("worker_id") or "").strip()
            for worker in workers
            if bool(worker.get("default_spawn"))
        )
    resolved_ids.update(
        worker_id
        for worker_id in stable_dedupe(
            [
                *list_of_strings(activation.get("activated_worker_ids")),
                *list_of_strings(activation.get("skipped_worker_ids")),
                *list_of_strings(activation.get("local_fallback_worker_ids")),
            ]
        )
        if worker_id in worker_by_id
    )
    for row in activation.get("workers", []):
        if not isinstance(row, dict):
            continue
        worker_id = str(row.get("planned_worker_id") or row.get("worker_id") or "").strip()
        if worker_id and worker_id in worker_by_id and row.get("resolved_as") in {
            "spawned",
            "local_fallback",
            "spawn_failed",
            "not_activated",
        }:
            resolved_ids.add(worker_id)
    resolved_ids.update(incoming_planned_worker_ids(log, worker_by_id))
    resolved_workers = [
        worker
        for worker in workers
        if str(worker.get("worker_id") or "").strip() in resolved_ids
    ]
    orchestration["planned_workers"] = {
        "count": len(resolved_workers),
        "roles": stable_dedupe(
            [str(worker.get("agent_type") or "").strip() for worker in resolved_workers]
        ),
        "workers": resolved_workers,
    }


def status_from_spawn_activation(
    worker_id: str,
    activation: dict[str, Any],
) -> str:
    for row in activation.get("workers", []):
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("planned_worker_id") or row.get("worker_id") or "").strip()
        if candidate_id != worker_id:
            continue
        if row.get("resolved_as") == "spawned":
            return "started"
        if row.get("resolved_as") in {"local_fallback", "spawn_failed"}:
            return "spawn_failed"
    if worker_id in stable_dedupe(
        list_of_strings(activation.get("activated_worker_ids"))
    ):
        return "started"
    if worker_id in stable_dedupe(
        list_of_strings(activation.get("local_fallback_worker_ids"))
    ):
        return "spawn_failed"
    return "planned_not_run"


def normalize_actual_workers(log: dict[str, Any]) -> None:
    orchestration = log.setdefault("orchestration", {})
    planned_workers = orchestration.get("planned_workers")
    if not isinstance(planned_workers, dict):
        planned_workers = empty_planned_workers()
        orchestration["planned_workers"] = planned_workers
    activation = orchestration.get("spawn_activation")
    if not isinstance(activation, dict):
        activation = empty_spawn_activation()
        orchestration["spawn_activation"] = activation
    actual_workers = orchestration.get("actual_workers")
    if not isinstance(actual_workers, dict):
        actual_workers = {"summary": empty_actual_summary(), "workers": []}
        orchestration["actual_workers"] = actual_workers
    summary = actual_workers.get("summary")
    if not isinstance(summary, dict):
        summary = empty_actual_summary()
    else:
        merged_summary = empty_actual_summary()
        merged_summary.update(summary)
        summary = merged_summary
    incoming_rows = actual_workers.get("workers")
    if not isinstance(incoming_rows, list):
        incoming_rows = []
    by_id, by_tuple = build_planned_lookup(planned_workers)
    assigned_planned_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    notes = log.setdefault("notes", [])
    drift_events = activation.get("drift_events")
    if not isinstance(drift_events, list):
        drift_events = []
        activation["drift_events"] = drift_events
    expected_fingerprint = str(orchestration.get("orchestrator_fingerprint") or "").strip()
    expected_schema = str(
        ((orchestration.get("spawn_plan") or {}).get("schema_version") or "")
    ).strip()

    for index, row in enumerate(incoming_rows):
        if not isinstance(row, dict):
            continue
        normalized = normalize_actual_worker_row(row)
        status = str(normalized.get("status") or "").strip() or "completed"
        row_kind = normalized.get("row_kind")
        planned_worker_id = str(normalized.get("planned_worker_id") or "").strip() or None
        row_fingerprint = str(normalized.get("orchestrator_fingerprint") or "").strip()
        row_schema = str(normalized.get("spawn_plan_schema_version") or "").strip()
        drift_reason = None
        if row_fingerprint and expected_fingerprint and row_fingerprint != expected_fingerprint:
            drift_reason = "orchestrator_fingerprint_mismatch"
        elif row_schema and expected_schema and row_schema != expected_schema:
            drift_reason = "spawn_plan_schema_version_mismatch"
        if drift_reason:
            drift_events.append(
                {
                    "worker_id": str(normalized.get("worker_id") or planned_worker_id or ""),
                    "planned_worker_id": planned_worker_id,
                    "reason": drift_reason,
                }
            )
            planned_worker_id = None
            row_kind = "unplanned"
        if planned_worker_id and planned_worker_id in by_id and planned_worker_id not in assigned_planned_ids:
            row_kind = "planned"
            assigned_planned_ids.add(planned_worker_id)
        elif planned_worker_id:
            row_kind = "unplanned"
            if planned_worker_id in assigned_planned_ids:
                notes.append(
                    "Duplicate planned worker ledger row recorded as unplanned execution."
                )
            else:
                notes.append(
                    "Unknown planned_worker_id in actual worker payload; recorded as unplanned execution."
                )
            planned_worker_id = None
        elif drift_reason:
            row_kind = "unplanned"
            planned_worker_id = None
        else:
            matches = by_tuple.get(actual_worker_fallback_tuple(normalized), [])
            if len(matches) == 1:
                candidate_id = str(matches[0]["worker_id"] or "").strip()
                if candidate_id and candidate_id not in assigned_planned_ids:
                    planned_worker_id = candidate_id
                    row_kind = "planned"
                    assigned_planned_ids.add(candidate_id)
                else:
                    row_kind = "unplanned"
                    planned_worker_id = None
            elif len(matches) > 1:
                row_kind = "unplanned"
                planned_worker_id = None
                notes.append(
                    "Ambiguous actual worker fallback match; recorded as unplanned execution."
                )
            else:
                row_kind = "unplanned"
        if row_kind == "planned":
            normalized["row_kind"] = "planned"
            normalized["planned_worker_id"] = planned_worker_id
            normalized["worker_id"] = str(normalized.get("worker_id") or planned_worker_id)
            normalized["status"] = planned_status(status)
        else:
            normalized["row_kind"] = "unplanned"
            normalized["planned_worker_id"] = None
            normalized["worker_id"] = str(
                normalized.get("worker_id")
                or f"actual:unplanned:{index + 1}:{short_hash(canonical_json(normalized))}"
            )
            normalized["status"] = unplanned_status(status)
        normalized_rows.append(normalized)

    for worker in planned_workers.get("workers", []):
        if not isinstance(worker, dict):
            continue
        worker_id = str(worker.get("worker_id") or "").strip()
        if not worker_id or worker_id in assigned_planned_ids:
            continue
        normalized_rows.append(
            {
                "row_kind": "planned",
                "worker_id": worker_id,
                "planned_worker_id": worker_id,
                "agent_type": worker.get("agent_type"),
                "model": worker.get("model"),
                "reasoning_effort": worker.get("reasoning_effort"),
                "status": status_from_spawn_activation(worker_id, activation),
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
            }
        )

    capture_complete = to_bool(summary.get("capture_complete"))
    has_nonterminal_status = any(
        str(row.get("status") or "") in NONTERMINAL_ACTUAL_STATUSES
        for row in normalized_rows
    )
    if capture_complete is None and normalized_rows:
        capture_complete = not has_nonterminal_status
    if capture_complete and has_nonterminal_status:
        raise ValueError(
            "capture_complete=true cannot include nonterminal actual worker statuses"
        )
    summary["capture_complete"] = capture_complete
    summary["capture_incomplete_reason"] = (
        str(summary.get("capture_incomplete_reason") or "").strip() or None
    )

    summary["materialized_count"] = len(normalized_rows)
    summary["planned_row_count"] = sum(
        1 for row in normalized_rows if row.get("row_kind") == "planned"
    )
    summary["unplanned_row_count"] = sum(
        1 for row in normalized_rows if row.get("row_kind") == "unplanned"
    )
    summary["executed_count"] = sum(
        1
        for row in normalized_rows
        if str(row.get("status") or "")
        in {
            "completed",
            "failed",
            "cancelled",
            "unplanned_completed",
            "unplanned_failed",
            "unplanned_cancelled",
        }
    )
    summary["completed_count"] = sum(
        1
        for row in normalized_rows
        if row["status"] in {"completed", "unplanned_completed"}
    )
    summary["failed_count"] = sum(
        1 for row in normalized_rows if row["status"] in {"failed", "unplanned_failed"}
    )
    summary["cancelled_count"] = sum(
        1
        for row in normalized_rows
        if row["status"] in {"cancelled", "unplanned_cancelled"}
    )
    summary["spawn_failed_count"] = sum(
        1 for row in normalized_rows if row["status"] == "spawn_failed"
    )
    summary["planned_not_run_count"] = sum(
        1 for row in normalized_rows if row["status"] == "planned_not_run"
    )
    actual_workers["summary"] = summary
    actual_workers["workers"] = normalized_rows


def clamp_ratio(numerator: Any, denominator: Any) -> float | None:
    top = safe_float(numerator)
    bottom = safe_float(denominator)
    if top is None or bottom is None or bottom <= 0:
        return None
    return round(max(0.0, min(1.0, top / bottom)), 3)


def bool_score(
    value: bool | None,
    true_score: float = 1.0,
    false_score: float = 0.0,
) -> float | None:
    if value is None:
        return None
    return true_score if value else false_score


def linear_penalty(
    count: int | None,
    penalty: float,
    floor: float = 0.0,
) -> float | None:
    if count is None:
        return None
    return max(floor, 1.0 - penalty * max(count, 0))


def weighted_average(items: list[tuple[float | None, float]]) -> float | None:
    filtered = [(value, weight) for value, weight in items if value is not None]
    if not filtered:
        return None
    total_weight = sum(weight for _value, weight in filtered)
    return round(
        sum(value * weight for value, weight in filtered) / total_weight,
        3,
    )


def score_worker_fit(review_mode: Any, worker_count: Any) -> float | None:
    mode = str(review_mode or "").strip()
    count = safe_int(worker_count)
    if not mode or count is None:
        return None
    if mode == "local-only":
        return 1.0 if count == 0 else max(0.0, 1.0 - 0.25 * count)
    if mode == "targeted-delegation":
        if 1 <= count <= 2:
            return 1.0
        if count in {0, 3}:
            return 0.6
        return 0.3
    if mode == "broad-delegation":
        if 3 <= count <= 4:
            return 1.0
        if count == 2:
            return 0.7
        if count in {1, 5}:
            return 0.4
        return 0.2
    return None


def score_main_model_cost_share(value: Any) -> float | None:
    share = safe_float(value)
    if share is None:
        return None
    if share <= 0.8:
        return 1.0
    if share <= 0.9:
        return 0.8
    if share <= 0.95:
        return 0.6
    return 0.4


def execution_fidelity_score(log: dict[str, Any]) -> float | None:
    orchestration = log.get("orchestration", {})
    planned_workers = orchestration.get("planned_workers", {})
    actual_workers = orchestration.get("actual_workers", {})
    planned_total = safe_int((planned_workers or {}).get("count"))
    if planned_total is None:
        planned_total = len((planned_workers or {}).get("workers") or [])
    rows = (actual_workers or {}).get("workers") or []
    if not isinstance(rows, list):
        rows = []
    unplanned_total = sum(
        1
        for row in rows
        if isinstance(row, dict) and str(row.get("row_kind") or "") == "unplanned"
    )
    planned_statuses = [
        str(row.get("status") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("row_kind") or "") == "planned"
    ]
    if planned_total == 0 and unplanned_total == 0:
        return 1.0
    if not rows:
        return None
    if planned_total == 0 and unplanned_total > 0:
        return 0.4
    if (
        planned_statuses
        and all(status in {"planned_not_run", "spawn_failed"} for status in planned_statuses)
        and unplanned_total == 0
    ):
        return 0.0
    if (
        planned_statuses
        and all(status in PLANNED_EXECUTED_STATUSES for status in planned_statuses)
        and len(planned_statuses) == planned_total
        and unplanned_total == 0
    ):
        return 1.0
    if (
        any(status in PLANNED_EXECUTED_STATUSES for status in planned_statuses)
        and any(status in {"planned_not_run", "spawn_failed"} for status in planned_statuses)
        and unplanned_total == 0
    ):
        return 0.7
    return 0.4


def packet_compaction_ratio(log: dict[str, Any]) -> float | None:
    packet_compaction = ((log.get("efficiency") or {}).get("packet_compaction") or {})
    return clamp_ratio(
        packet_compaction.get("savings_tokens"),
        packet_compaction.get("local_only_tokens"),
    )


def delegation_net_cost_ratio(log: dict[str, Any]) -> float | None:
    delegation = (
        (log.get("efficiency") or {}).get("model_tier_delegation") or {}
    )
    return clamp_ratio(
        delegation.get("net_savings_cost_nanousd"),
        delegation.get("gross_avoided_main_cost_nanousd"),
    )


def worker_fit_count(log: dict[str, Any]) -> int | None:
    orchestration = log.get("orchestration", {})
    actual_summary = ((orchestration.get("actual_workers") or {}).get("summary") or {})
    executed_count = safe_int(actual_summary.get("executed_count"))
    materialized = safe_int(actual_summary.get("materialized_count"))
    if materialized is not None and materialized > 0:
        return executed_count
    planned = orchestration.get("planned_workers") or {}
    count = safe_int(planned.get("count"))
    if count is not None:
        return count
    workers = planned.get("workers") or []
    return len(workers) if isinstance(workers, list) else None


def compute_scores(log: dict[str, Any]) -> None:
    orchestration = log.get("orchestration", {})
    quality = log.get("quality", {})
    safety = log.get("safety", {})
    tokens = log.get("tokens", {})
    efficiency_score = weighted_average(
        [
            (
                score_worker_fit(orchestration.get("review_mode"), worker_fit_count(log)),
                0.15,
            ),
            (execution_fidelity_score(log), 0.10),
            (bool_score(to_bool(orchestration.get("global_packet_used")), 1.0, 0.0), 0.10),
            (bool_score(not bool(orchestration.get("raw_reread_required")), 1.0, 0.4), 0.15),
            (linear_penalty(safe_int(quality.get("rerun_count")), 0.25, floor=0.25), 0.15),
            (score_main_model_cost_share(tokens.get("main_model_cost_share")), 0.15),
            (packet_compaction_ratio(log), 0.10),
            (delegation_net_cost_ratio(log), 0.10),
        ]
    )

    severity = str(quality.get("human_post_edit_severity") or "unknown").lower()
    severity_scores = {
        "none": 1.0,
        "low": 0.75,
        "medium": 0.5,
        "high": 0.25,
        "unknown": 0.6,
    }
    human_edit_required = to_bool(quality.get("human_post_edit_required"))
    human_edit_score = None
    if human_edit_required is not None:
        human_edit_score = (
            1.0 if not human_edit_required else severity_scores.get(severity, 0.6)
        )
    result_status = str(quality.get("result_status") or "").lower()
    status_scores = {"completed": 1.0, "dry-run": 0.8, "stopped": 0.5, "failed": 0.2}
    quality_score = weighted_average(
        [
            (status_scores.get(result_status), 0.1),
            (bool_score(to_bool(quality.get("first_pass_usable")), 1.0, 0.0), 0.3),
            (human_edit_score, 0.15),
            (linear_penalty(safe_int(quality.get("unsupported_claims_found")), 0.2), 0.15),
            (linear_penalty(safe_int(quality.get("evidence_gaps_found")), 0.15), 0.1),
            (linear_penalty(safe_int(quality.get("template_violations_found")), 0.25), 0.1),
            (bool_score(not bool(quality.get("final_output_changed_after_review")), 1.0, 0.65), 0.1),
        ]
    )

    validation_run = to_bool(safety.get("validation_run"))
    validation_passed = to_bool(safety.get("validation_passed"))
    apply_attempted = to_bool(safety.get("apply_attempted"))
    if apply_attempted and validation_passed is False:
        validation_boundary_score = 0.0
    elif validation_run and validation_passed is True:
        validation_boundary_score = 1.0
    elif validation_run and validation_passed is False:
        validation_boundary_score = 0.3
    elif apply_attempted:
        validation_boundary_score = 0.2
    else:
        validation_boundary_score = None

    safety_score = weighted_average(
        [
            (validation_boundary_score, 0.3),
            (bool_score(to_bool(safety.get("fingerprint_match")), 1.0, 0.0), 0.15),
            (bool_score(not bool(safety.get("ambiguous_hunk_match")), 1.0, 0.0), 0.15),
            (bool_score(not bool(safety.get("marker_conflict_detected")), 1.0, 0.4), 0.1),
            (bool_score(not bool(safety.get("rollback_needed")), 1.0, 0.2), 0.1),
            (bool_score(not bool(safety.get("active_git_operation_detected")), 1.0, 0.0), 0.1),
            (
                bool_score(to_bool(safety.get("apply_succeeded")), 1.0, 0.2)
                if apply_attempted
                else None,
                0.1,
            ),
        ]
    )

    overall = weighted_average(
        [(efficiency_score, 0.2), (quality_score, 0.35), (safety_score, 0.45)]
    )

    log.setdefault("scoring", {})
    log["scoring"]["formula_version"] = DEFAULT_FORMULA_VERSION
    log["scoring"]["efficiency_score"] = efficiency_score
    log["scoring"]["quality_score"] = quality_score
    log["scoring"]["safety_score"] = safety_score
    log["scoring"]["overall_score"] = overall


def finalize_log(log: dict[str, Any], final_payload: dict[str, Any]) -> None:
    deep_merge(log, final_payload)
    notes = log.get("notes")
    if not isinstance(notes, list):
        log["notes"] = []
    else:
        log["notes"] = stable_dedupe(
            [str(note) for note in notes if str(note).strip()]
        )

    latency = log.setdefault("latency", {})
    component_keys = [
        "collector_seconds",
        "linter_seconds",
        "packet_builder_seconds",
        "model_seconds",
        "validator_seconds",
        "apply_seconds",
    ]
    if latency.get("total_seconds") is None:
        total = sum(safe_float(latency.get(key)) or 0.0 for key in component_keys)
        if total > 0:
            latency["total_seconds"] = round(total, 3)
            log.setdefault("measurement", default_measurement())["latency_source"] = "estimated"

    if log.get("quality", {}).get("first_pass_usable") is not None:
        measurement = log.setdefault("measurement", default_measurement())
        if measurement.get("quality_source") == "unavailable":
            measurement["quality_source"] = "self_assessed"

    normalize_tokens(log)
    orchestration = log.setdefault("orchestration", {})
    spawn_plan, warnings = spawn_plan_from_payload(orchestration)
    orchestration["spawn_plan"] = spawn_plan
    if warnings:
        log.setdefault("notes", []).extend(warnings)
    if not str(orchestration.get("orchestrator_fingerprint") or "").strip():
        orchestration["orchestrator_fingerprint"] = orchestrator_fingerprint(
            mirrored_orchestrator_payload(orchestration)
        )
    normalize_spawn_activation(log)
    resolve_planned_workers(log)
    normalize_actual_workers(log)
    packet_metrics = build_result_packet_metrics(
        {
            "packet_sizing": log.get("packet_sizing"),
            "efficiency": log.get("efficiency"),
        }
    )
    log["efficiency"] = build_efficiency_payload(
        packet_metrics,
        planned_workers=((log.get("orchestration") or {}).get("planned_workers") or {}),
        main_model=((log.get("tokens") or {}).get("main_model") or {}),
        subagents=((log.get("tokens") or {}).get("subagents") or []),
    )
    compute_scores(log)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a base evaluation log.")
    init_parser.add_argument("--context", required=True, help="Path to the structured context JSON.")
    init_parser.add_argument("--orchestrator", required=True, help="Path to orchestrator.json.")
    init_parser.add_argument("--lint", help="Optional lint findings JSON.")
    init_parser.add_argument("--output", help="Optional log output path.")

    phase_parser = subparsers.add_parser("phase", help="Merge a deterministic phase result.")
    phase_parser.add_argument("--log", required=True, help="Path to the existing evaluation log.")
    phase_parser.add_argument(
        "--phase",
        required=True,
        choices=["build", "lint", "validate", "apply"],
        help="Workflow phase being merged.",
    )
    phase_parser.add_argument("--result", required=True, help="Path to the phase result JSON.")
    phase_parser.add_argument("--duration-seconds", type=float, help="Optional measured duration.")
    phase_parser.add_argument("--phase-label", help="Optional phase label for repeated phase merges.")

    finalize_parser = subparsers.add_parser("finalize", help="Merge final observations and score the log.")
    finalize_parser.add_argument("--log", required=True, help="Path to the existing evaluation log.")
    finalize_parser.add_argument("--final", required=True, help="Path to the final observations JSON.")
    return parser.parse_args()


def print_summary(path: Path, payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "log_path": str(path),
                "run_id": payload.get("run_id"),
                "result_status": (payload.get("quality") or {}).get("result_status"),
                "overall_score": (payload.get("scoring") or {}).get("overall_score"),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def run_cli(
    *,
    script_path: Path,
    build_base_log_fn: BuildBaseLogFn,
    apply_phase_update_fn: ApplyPhaseUpdateFn,
    finalize_log_fn: Callable[[dict[str, Any], dict[str, Any]], None],
) -> int:
    args = parse_args()

    if args.command == "init":
        context = load_json(Path(args.context))
        orchestrator = load_json(Path(args.orchestrator))
        lint_report = load_json(Path(args.lint)) if args.lint else None
        payload = build_base_log_fn(script_path, context, orchestrator, lint_report)
        output = (
            Path(args.output).resolve()
            if args.output
            else default_output_path(
                (payload.get("repo") or {}).get("repo_root"),
                payload["skill"]["name"],
                payload["run_id"],
            )
        )
        write_json(output, payload)
        print_summary(output, payload)
        return 0

    if args.command == "phase":
        log_path = Path(args.log).resolve()
        payload = load_json(log_path)
        result = load_json(Path(args.result))
        phase_label = getattr(args, "phase_label", None)
        parameters = inspect.signature(apply_phase_update_fn).parameters
        if "phase_label" in parameters:
            apply_phase_update_fn(
                payload,
                args.phase,
                result,
                args.duration_seconds,
                phase_label=phase_label,
            )
        else:
            apply_phase_update_fn(payload, args.phase, result, args.duration_seconds)
        compute_scores(payload)
        write_json(log_path, payload)
        print_summary(log_path, payload)
        return 0

    if args.command == "finalize":
        log_path = Path(args.log).resolve()
        payload = load_json(log_path)
        final_payload = load_json(Path(args.final))
        finalize_log_fn(payload, final_payload)
        write_json(log_path, payload)
        print_summary(log_path, payload)
        return 0

    raise SystemExit(f"Unsupported command: {args.command}")
