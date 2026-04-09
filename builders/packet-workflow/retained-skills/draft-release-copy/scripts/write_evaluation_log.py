#!/usr/bin/env python3
"""Emit and update local evaluation logs for draft-release-copy."""

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
    checks = (lint_report or {}).get("checks", {})
    return {
        "base_tag": context.get("base_tag"),
        "evidence_gate_status": "complete" if checks.get("evidence_complete") else "incomplete",
        "publish_fields_changed": [],
        "readme_sections_changed": [],
        "release_issue_created": None,
        "qa_required": None,
        "qa_reason": None,
        "qa_ran": None,
        "validation_commands": [],
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
    if phase == "build":
        qa_gate = result.get("qa_gate_guidance")
        if isinstance(qa_gate, dict):
            data["qa_required"] = common.to_bool(qa_gate.get("required_for_default_plan"))
            data["qa_reason"] = qa_gate.get("reason")
        return
    if phase == "validate":
        if result.get("qa_required") is not None:
            data["qa_required"] = common.to_bool(result.get("qa_required"))
        if result.get("qa_reason") is not None:
            data["qa_reason"] = result.get("qa_reason")
        if result.get("qa_clear") is not None:
            data["qa_ran"] = common.to_bool(result.get("qa_clear"))
        if result.get("validation_commands") is not None:
            data["validation_commands"] = common.list_of_strings(
                result.get("validation_commands")
            )
        return
    if phase == "apply" and result.get("qa_clear") is not None:
        data["qa_ran"] = common.to_bool(result.get("qa_required")) or common.to_bool(
            result.get("qa_clear")
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
