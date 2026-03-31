#!/usr/bin/env python3
"""Run an opt-in end-to-end smoke test for the weekly-update CLI wrappers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from weekly_update_lib import OUTPUT_SECTIONS


EXPECTED_PACKET_FILES = (
    "orchestrator.json",
    "global_packet.json",
    "mapping_packet.json",
    "changes_packet.json",
    "incidents_packet.json",
    "risks_packet.json",
)
EXPECTED_EVAL_FILES = ("packet_metrics.json",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", help="Repository root to inspect. Defaults to the current working directory.")
    parser.add_argument("--profile", help="Path to the active repo profile JSON.")
    parser.add_argument("--window-days", type=int, default=7, help="Window size passed through to collect.")
    parser.add_argument("--now-utc", help="Optional deterministic ISO8601 UTC timestamp override for collect.")
    return parser.parse_args()


def script_path(name: str) -> Path:
    return Path(__file__).resolve().with_name(name)


def repo_root_path(value: str | None) -> Path | None:
    if value:
        candidate = Path(value).resolve()
        return candidate if (candidate / ".git").exists() else None
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def smoke_summary(status: str, reason: str | None, repo_root: Path | None, next_action: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "reason": reason,
        "repo_root": str(repo_root) if repo_root else None,
        "next_action": next_action,
    }
    payload.update(extra)
    return payload


def run_script(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", *args]
    try:
        return subprocess.run(command, cwd=str(cwd) if cwd else None, env=env, text=True, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = "\n".join(part for part in (stderr, stdout) if part)
        detail_suffix = f"\n{details}" if details else ""
        raise RuntimeError(f"Command failed: {' '.join(command)}{detail_suffix}") from exc


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_minimal_plan(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_id": context.get("context_id"),
        "context_fingerprint": context.get("context_fingerprint"),
        "reporting_window": context.get("reporting_window"),
        "selected_packets": ["mapping_packet", "changes_packet", "incidents_packet", "risks_packet"],
        "overall_confidence": "high",
        "stop_reasons": [],
        "allow_marker_update": False,
        "sections": {section: [] for section in OUTPUT_SECTIONS},
    }


def missing_packet_files(packet_dir: Path) -> list[str]:
    return [name for name in EXPECTED_PACKET_FILES if not (packet_dir / name).is_file()]


def missing_eval_files(packet_dir: Path) -> list[str]:
    return [name for name in EXPECTED_EVAL_FILES if not (packet_dir / name).is_file()]


def main() -> int:
    args = parse_args()
    repo_root = repo_root_path(args.repo_root)
    if repo_root is None:
        print(
            json.dumps(
                smoke_summary(
                    "blocked",
                    "git_repo_required",
                    None if args.repo_root is None else Path(args.repo_root).resolve(),
                    "run_from_repo_or_pass_repo_root",
                ),
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    smoke_result: dict[str, Any]

    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "weekly-update"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        context_path = temp_dir / "context.json"
        lint_path = temp_dir / "lint.json"
        packet_dir = temp_dir / "packets"
        build_result_path = temp_dir / "build-result.json"
        plan_path = temp_dir / "weekly-update-plan.json"
        plan_validation_path = temp_dir / "weekly-update-plan-validation.json"
        apply_result_path = temp_dir / "apply-result.json"
        eval_log_path = temp_dir / "eval-log.json"

        run_script(
            [
                str(script_path("collect_weekly_update_context.py")),
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
                *(["--profile", args.profile] if args.profile else []),
                "--window-days",
                str(args.window_days),
                *(
                    ["--now-utc", args.now_utc]
                    if args.now_utc
                    else []
                ),
            ]
        )
        context = read_json(context_path)
        if not context:
            raise RuntimeError("collect_weekly_update_context.py produced an empty context payload")

        run_script(
            [
                str(script_path("lint_weekly_update.py")),
                "--context",
                str(context_path),
                "--output",
                str(lint_path),
            ]
        )
        run_script(
            [
                str(script_path("build_weekly_update_packets.py")),
                "--context",
                str(context_path),
                "--lint",
                str(lint_path),
                "--output-dir",
                str(packet_dir),
                "--result-output",
                str(build_result_path),
            ]
        )
        build_result = read_json(build_result_path)
        packet_metrics = read_json(packet_dir / "packet_metrics.json")

        packet_files = sorted(path.name for path in packet_dir.iterdir() if path.is_file())
        missing_packets = missing_packet_files(packet_dir)
        if missing_packets:
            raise RuntimeError(f"Missing packet files: {', '.join(missing_packets)}")
        missing_eval = missing_eval_files(packet_dir)
        if missing_eval:
            raise RuntimeError(f"Missing evaluation-side packet files: {', '.join(missing_eval)}")
        expected_file_count = len(EXPECTED_PACKET_FILES) + len(EXPECTED_EVAL_FILES)
        if len(packet_files) != expected_file_count:
            raise RuntimeError(f"Expected {expected_file_count} packet-side files, found {len(packet_files)}")
        if not (packet_dir / "orchestrator.json").is_file():
            raise RuntimeError("orchestrator.json was not written")
        if not (packet_dir / "global_packet.json").is_file():
            raise RuntimeError("global_packet.json was not written")
        orchestrator = read_json(packet_dir / "orchestrator.json")
        if "estimated_packet_tokens" in orchestrator or "packet_size_bytes" in orchestrator:
            raise RuntimeError("orchestrator.json unexpectedly contains token-efficiency counters")
        if packet_metrics.get("estimated_packet_tokens", 0) >= packet_metrics.get("estimated_local_only_tokens", 0):
            raise RuntimeError("packet_metrics.json did not report token-efficiency savings")
        if build_result.get("common_path_sufficient") is not True:
            raise RuntimeError("weekly-update smoke run required raw rereads in the common path")
        if int(build_result.get("raw_reread_count") or 0) != 0:
            raise RuntimeError("weekly-update smoke run reported raw rereads")

        plan = build_minimal_plan(context)
        plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        run_script(
            [
                str(script_path("write_evaluation_log.py")),
                "init",
                "--context",
                str(context_path),
                "--orchestrator",
                str(packet_dir / "orchestrator.json"),
                "--lint",
                str(lint_path),
                "--output",
                str(eval_log_path),
            ]
        )
        run_script(
            [
                str(script_path("write_evaluation_log.py")),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "build",
                "--result",
                str(build_result_path),
            ]
        )
        run_script(
            [
                str(script_path("validate_weekly_update_plan.py")),
                "--context",
                str(context_path),
                "--plan",
                str(plan_path),
                "--output",
                str(plan_validation_path),
            ]
        )
        plan_validation = read_json(plan_validation_path)
        if plan_validation.get("valid") is not True:
            raise RuntimeError("validate_weekly_update_plan.py did not accept the smoke plan")
        run_script(
            [
                str(script_path("write_evaluation_log.py")),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "validate",
                "--result",
                str(plan_validation_path),
            ]
        )
        run_script(
            [
                str(script_path("apply_weekly_update.py")),
                "--context",
                str(context_path),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--result-output",
                str(apply_result_path),
            ]
        )
        apply_result = read_json(apply_result_path)
        if apply_result.get("apply_succeeded") is not True:
            raise RuntimeError("apply_weekly_update.py did not report success")
        if apply_result.get("marker_update_written") is not False:
            raise RuntimeError("apply_weekly_update.py unexpectedly wrote the marker")
        if apply_result.get("primary_artifact") is not None:
            raise RuntimeError("apply_weekly_update.py reported an unexpected primary artifact")
        run_script(
            [
                str(script_path("write_evaluation_log.py")),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "apply",
                "--result",
                str(apply_result_path),
            ]
        )
        eval_log = read_json(eval_log_path)
        if eval_log.get("skill", {}).get("name") != "weekly-update":
            raise RuntimeError("write_evaluation_log.py did not initialize a weekly-update log")
        if eval_log.get("skill_specific", {}).get("data", {}).get("estimated_packet_tokens") != packet_metrics.get("estimated_packet_tokens"):
            raise RuntimeError("Build metrics did not merge into the evaluation log")

        smoke_result = smoke_summary(
            "ok",
            None,
            repo_root,
            "review_smoke_results",
            context_id=context.get("context_id"),
            packet_count=packet_metrics.get("packet_count"),
            packet_files=packet_files,
            plan_valid=bool(plan_validation.get("valid")),
            apply_succeeded=bool(apply_result.get("apply_succeeded")),
            marker_update_written=bool(apply_result.get("marker_update_written")),
            estimated_local_only_tokens=packet_metrics.get("estimated_local_only_tokens"),
            estimated_packet_tokens=packet_metrics.get("estimated_packet_tokens"),
            estimated_delegation_savings=packet_metrics.get("estimated_delegation_savings"),
            common_path_sufficient=build_result.get("common_path_sufficient"),
            raw_reread_count=build_result.get("raw_reread_count"),
        )

    print(json.dumps(smoke_result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
