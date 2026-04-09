#!/usr/bin/env python3
"""Emit and update local evaluation logs for public-docs-sync."""

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
    classifications = (lint_report or {}).get("classifications", {})
    return {
        "hard_drift_count": len(classifications.get("hard_drift", [])),
        "review_required_count": len(classifications.get("review_required", [])),
        "link_error_count": len(classifications.get("link_error", [])),
        "stale_baseline_count": len(classifications.get("stale_baseline", [])),
        "auto_apply_candidate_count": len((lint_report or {}).get("auto_apply_candidates", [])),
        "selected_packets": list(orchestrator.get("selected_packets") or []),
        "deterministic_edit_count": common.safe_int(context.get("deterministic_edit_count")),
        "manual_review_count": common.safe_int(context.get("manual_review_count")),
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
    if phase == "build":
        if isinstance(result.get("selected_packets"), list):
            data["selected_packets"] = [
                str(item) for item in result["selected_packets"] if str(item).strip()
            ]
        active_packet_count = common.safe_int(result.get("active_packet_count"))
        if active_packet_count is not None:
            input_size["active_areas"] = active_packet_count
        if result.get("auto_apply_candidate_count") is not None:
            data["auto_apply_candidate_count"] = common.safe_int(
                result.get("auto_apply_candidate_count")
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
