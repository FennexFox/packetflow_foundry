#!/usr/bin/env python3
"""Build compact yet drafting-sufficient packets for draft-release-copy."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import lint_release_copy as lint_tools
import release_copy_plan_contract as contract


GENERATED_FILE_PATTERNS = (
    re.compile(r"(^|/)(bin|obj|dist|build|coverage|generated|gen)/"),
    re.compile(r"\.(g|generated)\.[^.]+$"),
    re.compile(r"\.designer\.[^.]+$"),
    re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|cargo\.lock)$"),
    re.compile(r"\.min\.(js|css)$"),
)

SYNTHESIS_REQUIRED_KEYS = {
    "target_version",
    "base_tag",
    "applicable_gate_tracks",
    "evidence_complete",
    "conservative_wording_requirements",
    "publish_rewrite",
    "readme_rewrite",
    "shipped_change_summary",
    "issue_recommendation",
    "precheck_eligibility",
    "helper_handoff",
    "explicit_stop_risks",
    "common_path_contract",
    "plan_defaults",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_diff_totals(diff_stat: str | None) -> dict[str, int] | None:
    if not diff_stat:
        return None
    last_line = diff_stat.strip().splitlines()[-1]
    files_match = re.search(r"(?P<files>\d+) files? changed", last_line)
    insertions_match = re.search(r"(?P<insertions>\d+) insertions?\(\+\)", last_line)
    deletions_match = re.search(r"(?P<deletions>\d+) deletions?\(-\)", last_line)
    if not files_match and not insertions_match and not deletions_match:
        return None
    files_changed = int(files_match.group("files")) if files_match else 0
    insertions = int(insertions_match.group("insertions")) if insertions_match else 0
    deletions = int(deletions_match.group("deletions")) if deletions_match else 0
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "churn": insertions + deletions,
    }


def is_generated_file(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return any(pattern.search(lowered) for pattern in GENERATED_FILE_PATTERNS)


def core_area_for_path(path: str) -> str | None:
    lowered = path.replace("\\", "/").lower()
    if lowered.startswith(("noofficedemandfix/systems/", "noofficedemandfix/patches/", "noofficedemandfix/telemetry/")):
        return "runtime"
    if lowered in {"noofficedemandfix/mod.cs", "noofficedemandfix/setting.cs"}:
        return "runtime"
    if lowered.startswith((".github/workflows/", ".github/scripts/", ".github/issue_template/", ".github/instructions/")):
        return "process"
    if lowered in {".github/pull_request_template.md", "contributing.md", "maintaining.md", "readme.md"}:
        return "process"
    if lowered.endswith((".csproj", ".props", ".targets")) or lowered in {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "cargo.lock",
    }:
        return "config"
    return None


def active_groups(group_summary: dict[str, dict[str, Any]]) -> list[str]:
    ordered = ("runtime", "automation", "docs", "tests", "config", "other")
    return [name for name in ordered if (group_summary.get(name) or {}).get("count", 0) > 0]


def review_mode(file_count: int, group_count: int, override_signals: list[dict[str, str]]) -> tuple[str, int]:
    if file_count <= contract.SMALL_FILE_LIMIT and group_count <= contract.SMALL_GROUP_LIMIT:
        mode = "local-only"
    elif file_count > contract.MEDIUM_FILE_LIMIT or group_count >= contract.LARGE_GROUP_LIMIT:
        mode = "broad-delegation"
    else:
        mode = "targeted-delegation"

    if override_signals and mode == "local-only":
        mode = "targeted-delegation"
    elif override_signals and mode == "targeted-delegation":
        mode = "broad-delegation"

    if mode == "local-only":
        return mode, 0
    if mode == "targeted-delegation":
        return mode, 2
    return mode, 4 if group_count >= 5 else 3


def packet_worker_map() -> dict[str, list[str]]:
    return contract.packet_worker_map()


def findings_for_area(lint_report: dict[str, Any], areas: set[str]) -> dict[str, list[dict[str, str]]]:
    findings = lint_report.get("findings", {})
    return {
        level: [item for item in findings.get(level, []) if item.get("area") in areas]
        for level in ("errors", "warnings", "info")
    }


def handoff_command(context: dict[str, Any], lint_report: dict[str, Any]) -> str | None:
    helper = context.get("local_release_helper", {})
    if helper.get("status") != "present":
        return None
    if not lint_report.get("checks", {}).get("helper_handoff_allowed"):
        return None
    helper_path = str(helper.get("repo_relative_path") or "")
    if not helper_path.lower().endswith(".ps1"):
        return None
    target_version = str(context.get("target_version") or "").strip()
    version_arg = target_version if target_version.startswith("v") else f"v{target_version}"
    helper_cli_path = ".\\" + helper_path.replace("/", "\\")
    return f"powershell -File {helper_cli_path} -Version {version_arg}"


def unique_commit_subjects(subjects: list[str], limit: int = 4) -> list[str]:
    unique: list[str] = []
    for subject in subjects:
        text = str(subject or "").strip()
        if text and text not in unique:
            unique.append(text)
        if len(unique) >= limit:
            break
    return unique


def top_churn_files(changed_file_stats: dict[str, dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked = []
    for path, stats in changed_file_stats.items():
        churn = int((stats or {}).get("churn", 0) or 0)
        ranked.append(
            {
                "path": str(path),
                "churn": churn,
            }
        )
    ranked.sort(key=lambda item: (-item["churn"], item["path"]))
    return ranked[:limit]


def representative_files(context: dict[str, Any], limit: int = 5) -> list[str]:
    groups = context.get("changed_file_groups") or {}
    selected: list[str] = []
    for group_name in ("runtime", "automation", "docs", "tests", "config", "other"):
        sample_files = ((groups.get(group_name) or {}).get("sample_files") or [])
        for path in sample_files:
            text = str(path or "").strip()
            if text and text not in selected:
                selected.append(text)
            if len(selected) >= limit:
                return selected
    for path in context.get("changed_files", []):
        text = str(path or "").strip()
        if text and text not in selected:
            selected.append(text)
        if len(selected) >= limit:
            break
    return selected


def setting_default_mismatches(lint_report: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for finding in lint_report.get("findings", {}).get("warnings", []):
        if finding.get("code") == "setting_default_mismatch":
            message = str(finding.get("message") or "").strip()
            if message:
                mismatches.append(message)
    return mismatches


def significant_topic_signals(context: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for signal in lint_tools.significant_changelog_topics(context):
        matching_files = list(signal.get("matching_files") or [])
        sample_files = [str(item.get("path") or "").strip() for item in matching_files[:2] if str(item.get("path") or "").strip()]
        signals.append(
            {
                "id": signal.get("id"),
                "label": signal.get("label"),
                "matching_file_count": int(signal.get("matching_file_count", 0) or 0),
                "matching_subject_count": int(signal.get("matching_subject_count", 0) or 0),
                "churn_sum": int(signal.get("churn_sum", 0) or 0),
                "sample_files": sample_files,
                "evidence_anchor": sample_files[0] if sample_files else signal.get("label"),
            }
        )
    return signals


def unresolved_evidence_placeholders(context: dict[str, Any], lint_report: dict[str, Any]) -> list[str]:
    checks = lint_report.get("checks", {}) or {}
    if checks.get("evidence_complete"):
        return []
    tracks = checks.get("applicable_validation_tracks", {}) or {}
    placeholders: list[str] = []
    if tracks.get("software_gate"):
        placeholders.extend(
            [
                "comparable software evidence",
                "software anchor comparison summary",
                "software release PR validation note",
            ]
        )
    if tracks.get("telemetry_validation"):
        placeholders.extend(
            [
                "telemetry validation artifact",
                "telemetry validation summary",
            ]
        )
    if not placeholders:
        placeholders.append("explicit note that no scoped release gate applies")
    return placeholders


def conservative_wording_requirements(lint_report: dict[str, Any]) -> list[str]:
    checks = lint_report.get("checks", {}) or {}
    requirements = [
        "Do not present the software path as solved without complete applicable evidence.",
        "Keep helper wording local and optional.",
    ]
    if not checks.get("evidence_complete"):
        requirements.append("Keep release wording conservative and preserve unresolved evidence placeholders.")
    if any((checks.get("applicable_validation_tracks") or {}).values()):
        requirements.append("Match release-gate language to the applicable software or telemetry tracks.")
    return requirements


def explicit_stop_risks(lint_report: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    checks = lint_report.get("checks", {}) or {}
    if not checks.get("evidence_complete"):
        risks.append(
            {
                "category": "release_gate_incomplete",
                "message": "Applicable release-gate evidence is incomplete; conservative wording and unresolved checklist placeholders remain required.",
            }
        )
    if str((context.get("local_release_helper") or {}).get("status") or "") == "missing_local_release_script":
        risks.append(
            {
                "category": "missing_local_release_script",
                "message": "Local helper handoff is unavailable; the workflow may continue without helper execution guidance.",
            }
        )
    for finding in lint_report.get("findings", {}).get("errors", []):
        message = str(finding.get("message") or "").strip()
        if message:
            risks.append({"category": str(finding.get("code") or "lint_error"), "message": message})
    return risks


def issue_delta_summary(existing_issue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(existing_issue, dict):
        return None
    evidence = existing_issue.get("evidence") or {}
    return {
        "number": existing_issue.get("number"),
        "title": str(existing_issue.get("title") or "").strip(),
        "url": str(existing_issue.get("url") or "").strip(),
        "state": str(existing_issue.get("state") or "").strip(),
        "checked_item_count": len(list(existing_issue.get("checked_labels") or [])),
        "evidence_keys_present": sorted(key for key, value in evidence.items() if str(value or "").strip()),
    }


def issue_defaults(context: dict[str, Any]) -> dict[str, Any]:
    defaults = context.get("issue_defaults")
    return defaults if isinstance(defaults, dict) else {}


def issue_action_recommendation(context: dict[str, Any]) -> dict[str, Any]:
    existing_issue = context.get("existing_release_issue")
    title_prefix = str(issue_defaults(context).get("title_prefix") or "[Release]").strip() or "[Release]"
    title = f"{title_prefix} {contract.normalize_release_version(str(context.get('target_version') or ''))}".strip()
    if isinstance(existing_issue, dict):
        return {
            "mode": "sync-existing-body",
            "title": title,
            "reason": "A matching open release issue already exists; prefer reusing and syncing it.",
        }
    return {
        "mode": "create",
        "title": title,
        "reason": "No matching open release issue was discovered; create a new one if the draft reaches apply-safe status.",
    }


def publish_rewrite_guidance(context: dict[str, Any], lint_report: dict[str, Any], topic_signals: list[dict[str, Any]]) -> dict[str, Any]:
    checks = lint_report.get("checks", {}) or {}
    publish = context.get("publish_configuration", {}) or {}
    prior = context.get("base_tag_publish_configuration", {}) or {}
    rewrite_fields = ["change_log"]
    if checks.get("rewrite_publish_recommended"):
        rewrite_fields.extend(["short_description", "long_description"])
    if publish.get("mod_version") != context.get("target_version"):
        rewrite_fields.append("mod_version")
    rewrite_fields = [field for index, field in enumerate(rewrite_fields) if field not in rewrite_fields[:index]]
    return {
        "current": {
            "short_description": publish.get("short_description"),
            "long_description": publish.get("long_description"),
            "change_log": publish.get("change_log"),
            "mod_version": publish.get("mod_version"),
        },
        "prior_release_change_log": prior.get("change_log"),
        "rewrite_required_fields": rewrite_fields,
        "topic_anchors": [
            {
                "topic": signal.get("label"),
                "evidence_anchor": signal.get("evidence_anchor"),
            }
            for signal in topic_signals
        ],
        "lint_findings": findings_for_area(lint_report, {"publish"}),
    }


def readme_rewrite_guidance(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, Any]:
    checks = lint_report.get("checks", {}) or {}
    readme = context.get("readme", {}) or {}
    rewrite_sections: list[str] = []
    rewrite_intro = False
    if checks.get("rewrite_readme_recommended"):
        rewrite_sections.extend(["Current Release", "Current Status"])
        rewrite_intro = True
    return {
        "current_intro": readme.get("intro_text"),
        "current_sections": {
            "Current Release": ((readme.get("sections") or {}).get("Current Release")),
            "Current Status": ((readme.get("sections") or {}).get("Current Status")),
        },
        "rewrite_intro": rewrite_intro,
        "rewrite_required_sections": rewrite_sections,
        "settings_default_mismatches": setting_default_mismatches(lint_report),
        "lint_findings": findings_for_area(lint_report, {"readme", "copy"}),
    }


def precheck_eligibility(context: dict[str, Any]) -> dict[str, Any]:
    target_version = str(context.get("target_version") or "").strip()
    configured_version = str(((context.get("publish_configuration") or {}).get("mod_version")) or "").strip()
    return {
        "eligible": [
            "PublishConfiguration wording reviewed against shipped behavior",
            "Diagnostics wording reviewed",
            *(
                ["Tag/version confirmed"]
                if target_version and configured_version and target_version == configured_version
                else []
            ),
        ],
        "must_remain_unchecked": [
            "Release build completed successfully",
            "Applicable release-gate evidence or validation artifacts captured",
            "Applicable comparison summaries and release PR validation notes recorded",
            "Release notes reviewed",
            "Local release script verified",
        ],
    }


def issue_recommendation(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, Any]:
    recommendation = issue_action_recommendation(context)
    return {
        "existing_issue": issue_delta_summary(context.get("existing_release_issue")),
        "issue_action_recommendation": recommendation,
        "unresolved_evidence_placeholders": unresolved_evidence_placeholders(context, lint_report),
        "project_mode_default": str(issue_defaults(context).get("project_mode") or "auto-add-first"),
    }


def raw_local_bundle(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "publish_configuration": context.get("publish_configuration"),
        "base_tag_publish_configuration": context.get("base_tag_publish_configuration"),
        "readme": context.get("readme"),
        "setting_defaults": context.get("setting_defaults"),
        "changed_files": context.get("changed_files"),
        "changed_file_stats": context.get("changed_file_stats"),
        "commit_subjects": context.get("commit_subjects"),
        "existing_release_issue": context.get("existing_release_issue"),
        "evidence": context.get("evidence"),
        "lint_findings": lint_report.get("findings"),
        "lint_checks": lint_report.get("checks"),
    }


def synthesis_packet_common_path_ready(packet: dict[str, Any]) -> bool:
    if not SYNTHESIS_REQUIRED_KEYS.issubset(packet):
        return False
    contract_payload = packet.get("common_path_contract") or {}
    if contract_payload.get("sufficient_for_local_final_drafting") is not True:
        return False
    if contract_payload.get("packet_insufficiency_is_failure") is not True:
        return False
    if contract_payload.get("max_additional_focused_packets") != contract.COMMON_PATH_MAX_FOCUSED_PACKETS:
        return False
    plan_defaults = packet.get("plan_defaults") or {}
    draft_basis = plan_defaults.get("draft_basis") or {}
    return (
        draft_basis.get("common_path_sufficient") is True
        and int(draft_basis.get("raw_reread_count", 0) or 0) == 0
        and draft_basis.get("compensatory_reread_detected") is False
    )


def build_synthesis_packet(context: dict[str, Any], lint_report: dict[str, Any], topic_signals: list[dict[str, Any]]) -> dict[str, Any]:
    checks = lint_report.get("checks", {}) or {}
    packet = {
        "purpose": "Local-only decision packet for final release drafting. This packet must be sufficient for local final drafting in the common path.",
        "local_only": True,
        "target_version": context.get("target_version"),
        "base_tag": context.get("base_tag"),
        "revision_range": context.get("revision_range"),
        "applicable_gate_tracks": checks.get("applicable_validation_tracks", {}),
        "evidence_complete": bool(checks.get("evidence_complete")),
        "conservative_wording_requirements": conservative_wording_requirements(lint_report),
        "publish_rewrite": publish_rewrite_guidance(context, lint_report, topic_signals),
        "readme_rewrite": readme_rewrite_guidance(context, lint_report),
        "shipped_change_summary": {
            "topic_signals": topic_signals,
            "top_churn_files": top_churn_files(context.get("changed_file_stats", {}) or {}),
            "representative_files": representative_files(context),
            "condensed_commit_subjects": unique_commit_subjects(list(context.get("commit_subjects", []))),
            "diff_totals": parse_diff_totals(context.get("diff_stat")),
        },
        "issue_recommendation": issue_recommendation(context, lint_report),
        "precheck_eligibility": precheck_eligibility(context),
        "helper_handoff": {
            "status": (context.get("local_release_helper") or {}).get("status"),
            "available": bool(lint_report.get("checks", {}).get("helper_handoff_allowed")),
            "command": handoff_command(context, lint_report),
        },
        "explicit_stop_risks": explicit_stop_risks(lint_report, context),
        "common_path_contract": {
            "sufficient_for_local_final_drafting": True,
            "raw_reread_should_be_exceptional": True,
            "packet_insufficiency_is_failure": True,
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "raw_reread_allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
        },
        "plan_defaults": {
            "context_fingerprint": context.get("context_fingerprint"),
            "freshness_tuple": context.get("freshness_tuple"),
            "overall_confidence": "high" if checks.get("evidence_complete") else "medium",
            "evidence_status": "complete" if checks.get("evidence_complete") else (
                "incomplete" if any((checks.get("applicable_validation_tracks") or {}).values()) else "not-applicable"
            ),
            "draft_basis": {
                "common_path_sufficient": True,
                "raw_reread_count": 0,
                "reread_reasons": [],
                "focused_packets_used": [],
                "compensatory_reread_detected": False,
                "synthesis_packet_fingerprint": "",
            },
            "issue_action_recommendation": issue_action_recommendation(context),
        },
    }
    packet["plan_defaults"]["draft_basis"]["synthesis_packet_fingerprint"] = contract.json_fingerprint(packet)
    return packet


def build_packet_payloads(context: dict[str, Any], lint_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changed_files = list(context.get("changed_files", []))
    group_summary = context.get("changed_file_groups", {})
    active_group_names = active_groups(group_summary)
    diff_totals = parse_diff_totals(context.get("diff_stat"))
    generated_file_count = sum(1 for path in changed_files if is_generated_file(path))
    generated_file_ratio = (generated_file_count / len(changed_files)) if changed_files else 0.0
    core_areas_touched = sorted(
        {
            area
            for path in changed_files
            if (area := core_area_for_path(path)) is not None
        }
    )
    overrides: list[dict[str, str]] = []
    if (diff_totals or {}).get("churn", 0) >= contract.CHURN_OVERRIDE_LIMIT:
        overrides.append(
            {
                "reason": "diff_stat_threshold",
                "detail": f"Release diff churn reached {(diff_totals or {}).get('churn', 0)} lines (threshold {contract.CHURN_OVERRIDE_LIMIT}).",
            }
        )
    if len(core_areas_touched) >= 2:
        overrides.append(
            {
                "reason": "core_files_across_groups",
                "detail": "Core runtime/config/process files span multiple groups: " + ", ".join(core_areas_touched),
            }
        )
    if generated_file_count and generated_file_ratio < 0.5:
        overrides.append(
            {
                "reason": "generated_files_not_majority",
                "detail": f"Generated files are present but not the majority ({generated_file_count}/{len(changed_files)}).",
            }
        )
    mode, worker_count = review_mode(len(changed_files), len(active_group_names), overrides)
    topic_signals = significant_topic_signals(context)

    global_packet = {
        "workflow_family": contract.WORKFLOW_FAMILY,
        "repo_slug": context.get("repo_slug"),
        "branch": context.get("branch"),
        "head_commit": context.get("head_commit"),
        "base_tag": context.get("base_tag"),
        "target_version": context.get("target_version"),
        "authority_order": contract.AUTHORITY_ORDER,
        "gate_summary": {
            "evidence_complete": lint_report.get("checks", {}).get("evidence_complete"),
            "applicable_tracks": lint_report.get("checks", {}).get("applicable_validation_tracks", {}),
            "helper_status": (context.get("local_release_helper") or {}).get("status"),
            "helper_handoff_allowed": lint_report.get("checks", {}).get("helper_handoff_allowed"),
        },
        "worker_return_contract": contract.WORKER_RETURN_CONTRACT,
        "worker_output_shape": contract.WORKER_OUTPUT_SHAPE,
        "disallowed_claims": [
            "Do not present the software track as solved without complete applicable software-gate evidence.",
            "Do not claim release-facing files were updated unless the current run actually edited them.",
            "Do not describe the local helper as a shared team workflow asset.",
        ],
    }

    publish_packet = {
        "current_publish_fields": {
            "short_description": (context.get("publish_configuration") or {}).get("short_description"),
            "long_description": (context.get("publish_configuration") or {}).get("long_description"),
            "change_log": (context.get("publish_configuration") or {}).get("change_log"),
            "mod_version": (context.get("publish_configuration") or {}).get("mod_version"),
        },
        "prior_release_change_log": (context.get("base_tag_publish_configuration") or {}).get("change_log"),
        "rewrite_required_fields": publish_rewrite_guidance(context, lint_report, topic_signals)["rewrite_required_fields"],
        "lint_findings": findings_for_area(lint_report, {"publish"}),
    }

    readme_packet = {
        "intro_text": (context.get("readme") or {}).get("intro_text"),
        "current_sections": {
            "Current Release": ((context.get("readme") or {}).get("sections") or {}).get("Current Release"),
            "Current Status": ((context.get("readme") or {}).get("sections") or {}).get("Current Status"),
        },
        "settings_default_mismatches": setting_default_mismatches(lint_report),
        "rewrite_required_sections": readme_rewrite_guidance(context, lint_report)["rewrite_required_sections"],
        "lint_findings": findings_for_area(lint_report, {"readme", "copy"}),
    }

    changes_packet = {
        "revision_range": context.get("revision_range"),
        "diff_totals": diff_totals,
        "topic_signals": topic_signals,
        "top_churn_files": top_churn_files(context.get("changed_file_stats", {}) or {}),
        "representative_files": representative_files(context),
        "condensed_commit_subjects": unique_commit_subjects(list(context.get("commit_subjects", []))),
        "active_groups": active_group_names,
    }

    checklist_packet = {
        "issue_title": issue_action_recommendation(context)["title"],
        "existing_issue": issue_delta_summary(context.get("existing_release_issue")),
        "template": {
            "title_prefix": (context.get("release_checklist") or {}).get("title_prefix"),
            "fields": (context.get("release_checklist") or {}).get("fields"),
            "checkbox_labels": (context.get("release_checklist") or {}).get("checkbox_labels"),
        },
        "unresolved_placeholders": unresolved_evidence_placeholders(context, lint_report),
        "lint_findings": findings_for_area(lint_report, {"checklist", "evidence", "helper"}),
    }

    synthesis_packet = build_synthesis_packet(context, lint_report, topic_signals)

    packet_payloads: dict[str, dict[str, Any]] = {
        "global_packet.json": global_packet,
        "publish_packet.json": publish_packet,
        "readme_packet.json": readme_packet,
        "changes_packet.json": changes_packet,
        "checklist_packet.json": checklist_packet,
        "synthesis_packet.json": synthesis_packet,
    }
    if context.get("evidence"):
        packet_payloads["evidence_packet.json"] = {
            "applicable_tracks": lint_report.get("checks", {}).get("applicable_validation_tracks", {}),
            "evidence_fields": context.get("evidence"),
            "missing_placeholders": unresolved_evidence_placeholders(context, lint_report),
            "complete": lint_report.get("checks", {}).get("evidence_complete"),
        }

    packet_sizes = contract.packet_size_summary(packet_payloads)
    raw_bundle_bytes = contract.packet_size_bytes(raw_local_bundle(context, lint_report))
    packet_sizes["raw_local_source_bytes"] = raw_bundle_bytes
    packet_sizes["estimated_raw_source_tokens"] = contract.estimate_token_proxy(raw_bundle_bytes)

    recommended_workers: list[dict[str, Any]] = []
    optional_workers: list[dict[str, Any]] = []
    if mode == "targeted-delegation":
        recommended_workers = [
            {
                "name": "rules",
                "agent_type": "docs_verifier",
                "packets": ["global_packet.json", "checklist_packet.json", "readme_packet.json"],
                "responsibility": "Extract hard release checklist constraints, README wording constraints, and issue-creation policy.",
                "reasoning_effort": "medium",
            },
            {
                "name": "release-copy",
                "agent_type": "large_diff_auditor",
                "packets": ["global_packet.json", "publish_packet.json", "changes_packet.json"],
                "responsibility": "Summarize release-copy drift and supported release bullets.",
                "reasoning_effort": "medium",
                "model": "gpt-5.4-mini",
            },
        ]
    elif mode == "broad-delegation":
        recommended_workers.extend(
            [
                {
                    "name": "rules",
                    "agent_type": "docs_verifier",
                    "packets": ["global_packet.json", "checklist_packet.json", "readme_packet.json"],
                    "responsibility": "Extract hard release checklist constraints, README wording constraints, and issue-creation policy.",
                    "reasoning_effort": "medium",
                },
                {
                    "name": "release-copy",
                    "agent_type": "large_diff_auditor",
                    "packets": ["global_packet.json", "publish_packet.json", "changes_packet.json"],
                    "responsibility": "Summarize release-copy drift and supported release bullets.",
                    "reasoning_effort": "medium",
                    "model": "gpt-5.4-mini",
                },
                {
                    "name": "mapping",
                    "agent_type": "repo_mapper",
                    "packets": ["global_packet.json", "checklist_packet.json", "changes_packet.json"],
                    "responsibility": "Confirm authority order, packet membership, and release scope.",
                    "reasoning_effort": "low",
                },
            ]
        )
        if context.get("evidence") and worker_count >= 4:
            recommended_workers.append(
                {
                    "name": "evidence",
                    "agent_type": "evidence_summarizer",
                    "packets": ["global_packet.json", "evidence_packet.json"],
                    "responsibility": "Summarize normalized release-gate evidence or validation inputs.",
                    "reasoning_effort": "low",
                }
            )

    packet_files = [
        contract.SHARED_PACKET,
        "publish_packet.json",
        "readme_packet.json",
        "changes_packet.json",
        "checklist_packet.json",
        *(["evidence_packet.json"] if "evidence_packet.json" in packet_payloads else []),
        contract.SHARED_LOCAL_PACKET,
        "orchestrator.json",
    ]

    packet_metrics = {
        "worker_facing_packets": packet_sizes["worker_facing_packets"],
        "local_only_packets": sorted(name for name in packet_payloads if name in {contract.SHARED_LOCAL_PACKET}),
        "packet_count": len(packet_files),
        "packet_size_bytes": {
            "by_packet": packet_sizes["by_packet"],
            "worker_facing_total": packet_sizes["worker_facing_total"],
            "local_only_total": packet_sizes["local_only_total"],
            "raw_local_source_bytes": packet_sizes["raw_local_source_bytes"],
            "total": packet_sizes["total"],
        },
        "largest_packet_bytes": packet_sizes["largest_packet_bytes"],
        "largest_two_packets_bytes": packet_sizes["largest_two_packets_bytes"],
        "estimated_local_only_tokens": packet_sizes["estimated_local_only_tokens"],
        "estimated_packet_tokens": packet_sizes["estimated_packet_tokens"],
        "estimated_delegation_savings": packet_sizes["estimated_delegation_savings"],
        "estimated_raw_source_tokens": packet_sizes["estimated_raw_source_tokens"],
        "raw_reread_allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
        "synthesis_packet_sufficient_for_common_path": synthesis_packet_common_path_ready(synthesis_packet),
    }

    packet_payloads["orchestrator.json"] = {
        "target_version": context.get("target_version"),
        "base_tag": context.get("base_tag"),
        "review_mode": mode,
        "recommended_worker_count": len(recommended_workers),
        "worker_return_contract": contract.WORKER_RETURN_CONTRACT,
        "worker_output_shape": contract.WORKER_OUTPUT_SHAPE,
        "workflow_family": contract.WORKFLOW_FAMILY,
        "archetype": contract.ARCHETYPE,
        "orchestrator_profile": contract.ORCHESTRATOR_PROFILE,
        "preferred_worker_families": contract.PREFERRED_WORKER_FAMILIES,
        "packet_worker_map": contract.packet_worker_map(),
        "worker_selection_guidance": contract.WORKER_SELECTION_GUIDANCE,
        "routing_contract": contract.runtime_field_roles(),
        "shared_packet": contract.SHARED_PACKET,
        "shared_local_packet": contract.SHARED_LOCAL_PACKET,
        "review_overrides": overrides,
        "helper_status": (context.get("local_release_helper") or {}).get("status"),
        "raw_reread_allowed_reasons": contract.RAW_REREAD_ALLOWED_REASONS,
        "common_path_contract": {
            "required_packets": [contract.SHARED_PACKET, contract.SHARED_LOCAL_PACKET],
            "max_additional_focused_packets": contract.COMMON_PATH_MAX_FOCUSED_PACKETS,
            "synthesis_packet_must_be_sufficient": True,
            "raw_reread_should_be_exceptional": True,
            "packet_insufficiency_is_failure": True,
        },
        "local_responsibilities": [
            "Read global_packet.json and synthesis_packet.json first.",
            "Keep common-path drafting on those packets plus at most one focused packet.",
            "Treat raw reread as exceptional only for allowed reasons.",
            "Draft a local release-copy plan before validation.",
            "Run validator before any deterministic file or issue mutation.",
            "Apply release-facing file edits and the issue action only from validator-normalized output.",
            "Do not execute the local release helper.",
        ],
        "packet_files": packet_files,
        "recommended_workers": recommended_workers,
        "optional_workers": optional_workers,
    }
    packet_payloads["packet_metrics.json"] = packet_metrics
    return packet_payloads


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build compact release-copy packets for token-efficient release preparation."
    )
    parser.add_argument("--context", required=True, help="Path to JSON from collect_release_copy_context.py")
    parser.add_argument("--lint", required=True, help="Path to JSON from lint_release_copy.py")
    parser.add_argument("--output-dir", required=True, help="Directory for generated packets")
    args = parser.parse_args()

    context = load_json(Path(args.context))
    lint_report = load_json(Path(args.lint))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    packets = build_packet_payloads(context, lint_report)
    for file_name, payload in packets.items():
        contract.write_json(output_dir / file_name, payload)

    orchestrator = packets["orchestrator.json"]
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "review_mode": orchestrator["review_mode"],
                "packet_files": orchestrator["packet_files"],
                "recommended_worker_count": orchestrator["recommended_worker_count"],
                "packet_metrics_file": str(output_dir / "packet_metrics.json"),
                "estimated_delegation_savings": packets["packet_metrics.json"]["estimated_delegation_savings"],
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
