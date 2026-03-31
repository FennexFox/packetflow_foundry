#!/usr/bin/env python3
"""Emit and update local evaluation logs for packet-driven skills."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SKILL_FAMILY = "repo-packet-workflow"
SKILL_VERSION = "unversioned"
DEFAULT_FORMULA_VERSION = "1.0"
DEFAULT_BASELINE_METHOD = "none"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


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


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if key == "notes" and isinstance(value, list):
            base.setdefault("notes", [])
            base["notes"].extend(str(item) for item in value if str(item).strip())
            continue
        if key == "skill_specific" and isinstance(value, dict):
            target = base.setdefault("skill_specific", {"schema_name": "", "schema_version": "1.0", "data": {}})
            if "schema_name" in value:
                target["schema_name"] = value["schema_name"]
            if "schema_version" in value:
                target["schema_version"] = value["schema_version"]
            data_value = value.get("data")
            if isinstance(data_value, dict):
                target.setdefault("data", {})
                deep_merge(target["data"], data_value)
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


def skill_identity(script_path: Path) -> dict[str, str]:
    skill_root = script_path.resolve().parents[1]
    frontmatter = parse_frontmatter(skill_root)
    return {
        "name": frontmatter.get("name", skill_root.name),
        "family": SKILL_FAMILY,
        "archetype": infer_archetype(skill_root),
        "skill_version": SKILL_VERSION,
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


def find_branch(context: dict[str, Any]) -> str | None:
    branch = str(context.get("branch") or "").strip()
    if branch:
        return branch
    branch_state = context.get("branch_state") or {}
    branch = str(branch_state.get("branch") or "").strip()
    if branch:
        return branch
    pr = context.get("pr", {})
    return str(pr.get("headRefName") or "").strip() or None


def find_head_sha(context: dict[str, Any]) -> str | None:
    for key in ("head_sha", "head_commit"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    pr = context.get("pr", {})
    return str(pr.get("headRefOid") or "").strip() or None


def find_base_ref(context: dict[str, Any]) -> str | None:
    for key in ("base_ref", "base_tag", "base_commit"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    pr = context.get("pr", {})
    return str(pr.get("baseRefName") or "").strip() or None


def packet_files(orchestrator: dict[str, Any]) -> list[str]:
    return [str(item) for item in orchestrator.get("packet_files", []) if str(item).strip()]


def item_packet_count(orchestrator: dict[str, Any]) -> int:
    shared = {"global_packet.json", "rules_packet.json", "orchestrator.json"}
    count = 0
    for name in packet_files(orchestrator):
        lowered = name.lower()
        if lowered in shared or "batch-packet" in lowered or lowered.startswith("batch-"):
            continue
        count += 1
    return count


def batch_packet_count(orchestrator: dict[str, Any]) -> int:
    return sum(
        1
        for name in packet_files(orchestrator)
        if "batch-packet" in name.lower() or name.lower().startswith("batch-")
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
        return sum(1 for entry in context["files"] if str(entry.get("change_kind") or "") == "untracked")
    return safe_int(context.get("untracked_files")) or 0


def diff_churn(orchestrator: dict[str, Any], context: dict[str, Any]) -> int:
    diff_summary = orchestrator.get("diff_summary", {})
    totals = diff_summary.get("diff_stat_totals") or {}
    if safe_int(totals.get("churn")) is not None:
        return int(totals["churn"])
    totals = context.get("diff_stat_totals") or {}
    return safe_int(totals.get("churn")) or 0


def normalize_override_signals(orchestrator: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()
    for key in ("review_mode_overrides", "review_overrides"):
        for item in orchestrator.get(key, []):
            if isinstance(item, dict):
                reason = str(item.get("reason") or "").strip()
                if reason and reason not in seen:
                    seen.add(reason)
                    signals.append(reason)
            else:
                text = str(item).strip()
                if text and text not in seen:
                    seen.add(text)
                    signals.append(text)
    return signals


def load_packet_metrics_from_build_result(result: dict[str, Any]) -> dict[str, Any]:
    packet_metrics_file = result.get("packet_metrics_file")
    if not packet_metrics_file:
        return {}
    path = Path(str(packet_metrics_file))
    if not path.is_file():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def common_path_failure_reasons(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for item in result.get("common_path_failures") or []:
        if not isinstance(item, dict):
            continue
        for reason in item.get("explicit_reread_reasons") or []:
            text = str(reason).strip()
            if text and text not in reasons:
                reasons.append(text)
    return reasons


def worker_roles(orchestrator: dict[str, Any]) -> list[str]:
    roles = []
    for item in orchestrator.get("recommended_workers", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("agent_type") or item.get("role") or item.get("name") or "").strip()
        if role:
            roles.append(role)
    return roles


def count_messages(findings: dict[str, Any], *keys: str) -> list[str]:
    messages: list[str] = []
    for key in keys:
        value = findings.get(key)
        if isinstance(value, list):
            messages.extend(str(item) for item in value if str(item).strip())
    return messages


def summarize_findings(lint_report: dict[str, Any] | None) -> dict[str, Any]:
    findings = (lint_report or {}).get("findings", {})
    messages = count_messages(findings, "errors", "warnings", "info")
    unsupported = [message for message in messages if "unsupported claim" in message.lower()]
    evidence = [
        message
        for message in messages
        if any(token in message.lower() for token in ("evidence", "tested", "testing", "verification", "command"))
    ]
    template = [
        message
        for message in messages
        if any(token in message.lower() for token in ("template", "section", "placeholder", "blank bullet", "body contains"))
    ]
    return {
        "messages": messages,
        "unsupported_claims_found": len(unsupported),
        "evidence_gaps_found": len(evidence),
        "template_violations_found": len(template),
    }


def skill_specific_data(
    skill_name: str,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    findings = (lint_report or {}).get("findings", {})
    messages = count_messages(findings, "errors", "warnings")
    if skill_name == "gh-fix-pr-writeup":
        expected = list(context.get("expected_template_sections") or [])
        actual = list(context.get("current_body_sections") or [])
        return {
            "title_changed": None,
            "body_changed": None,
            "template_sections_required": len(expected),
            "template_sections_filled": len([section for section in expected if section in actual]),
            "unsupported_claim_categories": sorted({message for message in messages if "unsupported claim" in message.lower()}),
            "evidence_gap_categories": sorted({message for message in messages if "testing" in message.lower() or "evidence" in message.lower()}),
        }
    if skill_name == "gh-address-review-threads":
        counts = orchestrator.get("thread_counts", {})
        marker_summary = orchestrator.get("marker_conflict_summary", {})
        return {
            "review_mode": orchestrator.get("review_mode"),
            "packet_count": len(packet_files(orchestrator)),
            "worker_count": safe_int(orchestrator.get("recommended_worker_count")) or len(worker_roles(orchestrator)),
            "thread_batch_count": safe_int((orchestrator.get("analysis_targets") or {}).get("batch_count")) or 0,
            "singleton_thread_packet_count": sum(1 for name in packet_files(orchestrator) if name.startswith("thread-")),
            "common_path_sufficient": None,
            "threads_seen": safe_int(counts.get("unresolved")) or 0,
            "threads_accepted": None,
            "threads_rejected": None,
            "threads_deferred": None,
            "threads_defer_outdated": None,
            "threads_resolved": None,
            "outdated_threads_seen": safe_int(counts.get("unresolved_outdated")) or 0,
            "marker_conflicts": len(orchestrator.get("marker_conflicts", [])),
            "marker_conflicts_warning": safe_int((marker_summary.get("by_severity") or {}).get("warning")) or 0,
            "marker_conflicts_adoption_blocking": safe_int((marker_summary.get("by_severity") or {}).get("adoption-blocking")) or 0,
            "marker_conflicts_hard_stop": safe_int((marker_summary.get("by_severity") or {}).get("hard-stop")) or 0,
            "adopted_unmarked_reply_count": 0,
            "skipped_outdated_count": 0,
            "invalid_complete_count": 0,
            "resolve_after_complete_count": 0,
            "validation_commands": [],
            "final_pr_url": context.get("pr", {}).get("url"),
            "estimated_packet_tokens": None,
            "estimated_delegation_savings": None,
        }
    if skill_name == "reword-recent-commits":
        commits = context.get("commits", [])
        return {
            "commits_in_scope": len(commits) if isinstance(commits, list) else safe_int(context.get("count")) or 0,
            "commits_rewritten": None,
            "rewrite_strategy": None,
            "force_push_needed": None,
        }
    if skill_name == "prepare-release-copy":
        checks = (lint_report or {}).get("checks", {})
        return {
            "base_tag": context.get("base_tag"),
            "evidence_gate_status": "complete" if checks.get("evidence_complete") else "incomplete",
            "publish_fields_changed": [],
            "readme_sections_changed": [],
            "release_issue_created": None,
        }
    if skill_name == "git-split-and-commit":
        return {
            "commit_buckets_planned": None,
            "commit_buckets_applied": None,
            "hunk_splits_attempted": sum(1 for name in packet_files(orchestrator) if "split-file" in name.lower()),
            "hunk_splits_blocked": None,
            "targeted_checks_failed": 0,
        }
    if skill_name == "packet-workflow-skill-builder":
        spec = context.get("spec") or {}
        generated = context.get("generated_files") or []
        return {
            "requested_archetype": spec.get("archetype"),
            "requested_domain_slug": spec.get("domain_slug"),
            "generated_file_count": len(generated) if isinstance(generated, list) else 0,
            "includes_optional_local_helper": bool(spec.get("optional_local_helper")),
            "template_validation_passed": None,
        }
    return {"custom_metrics": {}}


def derive_run_id(skill_name: str, context: dict[str, Any]) -> tuple[str, str]:
    timestamp = isoformat_utc()
    ref = find_head_sha(context) or context.get("context_id") or context.get("run_id") or "nohead"
    return f"{timestamp}__{skill_name}__{slugify(str(ref))[:16]}", timestamp


def safe_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "-", value).strip(" .")
    return sanitized or "evaluation-log"


def default_output_path(skill_name: str, run_id: str) -> Path:
    return Path.home() / ".codex" / "tmp" / "evaluation_logs" / skill_name / f"{safe_filename(run_id)}.json"


def build_base_log(
    script_path: Path,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    identity = skill_identity(script_path)
    skill_name = identity["name"]
    run_id, timestamp = derive_run_id(skill_name, context)
    lint_summary = summarize_findings(lint_report)
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
            "branch": find_branch(context),
            "head_sha": find_head_sha(context),
            "base_ref": find_base_ref(context),
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
            "candidate_batches": safe_int((orchestrator.get("analysis_targets") or {}).get("batch_count")) or 0,
            "split_file_packets": sum(1 for name in packet_files(orchestrator) if "split-file" in name.lower()),
            "active_areas": active_area_count(context, orchestrator),
            "diff_churn_lines": diff_churn(orchestrator, context),
        },
        "orchestration": {
            "review_mode": orchestrator.get("review_mode"),
            "override_signals": normalize_override_signals(orchestrator),
            "worker_count": safe_int(orchestrator.get("recommended_worker_count")) or len(worker_roles(orchestrator)),
            "worker_roles": worker_roles(orchestrator),
            "batch_packets_used": batch_packet_count(orchestrator),
            "item_packets_used": item_packet_count(orchestrator),
            "global_packet_used": "global_packet.json" in packet_files(orchestrator) or orchestrator.get("shared_packet") == "global_packet.json",
            "rules_packet_used": "rules_packet.json" in packet_files(orchestrator),
            "raw_reread_required": False,
            "raw_reread_reason": None,
            "low_confidence_stop": False,
            "stop_reasons": [],
        },
        "baseline": {
            "method": DEFAULT_BASELINE_METHOD,
            "confidence": "unavailable",
            "paired_run_available": False,
            "baseline_skill_version": None,
            "estimated_local_only_tokens": None,
            "estimated_token_savings": None,
            "estimated_delegation_savings": None,
        },
        "measurement": {
            "token_source": "unavailable",
            "latency_source": "unavailable",
            "quality_source": "unavailable",
        },
        "tokens": {
            "main_model": {
                "model": None,
                "reasoning_effort": None,
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
            },
            "subagents": [],
            "total_input_tokens": None,
            "total_output_tokens": None,
            "total_reasoning_tokens": None,
            "main_model_token_share": None,
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
            "apply_attempted": False,
            "apply_succeeded": None,
            "mutation_type": None,
            "rollback_needed": False,
            "active_git_operation_detected": context.get("active_operation") is not None,
            "fingerprint_match": None,
            "ambiguous_hunk_match": False,
            "marker_conflict_detected": len(orchestrator.get("marker_conflicts", [])) > 0,
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
        "notes": [],
        "skill_specific": {
            "schema_name": skill_name,
            "schema_version": "1.0",
            "data": skill_specific_data(skill_name, context, orchestrator, lint_report),
        },
    }


def update_latency(log: dict[str, Any], phase: str, duration: float | None) -> None:
    if duration is None:
        return
    mapping = {
        "build": "packet_builder_seconds",
        "lint": "linter_seconds",
        "validate": "validator_seconds",
        "apply": "apply_seconds",
    }
    key = mapping.get(phase)
    if key:
        log.setdefault("latency", {})[key] = round(duration, 3)
        log.setdefault("measurement", {})["latency_source"] = "measured"


def bool_score(value: bool | None, true_score: float = 1.0, false_score: float = 0.0) -> float | None:
    if value is None:
        return None
    return true_score if value else false_score


def linear_penalty(count: int | None, penalty: float, floor: float = 0.0) -> float | None:
    if count is None:
        return None
    return max(floor, 1.0 - penalty * max(count, 0))


def weighted_average(items: list[tuple[float | None, float]]) -> float | None:
    filtered = [(value, weight) for value, weight in items if value is not None]
    if not filtered:
        return None
    total_weight = sum(weight for _value, weight in filtered)
    return round(sum(value * weight for value, weight in filtered) / total_weight, 3)


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


def score_token_share(value: Any) -> float | None:
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


def score_baseline_savings(baseline: dict[str, Any]) -> float | None:
    savings = safe_float(baseline.get("estimated_token_savings"))
    reference = safe_float(baseline.get("estimated_local_only_tokens"))
    if savings is None or reference is None or reference <= 0:
        return None
    return round(max(0.0, min(1.0, savings / reference)), 3)


def compute_scores(log: dict[str, Any]) -> None:
    orchestration = log.get("orchestration", {})
    quality = log.get("quality", {})
    safety = log.get("safety", {})
    baseline = log.get("baseline", {})
    tokens = log.get("tokens", {})

    efficiency = weighted_average(
        [
            (score_worker_fit(orchestration.get("review_mode"), orchestration.get("worker_count")), 0.25),
            (bool_score(to_bool(orchestration.get("global_packet_used")), 1.0, 0.0), 0.1),
            (bool_score(not bool(orchestration.get("raw_reread_required")), 1.0, 0.4), 0.2),
            (linear_penalty(safe_int(quality.get("rerun_count")), 0.25, floor=0.25), 0.2),
            (score_token_share(tokens.get("main_model_token_share")), 0.15),
            (score_baseline_savings(baseline), 0.1),
        ]
    )

    severity = str(quality.get("human_post_edit_severity") or "unknown").lower()
    severity_scores = {"none": 1.0, "low": 0.75, "medium": 0.5, "high": 0.25, "unknown": 0.6}
    human_edit_required = to_bool(quality.get("human_post_edit_required"))
    human_edit_score = None
    if human_edit_required is not None:
        human_edit_score = 1.0 if not human_edit_required else severity_scores.get(severity, 0.6)

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
            (bool_score(to_bool(safety.get("apply_succeeded")), 1.0, 0.2) if apply_attempted else None, 0.1),
        ]
    )

    overall = weighted_average([(efficiency, 0.2), (quality_score, 0.35), (safety_score, 0.45)])

    log.setdefault("scoring", {})
    log["scoring"]["formula_version"] = DEFAULT_FORMULA_VERSION
    log["scoring"]["efficiency_score"] = efficiency
    log["scoring"]["quality_score"] = quality_score
    log["scoring"]["safety_score"] = safety_score
    log["scoring"]["overall_score"] = overall


def apply_phase_update(log: dict[str, Any], phase: str, result: dict[str, Any], duration: float | None) -> None:
    update_latency(log, phase, duration)
    if phase == "build":
        orchestration = log.setdefault("orchestration", {})
        baseline = log.setdefault("baseline", {})
        measurement = log.setdefault("measurement", {})
        skill_data = log.setdefault("skill_specific", {}).setdefault("data", {})
        if result.get("review_mode"):
            orchestration["review_mode"] = result.get("review_mode")
        worker_count = safe_int(result.get("recommended_worker_count"))
        if worker_count is not None:
            orchestration["worker_count"] = worker_count
        if isinstance(result.get("recommended_workers"), list):
            orchestration["worker_roles"] = [
                str(item.get("agent_type") or item.get("role") or item.get("name") or "").strip()
                for item in result["recommended_workers"]
                if isinstance(item, dict) and str(item.get("agent_type") or item.get("role") or item.get("name") or "").strip()
            ]
        override_reasons = []
        for item in result.get("override_signals") or []:
            if isinstance(item, dict):
                reason = str(item.get("reason") or "").strip()
                if reason:
                    override_reasons.append(reason)
        if override_reasons:
            orchestration["override_signals"] = override_reasons
        common_path_sufficient = to_bool(result.get("common_path_sufficient"))
        if common_path_sufficient is not None:
            skill_data["common_path_sufficient"] = common_path_sufficient
            orchestration["raw_reread_required"] = not common_path_sufficient
        reread_reasons = common_path_failure_reasons(result)
        if reread_reasons:
            orchestration["raw_reread_reason"] = reread_reasons[0] if len(reread_reasons) == 1 else "multiple"
            orchestration["stop_reasons"] = list(dict.fromkeys(list(orchestration.get("stop_reasons") or []) + reread_reasons))
        thread_counts = result.get("thread_counts") or {}
        unresolved = safe_int(thread_counts.get("unresolved"))
        outdated = safe_int(thread_counts.get("unresolved_outdated"))
        if unresolved is not None:
            skill_data["threads_seen"] = unresolved
        if outdated is not None:
            skill_data["outdated_threads_seen"] = outdated
        batch_count = safe_int(result.get("thread_batch_count"))
        if batch_count is not None:
            skill_data["thread_batch_count"] = batch_count
        singleton_count = safe_int(result.get("singleton_thread_packet_count"))
        if singleton_count is not None:
            skill_data["singleton_thread_packet_count"] = singleton_count
        packet_metrics = load_packet_metrics_from_build_result(result)
        packet_count = safe_int(packet_metrics.get("packet_count"))
        if packet_count is not None:
            skill_data["packet_count"] = packet_count
        estimated_local = safe_int(packet_metrics.get("estimated_local_only_tokens"))
        estimated_packet = safe_int(packet_metrics.get("estimated_packet_tokens"))
        estimated_savings = safe_int(packet_metrics.get("estimated_delegation_savings"))
        if estimated_local is not None:
            baseline["estimated_local_only_tokens"] = estimated_local
        if estimated_savings is not None:
            baseline["estimated_token_savings"] = estimated_savings
            baseline["estimated_delegation_savings"] = estimated_savings
            skill_data["estimated_delegation_savings"] = estimated_savings
        if estimated_packet is not None:
            skill_data["estimated_packet_tokens"] = estimated_packet
        if packet_metrics:
            measurement["token_source"] = "estimated"
        return

    if phase == "lint":
        lint_like = result.get("findings", result)
        lint_summary = summarize_findings({"findings": lint_like})
        quality = log.setdefault("quality", {})
        quality["unsupported_claims_found"] = lint_summary["unsupported_claims_found"]
        quality["evidence_gaps_found"] = lint_summary["evidence_gaps_found"]
        quality["template_violations_found"] = lint_summary["template_violations_found"]
        log.setdefault("measurement", {})["quality_source"] = "estimated"
        return

    if phase == "validate":
        safety = log.setdefault("safety", {})
        orchestration = log.setdefault("orchestration", {})
        skill_data = log.setdefault("skill_specific", {}).setdefault("data", {})
        safety["validation_run"] = True

        validation_passed = None
        if "validation_passed" in result:
            validation_passed = to_bool(result.get("validation_passed"))
        elif "valid" in result:
            validation_passed = to_bool(result.get("valid"))
        elif "ok" in result:
            validation_passed = to_bool(result.get("ok"))
        elif "can_apply" in result and "errors" in result:
            validation_passed = to_bool(result.get("can_apply")) and not bool(result.get("errors"))
        safety["validation_passed"] = validation_passed

        fingerprint_match = result.get("fingerprint_match")
        if fingerprint_match is not None:
            safety["fingerprint_match"] = to_bool(fingerprint_match)

        ambiguous_match = result.get("ambiguous_hunk_match")
        if ambiguous_match is not None:
            safety["ambiguous_hunk_match"] = to_bool(ambiguous_match)
        merge_skill_counters(skill_data, result.get("counters"))

        stop_reasons = result.get("stop_reasons") or []
        if isinstance(stop_reasons, list) and stop_reasons:
            existing = list(orchestration.get("stop_reasons") or [])
            for reason in stop_reasons:
                if isinstance(reason, str) and reason not in existing:
                    existing.append(reason)
            orchestration["stop_reasons"] = existing
            orchestration["low_confidence_stop"] = any(
                "low confidence" in str(reason).lower() for reason in existing
            )
        return

    if phase == "apply":
        safety = log.setdefault("safety", {})
        quality = log.setdefault("quality", {})
        outputs = log.setdefault("outputs", {})
        orchestration = log.setdefault("orchestration", {})
        skill_data = log.setdefault("skill_specific", {}).setdefault("data", {})
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

        fingerprint_match = result.get("fingerprint_match")
        if fingerprint_match is not None:
            safety["fingerprint_match"] = to_bool(fingerprint_match)
        ambiguous_match = result.get("ambiguous_hunk_match")
        if ambiguous_match is not None:
            safety["ambiguous_hunk_match"] = to_bool(ambiguous_match)
        rollback_needed = result.get("rollback_needed")
        if rollback_needed is not None:
            safety["rollback_needed"] = to_bool(rollback_needed)

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
            if log.get("skill", {}).get("name") == "gh-address-review-threads":
                resolved = sum(1 for item in mutations if isinstance(item, dict) and item.get("kind") == "resolve_thread")
                if resolved:
                    skill_data["threads_resolved"] = resolved
        if result.get("primary_artifact"):
            outputs["primary_artifact"] = result.get("primary_artifact")
        secondary = result.get("secondary_artifacts")
        if isinstance(secondary, list):
            outputs["secondary_artifacts"] = secondary
        merge_skill_counters(skill_data, result.get("counters"))

        stop_reasons = result.get("stop_reasons") or []
        if isinstance(stop_reasons, list) and stop_reasons:
            existing = list(orchestration.get("stop_reasons") or [])
            for reason in stop_reasons:
                if isinstance(reason, str) and reason not in existing:
                    existing.append(reason)
            orchestration["stop_reasons"] = existing
            orchestration["low_confidence_stop"] = orchestration.get("low_confidence_stop") or any(
                "low confidence" in str(reason).lower() for reason in existing
            )

        if dry_run:
            quality["result_status"] = "dry-run"
        elif apply_succeeded is True:
            quality["result_status"] = "completed"
        elif stop_reasons:
            quality["result_status"] = "stopped"
        elif apply_attempted:
            quality["result_status"] = "failed"
        return


def merge_skill_counters(skill_data: dict[str, Any], counters: Any) -> None:
    if not isinstance(skill_data, dict) or not isinstance(counters, dict):
        return
    for key in (
        "adopted_unmarked_reply_count",
        "skipped_outdated_count",
        "invalid_complete_count",
        "resolve_after_complete_count",
        "threads_accepted",
        "threads_rejected",
        "threads_deferred",
        "threads_defer_outdated",
    ):
        value = safe_int(counters.get(key))
        if value is not None:
            skill_data[key] = value


def normalize_tokens(log: dict[str, Any]) -> None:
    tokens = log.setdefault("tokens", {})
    main_model = tokens.setdefault("main_model", {})
    subagents = tokens.get("subagents")
    if not isinstance(subagents, list):
        subagents = []
        tokens["subagents"] = subagents

    def token_value(section: dict[str, Any], key: str) -> int:
        return safe_int(section.get(key)) or 0

    main_input = token_value(main_model, "input_tokens")
    main_output = token_value(main_model, "output_tokens")
    main_reasoning = token_value(main_model, "reasoning_tokens")
    sub_input = 0
    sub_output = 0
    sub_reasoning = 0
    for agent in subagents:
        if not isinstance(agent, dict):
            continue
        sub_input += token_value(agent, "input_tokens")
        sub_output += token_value(agent, "output_tokens")
        sub_reasoning += token_value(agent, "reasoning_tokens")

    total_input = main_input + sub_input
    total_output = main_output + sub_output
    total_reasoning = main_reasoning + sub_reasoning
    if total_input:
        tokens["total_input_tokens"] = total_input
    if total_output:
        tokens["total_output_tokens"] = total_output
    if total_reasoning:
        tokens["total_reasoning_tokens"] = total_reasoning
    if total_input:
        tokens["main_model_token_share"] = round(main_input / total_input, 3)

    if total_input or total_output or total_reasoning:
        log.setdefault("measurement", {})["token_source"] = "measured"


def finalize_log(log: dict[str, Any], final_payload: dict[str, Any]) -> None:
    deep_merge(log, final_payload)

    notes = log.get("notes")
    if not isinstance(notes, list):
        log["notes"] = []
    else:
        deduped: list[str] = []
        for note in notes:
            if isinstance(note, str) and note not in deduped:
                deduped.append(note)
        log["notes"] = deduped

    measurement = log.setdefault("measurement", {})
    if log.get("tokens", {}).get("main_model", {}).get("model") or log.get("tokens", {}).get("subagents"):
        measurement["token_source"] = "measured"
    if log.get("quality", {}).get("first_pass_usable") is not None and measurement.get("quality_source") == "unavailable":
        measurement["quality_source"] = "self_assessed"

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
            if measurement.get("latency_source") == "unavailable":
                measurement["latency_source"] = "estimated"

    normalize_tokens(log)
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

    finalize_parser = subparsers.add_parser("finalize", help="Merge final agent observations and score the log.")
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
        )
    )


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()

    if args.command == "init":
        context = load_json(Path(args.context))
        orchestrator = load_json(Path(args.orchestrator))
        lint_report = load_json(Path(args.lint)) if args.lint else None
        payload = build_base_log(script_path, context, orchestrator, lint_report)
        output = Path(args.output).resolve() if args.output else default_output_path(payload["skill"]["name"], payload["run_id"])
        write_json(output, payload)
        print_summary(output, payload)
        return 0

    if args.command == "phase":
        log_path = Path(args.log).resolve()
        payload = load_json(log_path)
        result = load_json(Path(args.result))
        apply_phase_update(payload, args.phase, result, args.duration_seconds)
        compute_scores(payload)
        write_json(log_path, payload)
        print_summary(log_path, payload)
        return 0

    if args.command == "finalize":
        log_path = Path(args.log).resolve()
        payload = load_json(log_path)
        final_payload = load_json(Path(args.final))
        finalize_log(payload, final_payload)
        write_json(log_path, payload)
        print_summary(log_path, payload)
        return 0

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
