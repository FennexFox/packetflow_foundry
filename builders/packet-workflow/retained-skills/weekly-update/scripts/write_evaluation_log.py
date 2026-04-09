#!/usr/bin/env python3
"""Emit and update local evaluation logs for weekly-update."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def resolve_builder_scripts_dir() -> Path:
    script_path = Path(__file__).resolve()
    searched: list[Path] = []
    seen: set[Path] = set()
    for base in script_path.parents:
        for candidate in (
            base / "builders" / "packet-workflow" / "retained-skills" / "scripts",
            base
            / ".codex"
            / "vendor"
            / "packetflow_foundry"
            / "builders"
            / "packet-workflow"
            / "retained-skills"
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

import evaluation_log_common as common  # noqa: E402


def analysis_ref_payload(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("analysis_ref")
    return payload if isinstance(payload, dict) else {}


def find_branch(context: dict[str, Any]) -> str | None:
    analysis_ref = analysis_ref_payload(context)
    branch = str(
        analysis_ref.get("selected_branch_label")
        or analysis_ref.get("selected_branch")
        or context.get("current_branch")
        or context.get("branch")
        or ""
    ).strip()
    return branch or common.default_find_branch(context)


def find_head_sha(context: dict[str, Any]) -> str | None:
    analysis_ref = analysis_ref_payload(context)
    for value in (
        analysis_ref.get("selected_sha"),
        context.get("head_sha"),
        context.get("head_commit"),
    ):
        resolved = str(value or "").strip()
        if resolved:
            return resolved
    return common.default_find_head_sha(context)


def skill_specific_data(
    skill_name: str,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates = list(context.get("candidate_inventory") or [])
    classification_counts: dict[str, int] = {}
    raw_reread_reason_counts: dict[str, int] = {}
    for candidate in candidates:
        classification = str(candidate.get("proposed_classification") or "").strip()
        if classification:
            classification_counts[classification] = (
                classification_counts.get(classification, 0) + 1
            )
        raw_reread_reason = str(candidate.get("raw_reread_reason") or "").strip()
        if raw_reread_reason:
            raw_reread_reason_counts[raw_reread_reason] = (
                raw_reread_reason_counts.get(raw_reread_reason, 0) + 1
            )
    return {
        "reporting_window": context.get("reporting_window"),
        "review_mode": orchestrator.get("review_mode"),
        "selected_packets": list(orchestrator.get("selected_packets") or []),
        "candidate_counts_by_proposed_classification": classification_counts,
        "raw_reread_reason_counts": raw_reread_reason_counts,
        "coverage_gap_count": len(context.get("source_gaps") or []),
        "common_path_sufficient": not raw_reread_reason_counts,
        "raw_reread_count": sum(raw_reread_reason_counts.values()),
        "plan_overall_confidence": None,
        "allow_marker_update": None,
        "marker_update_attempted": None,
        "marker_update_written": None,
    }


def build_base_log(
    script_path: Path,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return common.build_base_log(
        script_path,
        context,
        orchestrator,
        lint_report,
        skill_specific_data_fn=skill_specific_data,
        find_branch_fn=find_branch,
        find_head_sha_fn=find_head_sha,
    )


def apply_phase_update(
    log: dict[str, Any],
    phase: str,
    result: dict[str, Any],
    duration: float | None,
) -> None:
    common.apply_common_phase_update(log, phase, result, duration)
    orchestration = log.setdefault("orchestration", {})
    data = log.setdefault("skill_specific", {}).setdefault("data", {})
    if phase == "build":
        if isinstance(result.get("selected_packets"), list):
            data["selected_packets"] = [
                str(item) for item in result["selected_packets"] if str(item).strip()
            ]
        if isinstance(result.get("candidate_counts_by_proposed_classification"), dict):
            data["candidate_counts_by_proposed_classification"] = result[
                "candidate_counts_by_proposed_classification"
            ]
        if isinstance(result.get("raw_reread_reason_counts"), dict):
            data["raw_reread_reason_counts"] = result["raw_reread_reason_counts"]
            raw_reread_count = sum(
                common.safe_int(value) or 0
                for value in result["raw_reread_reason_counts"].values()
            )
            data["raw_reread_count"] = raw_reread_count
            orchestration["raw_reread_required"] = raw_reread_count > 0
            active_reasons = [
                str(reason)
                for reason, count in result["raw_reread_reason_counts"].items()
                if common.safe_int(count)
            ]
            orchestration["raw_reread_reason"] = (
                ", ".join(active_reasons) if active_reasons else None
            )
        coverage_gap_count = common.safe_int(result.get("coverage_gap_count"))
        if coverage_gap_count is not None:
            data["coverage_gap_count"] = coverage_gap_count
        common_path_sufficient = common.to_bool(result.get("common_path_sufficient"))
        if common_path_sufficient is not None:
            data["common_path_sufficient"] = common_path_sufficient
        return

    if phase == "validate":
        if result.get("overall_confidence") is not None:
            data["plan_overall_confidence"] = result.get("overall_confidence")
        if result.get("allow_marker_update") is not None:
            data["allow_marker_update"] = common.to_bool(result.get("allow_marker_update"))
        return

    if phase == "apply":
        if result.get("overall_confidence") is not None:
            data["plan_overall_confidence"] = result.get("overall_confidence")
        if result.get("allow_marker_update") is not None:
            data["allow_marker_update"] = common.to_bool(result.get("allow_marker_update"))
        if "marker_update_attempted" in result:
            data["marker_update_attempted"] = common.to_bool(
                result.get("marker_update_attempted")
            )
        if "marker_update_written" in result:
            data["marker_update_written"] = common.to_bool(
                result.get("marker_update_written")
            )


def finalize_log(log: dict[str, Any], final_payload: dict[str, Any]) -> None:
    common.finalize_log(log, final_payload)


def main() -> int:
    return common.run_cli(
        script_path=Path(__file__).resolve(),
        build_base_log_fn=build_base_log,
        apply_phase_update_fn=apply_phase_update,
        finalize_log_fn=finalize_log,
    )


load_json = common.load_json
write_json = common.write_json
default_output_path = common.default_output_path
item_packet_count = common.item_packet_count
batch_packet_count = common.batch_packet_count


if __name__ == "__main__":
    raise SystemExit(main())
