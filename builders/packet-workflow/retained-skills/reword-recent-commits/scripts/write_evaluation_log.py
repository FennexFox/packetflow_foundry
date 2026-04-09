#!/usr/bin/env python3
"""Emit and update local evaluation logs for reword-recent-commits."""

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
    commits = context.get("commits", [])
    return {
        "branch": context.get("branch"),
        "count": len(commits) if isinstance(commits, list) else common.safe_int(context.get("count")),
        "rules_reliability": context.get("rules_reliability") or orchestrator.get("rules_reliability"),
        "commit_packet_count": common.safe_int(orchestrator.get("commit_packet_count")),
        "delegation_non_use_cases": None,
        "common_path_sufficient": None,
        "raw_reread_count": None,
        "validation_commands": [],
        "new_head": None,
        "applied_commit_hashes": [],
        "force_push_needed": None,
        "cleanup_succeeded": None,
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
        commit_packet_count = common.safe_int(result.get("commit_packet_count"))
        if commit_packet_count is not None:
            input_size["candidate_batches"] = commit_packet_count
            data["commit_packet_count"] = commit_packet_count
        active_packet_count = common.safe_int(result.get("active_packet_count"))
        if active_packet_count is not None:
            input_size["active_areas"] = active_packet_count
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
    if phase == "validate":
        data["validation_commands"] = ["validate_reword_plan.py"]
        if result.get("rules_reliability") is not None:
            data["rules_reliability"] = result.get("rules_reliability")
        return
    if phase == "apply":
        if result.get("new_head") is not None:
            data["new_head"] = result.get("new_head")
        if isinstance(result.get("applied_commit_hashes"), list):
            data["applied_commit_hashes"] = result.get("applied_commit_hashes")
        if result.get("force_push_needed") is not None:
            data["force_push_needed"] = common.to_bool(result.get("force_push_needed"))
        if result.get("cleanup_succeeded") is not None:
            data["cleanup_succeeded"] = common.to_bool(result.get("cleanup_succeeded"))
        if result.get("rules_reliability") is not None:
            data["rules_reliability"] = result.get("rules_reliability")


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
