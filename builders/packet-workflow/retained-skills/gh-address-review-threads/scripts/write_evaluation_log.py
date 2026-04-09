#!/usr/bin/env python3
"""Emit and update local evaluation logs for gh-address-review-threads."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def resolve_builder_scripts_dir() -> Path:
    script_path = Path(__file__).resolve()
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
            if candidate.is_dir():
                return candidate.resolve()
    raise SystemExit("[ERROR] Missing packet-workflow builder scripts.")


BUILDER_SCRIPTS_DIR = resolve_builder_scripts_dir()
if str(BUILDER_SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(BUILDER_SCRIPTS_DIR))

import evaluation_log_common as common  # noqa: E402


def skill_specific_data(
    skill_name: str,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    counts = orchestrator.get("thread_counts", {})
    return {
        "threads_seen": common.safe_int(counts.get("unresolved")) or 0,
        "threads_accepted": None,
        "threads_rejected": None,
        "threads_deferred": None,
        "threads_defer_outdated": None,
        "threads_resolved": None,
        "outdated_threads_seen": common.safe_int(counts.get("unresolved_outdated")) or 0,
        "outdated_transition_candidates": None,
        "outdated_auto_resolved": None,
        "outdated_recheck_ambiguous": None,
        "adopted_unmarked_reply_count": None,
        "skipped_outdated_count": None,
        "invalid_complete_count": None,
        "resolve_after_complete_count": None,
        "common_path_sufficient": None,
        "build_phase_count": 0,
        "build_phases": {},
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
    )


def loaded_build_metrics(result: dict[str, Any]) -> dict[str, Any] | None:
    metrics = common.build_result_packet_metrics(result)
    if metrics is not None:
        return metrics
    for key in ("packet_metrics_file", "packet_sizing_file"):
        path_text = str(result.get(key) or "").strip()
        if not path_text:
            continue
        path = Path(path_text)
        if path.is_file():
            return common.load_json(path)
    return None


def apply_phase_update(
    log: dict[str, Any],
    phase: str,
    result: dict[str, Any],
    duration: float | None,
    phase_label: str | None = None,
) -> None:
    common.apply_common_phase_update(
        log,
        phase,
        result,
        duration,
        phase_label=phase_label,
    )
    input_size = log.setdefault("input_size", {})
    data = log.setdefault("skill_specific", {}).setdefault("data", {})
    orchestration = log.setdefault("orchestration", {})
    if phase == "build":
        thread_batch_count = common.safe_int(result.get("thread_batch_count"))
        if thread_batch_count is not None:
            input_size["candidate_batches"] = thread_batch_count
        active_areas = result.get("active_areas")
        if isinstance(active_areas, list):
            input_size["active_areas"] = len(active_areas)
        counts = result.get("thread_counts") or {}
        if common.safe_int(counts.get("unresolved")) is not None:
            data["threads_seen"] = common.safe_int(counts.get("unresolved"))
        if common.safe_int(counts.get("unresolved_outdated")) is not None:
            data["outdated_threads_seen"] = common.safe_int(
                counts.get("unresolved_outdated")
            )
        if result.get("common_path_sufficient") is not None:
            data["common_path_sufficient"] = common.to_bool(
                result.get("common_path_sufficient")
            )
        for key in (
            "outdated_transition_candidates",
            "outdated_recheck_ambiguous",
        ):
            if common.safe_int(result.get(key)) is not None:
                data[key] = common.safe_int(result.get(key))
        metrics = loaded_build_metrics(result) or {}
        if phase_label:
            build_phases = data.setdefault("build_phases", {})
            build_phases[phase_label] = {
                "packet_count": common.safe_int(metrics.get("packet_count")),
                "packet_sizing": log.get("packet_sizing"),
                "efficiency": log.get("efficiency"),
            }
            data["build_phase_count"] = len(build_phases)
        orchestration["raw_reread_required"] = False
        return

    if phase == "apply":
        counters = result.get("counters") or {}
        reconciliation_summary = result.get("reconciliation_summary") or {}
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
            if common.safe_int(counters.get(key)) is not None:
                data[key] = common.safe_int(counters.get(key))
        for key in (
            "outdated_transition_candidates",
            "outdated_auto_resolved",
            "outdated_recheck_ambiguous",
        ):
            if common.safe_int(reconciliation_summary.get(key)) is not None:
                data[key] = common.safe_int(reconciliation_summary.get(key))
        mutations = result.get("mutations") or []
        if isinstance(mutations, list):
            data["threads_resolved"] = sum(
                1
                for mutation in mutations
                if isinstance(mutation, dict) and mutation.get("kind") == "resolve_thread"
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


if __name__ == "__main__":
    raise SystemExit(main())
