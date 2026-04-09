#!/usr/bin/env python3
"""Emit and update local evaluation logs for gh-fix-pr-writeup."""

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
    findings = (lint_report or {}).get("findings", {})
    messages = common.count_messages(findings, "errors", "warnings")
    expected = list(context.get("expected_template_sections") or [])
    actual = list(context.get("current_body_sections") or [])
    return {
        "title_changed": None,
        "body_changed": None,
        "template_sections_required": len(expected),
        "template_sections_filled": len(
            [section for section in expected if section in actual]
        ),
        "rewrite_strategy": None,
        "qa_required": None,
        "qa_reason": None,
        "qa_ran": None,
        "validation_commands": [],
        "edited_pr_url": context.get("pr", {}).get("url"),
        "delegation_non_use_cases": None,
        "common_path_sufficient": None,
        "raw_reread_count": None,
        "unsupported_claim_categories": sorted(
            {message for message in messages if "unsupported claim" in message.lower()}
        ),
        "evidence_gap_categories": sorted(
            {
                message
                for message in messages
                if "testing" in message.lower() or "evidence" in message.lower()
            }
        ),
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
    orchestration = log.setdefault("orchestration", {})
    if phase == "build":
        if result.get("delegation_non_use_cases") is not None:
            data["delegation_non_use_cases"] = result.get("delegation_non_use_cases")
        if result.get("rewrite_strategy") is not None:
            data["rewrite_strategy"] = result.get("rewrite_strategy")
        if result.get("qa_required") is not None:
            data["qa_required"] = common.to_bool(result.get("qa_required"))
        if result.get("qa_reason") is not None:
            data["qa_reason"] = result.get("qa_reason")
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
        if result.get("qa_required") is not None:
            data["qa_required"] = common.to_bool(result.get("qa_required"))
        if result.get("qa_reason") is not None:
            data["qa_reason"] = result.get("qa_reason")
        if result.get("validation_commands") is not None:
            data["validation_commands"] = common.list_of_strings(
                result.get("validation_commands")
            )
        return

    if phase == "apply":
        if result.get("qa_required") is not None:
            data["qa_required"] = common.to_bool(result.get("qa_required"))
        if result.get("qa_clear") is not None:
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
