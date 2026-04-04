#!/usr/bin/env python3
"""Run an end-to-end smoke test for draft-release-copy on a synthetic temp repo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import release_copy_plan_contract as contract


EXPECTED_PACKET_FILES = (
    "orchestrator.json",
    "global_packet.json",
    "publish_packet.json",
    "readme_packet.json",
    "changes_packet.json",
    "checklist_packet.json",
    "synthesis_packet.json",
)

README_BASE = """# ExampleProduct

Intro text.

## Current Release
Experimental path remains under investigation.

## Current Status
Current status block.

## Settings
| Setting | Default | Purpose |
| --- | --- | --- |
| `SoftCap` | `5000` | Runtime cap. |
"""


README_HEAD = """# ExampleProduct

Intro text.

## Current Release
Experimental path remains under investigation.

## Current Status
Current status block.

## Settings
| Setting | Default | Purpose |
| --- | --- | --- |
| `SoftCap` | `5000` | Runtime cap. |
"""


PUBLISH_BASE = """<Configuration>
  <ShortDescription Value="Current short description" />
  <LongDescription>Current long description.</LongDescription>
  <ModVersion Value="1.0.0" />
  <ChangeLog>- Prior release note.</ChangeLog>
</Configuration>
"""


PUBLISH_HEAD = """<Configuration>
  <ShortDescription Value="Current short description" />
  <LongDescription>Current long description.</LongDescription>
  <ModVersion Value="1.1.0" />
  <ChangeLog>- Diagnostics note for this release.</ChangeLog>
</Configuration>
"""


SETTING_BASE = """namespace ExampleProduct;

public sealed class Setting
{
    public int SoftCap { get; set; }

    public override void SetDefaults()
    {
        SoftCap = 5000;
    }
}
"""


SETTING_HEAD = """namespace ExampleProduct;

public sealed class Setting
{
    public int SoftCap { get; set; }

    public override void SetDefaults()
    {
        SoftCap = 5000;
    }
}
"""


DIAGNOSTICS_HEAD = """namespace ExampleProduct.Systems;

public sealed class OfficeDemandDiagnosticsSystem
{
    public string Describe()
    {
        return "Diagnostics cleanup";
    }
}
"""


MAINTAINING_MD = """# Maintaining

## Release Operations
Keep release copy aligned with shipped behavior.
"""


RELEASE_TEMPLATE = """name: Release checklist
description: Prepare the release checklist.
title: "[Release] "
labels: [release]
body:
  - type: input
    id: target_version
    attributes:
      label: Target version
  - type: textarea
    id: included_changes
    attributes:
      label: Included changes
  - type: textarea
    id: release_gate
    attributes:
      label: Release-gate evidence / validation
  - type: checkboxes
    id: checks
    attributes:
      label: Checklist
      options:
        - label: PublishConfiguration wording reviewed against shipped behavior
        - label: Release notes reviewed
"""


RELEASE_WORKFLOW = """name: release
on:
  push:
    tags:
      - "v*"
jobs:
  publish:
    runs-on: ubuntu-latest
"""


def script_path(name: str) -> Path:
    return Path(__file__).resolve().with_name(name)


def run_command(args: list[str], *, cwd: Path) -> str:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", *args] if args[0].endswith(".py") else args
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        details = "\n".join(part for part in ((result.stderr or "").strip(), (result.stdout or "").strip()) if part)
        detail_suffix = f"\n{details}" if details else ""
        raise RuntimeError(f"Command failed: {' '.join(command)}{detail_suffix}")
    return result.stdout


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(args: list[str], *, cwd: Path) -> str:
    return run_command(["git", *args], cwd=cwd)


def init_repo(repo_root: Path) -> None:
    git(["init"], cwd=repo_root)
    git(["config", "user.name", "Codex Smoke"], cwd=repo_root)
    git(["config", "user.email", "codex-smoke@example.invalid"], cwd=repo_root)

    write_text(repo_root / "README.md", README_BASE)
    write_text(repo_root / "MAINTAINING.md", MAINTAINING_MD)
    write_text(repo_root / ".github/ISSUE_TEMPLATE/release_checklist.yml", RELEASE_TEMPLATE)
    write_text(repo_root / ".github/workflows/release.yml", RELEASE_WORKFLOW)
    write_text(
        repo_root / ".codex/project/profiles/draft-release-copy/profile.json",
        json.dumps(
            {
                "name": "draft-release-copy",
                "summary": "smoke profile",
                "bindings": {
                    "primary_readme_path": "README.md",
                    "settings_source_path": "ExampleProduct/Setting.cs",
                    "publish_config_path": "ExampleProduct/Properties/PublishConfiguration.xml",
                },
                "extra": {
                    "release_copy": {
                        "maintaining_path": "MAINTAINING.md",
                        "release_checklist_template_path": ".github/ISSUE_TEMPLATE/release_checklist.yml",
                        "release_workflow_path": ".github/workflows/release.yml",
                    }
                },
            },
            indent=2,
        ) + "\n",
    )
    write_text(repo_root / "ExampleProduct/Properties/PublishConfiguration.xml", PUBLISH_BASE)
    write_text(repo_root / "ExampleProduct/Setting.cs", SETTING_BASE)
    write_text(repo_root / "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs", "namespace ExampleProduct.Systems;\n")
    git(["add", "."], cwd=repo_root)
    git(["commit", "-m", "Initial release baseline"], cwd=repo_root)
    git(["tag", "v1.0.0"], cwd=repo_root)

    write_text(repo_root / "README.md", README_HEAD)
    write_text(repo_root / "ExampleProduct/Properties/PublishConfiguration.xml", PUBLISH_HEAD)
    write_text(repo_root / "ExampleProduct/Setting.cs", SETTING_HEAD)
    write_text(repo_root / "ExampleProduct/Systems/OfficeDemandDiagnosticsSystem.cs", DIAGNOSTICS_HEAD)
    git(["add", "."], cwd=repo_root)
    git(["commit", "-m", "Refresh diagnostics release copy"], cwd=repo_root)


def build_smoke_plan(context: dict[str, Any], synthesis_packet: dict[str, Any]) -> dict[str, Any]:
    defaults = synthesis_packet.get("plan_defaults") or {}
    draft_basis = defaults.get("draft_basis") or {}
    return {
        "context_fingerprint": defaults.get("context_fingerprint") or context.get("context_fingerprint"),
        "freshness_tuple": defaults.get("freshness_tuple") or context.get("freshness_tuple"),
        "overall_confidence": defaults.get("overall_confidence") or "medium",
        "stop_reasons": [],
        "evidence_status": defaults.get("evidence_status") or "not-applicable",
        "draft_basis": {
            "common_path_sufficient": True,
            "raw_reread_count": 0,
            "reread_reasons": [],
            "focused_packets_used": [],
            "compensatory_reread_detected": False,
            "synthesis_packet_fingerprint": draft_basis.get("synthesis_packet_fingerprint"),
        },
        "publish_update": {"mode": "noop"},
        "readme_update": {"mode": "noop"},
        "issue_action": {"mode": "noop"},
    }


def build_smoke_summary(status: str, reason: str | None, repo_root: Path, next_action: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "reason": reason,
        "repo_root": str(repo_root),
        "next_action": next_action,
    }
    payload.update(extra)
    return payload


def main() -> int:
    smoke_output: dict[str, Any]

    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "draft-release-copy"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        repo_root = temp_dir / "repo"
        repo_root.mkdir()
        init_repo(repo_root)

        context_path = temp_dir / "context.json"
        lint_path = temp_dir / "lint.json"
        packet_dir = temp_dir / "packets"
        build_path = temp_dir / "build.json"
        plan_path = temp_dir / "release-copy-plan.json"
        validation_path = temp_dir / "validation.json"
        apply_path = temp_dir / "apply.json"

        publish_path = repo_root / "ExampleProduct/Properties/PublishConfiguration.xml"
        readme_path = repo_root / "README.md"
        publish_before = publish_path.read_text(encoding="utf-8")
        readme_before = readme_path.read_text(encoding="utf-8")

        run_command(
            [
                str(script_path("collect_release_copy_context.py")),
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
            ],
            cwd=repo_root,
        )
        context = read_json(context_path)

        run_command(
            [
                str(script_path("lint_release_copy.py")),
                "--context",
                str(context_path),
                "--output",
                str(lint_path),
            ],
            cwd=repo_root,
        )
        lint = read_json(lint_path)

        run_command(
            [
                str(script_path("build_release_copy_packets.py")),
                "--context",
                str(context_path),
                "--lint",
                str(lint_path),
                "--output-dir",
                str(packet_dir),
                "--result-output",
                str(build_path),
            ],
            cwd=repo_root,
        )

        packet_files = sorted(path.name for path in packet_dir.iterdir() if path.is_file())
        missing_packets = [name for name in EXPECTED_PACKET_FILES if name not in packet_files]
        if missing_packets:
            raise RuntimeError(f"Missing packet files: {', '.join(missing_packets)}")
        if "packet_metrics.json" not in packet_files:
            raise RuntimeError("packet_metrics.json was not written")

        synthesis_packet = read_json(packet_dir / "synthesis_packet.json")
        orchestrator = read_json(packet_dir / "orchestrator.json")
        packet_metrics = read_json(packet_dir / "packet_metrics.json")
        build_result = read_json(build_path)
        if synthesis_packet.get("common_path_contract", {}).get("sufficient_for_local_final_drafting") is not True:
            raise RuntimeError("synthesis_packet.json is not marked sufficient for common-path local drafting")
        if build_result.get("packet_metrics") != packet_metrics:
            raise RuntimeError("build result packet_metrics disagrees with packet_metrics.json")
        if build_result.get("packet_count") != packet_metrics.get("packet_count"):
            raise RuntimeError("build result packet_count disagrees with packet_metrics.json")
        if build_result.get("estimated_delegation_savings") != packet_metrics.get("estimated_delegation_savings"):
            raise RuntimeError("build result estimated_delegation_savings disagrees with packet_metrics.json")
        if build_result.get("review_mode") != orchestrator.get("review_mode"):
            raise RuntimeError("build result review_mode disagrees with orchestrator.json")
        if build_result.get("common_path_sufficient") is not True:
            raise RuntimeError("build result did not report common-path sufficiency")

        plan = build_smoke_plan(context, synthesis_packet)
        plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        run_command(
            [
                str(script_path("validate_release_copy.py")),
                "--context",
                str(context_path),
                "--lint",
                str(lint_path),
                "--plan",
                str(plan_path),
                "--output",
                str(validation_path),
            ],
            cwd=repo_root,
        )
        validation = read_json(validation_path)
        if validation.get("valid") is not True:
            raise RuntimeError("validate_release_copy.py did not accept the smoke plan")

        run_command(
            [
                str(script_path("apply_release_copy.py")),
                "--validation",
                str(validation_path),
                "--dry-run",
                "--result-output",
                str(apply_path),
            ],
            cwd=repo_root,
        )
        apply_result = read_json(apply_path)
        if apply_result.get("apply_succeeded") is not True:
            raise RuntimeError("apply_release_copy.py did not report success")
        if apply_result.get("raw_reread_count") != 0:
            raise RuntimeError("common-path smoke expected raw_reread_count == 0")
        if apply_result.get("compensatory_reread_detected") is not False:
            raise RuntimeError("common-path smoke expected compensatory_reread_detected == false")
        if publish_path.read_text(encoding="utf-8") != publish_before:
            raise RuntimeError("dry-run mutated PublishConfiguration.xml")
        if readme_path.read_text(encoding="utf-8") != readme_before:
            raise RuntimeError("dry-run mutated README.md")

        smoke_output = build_smoke_summary(
            "ok",
            None,
            repo_root,
            "review_smoke_results",
            base_tag=context.get("base_tag"),
            target_version=context.get("target_version"),
            output_files=packet_files,
            packet_count=packet_metrics.get("packet_count"),
            largest_packet_bytes=packet_metrics.get("largest_packet_bytes"),
            largest_two_packets_bytes=packet_metrics.get("largest_two_packets_bytes"),
            estimated_delegation_savings=packet_metrics.get("estimated_delegation_savings"),
            raw_reread_count=apply_result.get("raw_reread_count"),
            compensatory_reread_detected=apply_result.get("compensatory_reread_detected"),
            apply_succeeded=apply_result.get("apply_succeeded"),
            smoke_output_fields=contract.SMOKE_OUTPUT_FIELDS,
        )

    print(json.dumps(smoke_output, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

