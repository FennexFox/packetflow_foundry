#!/usr/bin/env python3
"""Emit and update local evaluation logs for git-split-and-commit."""

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
while str(BUILDER_SCRIPTS_DIR) in sys.path:
    sys.path.remove(str(BUILDER_SCRIPTS_DIR))
sys.path.insert(0, str(BUILDER_SCRIPTS_DIR))

import evaluation_log_common as common  # noqa: E402


def skill_specific_data(
    skill_name: str,
    context: dict[str, Any],
    orchestrator: dict[str, Any],
    lint_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "commit_buckets_planned": common.safe_int(orchestrator.get("candidate_batch_count")),
        "commit_buckets_applied": None,
        "split_file_count": common.safe_int(orchestrator.get("split_file_count")),
        "decision_ready_packets": common.to_bool(
            orchestrator.get("decision_ready_packets")
        ),
        "raw_reread_count": len(orchestrator.get("raw_reread_reasons", []) or []),
        "common_path_sufficient": common.to_bool(
            orchestrator.get("common_path_sufficient")
        ),
        "delegation_non_use_cases": None,
        "targeted_checks_failed": 0,
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


def apply_phase_update(
    log: dict[str, Any],
    phase: str,
    result: dict[str, Any],
    duration: float | None,
) -> None:
    common.apply_common_phase_update(log, phase, result, duration)
    data = log.setdefault("skill_specific", {}).setdefault("data", {})
    input_size = log.setdefault("input_size", {})
    orchestration = log.setdefault("orchestration", {})
    if phase == "build":
        active_packet_count = common.safe_int(result.get("active_packet_count"))
        if active_packet_count is not None:
            input_size["active_areas"] = active_packet_count
        candidate_batch_count = common.safe_int(result.get("candidate_batch_count"))
        if candidate_batch_count is not None:
            input_size["candidate_batches"] = candidate_batch_count
            data["commit_buckets_planned"] = candidate_batch_count
        split_file_count = common.safe_int(result.get("split_file_count"))
        if split_file_count is not None:
            data["split_file_count"] = split_file_count
        if result.get("delegation_non_use_cases") is not None:
            data["delegation_non_use_cases"] = result.get("delegation_non_use_cases")
        if result.get("common_path_sufficient") is not None:
            data["common_path_sufficient"] = common.to_bool(
                result.get("common_path_sufficient")
            )
        if result.get("raw_reread_count") is not None:
            data["raw_reread_count"] = common.safe_int(result.get("raw_reread_count"))
            orchestration["raw_reread_required"] = (
                common.safe_int(result.get("raw_reread_count")) or 0
            ) > 0
        return
    if phase == "apply":
        counters = result.get("counters") or {}
        if common.safe_int(counters.get("commit_buckets_applied")) is not None:
            data["commit_buckets_applied"] = common.safe_int(
                counters.get("commit_buckets_applied")
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
