#!/usr/bin/env python3
"""Smoke-test the public-docs-sync workflow on a temp repository."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_python(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"python {' '.join(args)} failed")
    return result


def run_git(repo_root: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def create_repo(repo_root: Path) -> None:
    (repo_root / "ExampleProduct").mkdir(parents=True, exist_ok=True)
    (repo_root / ".codex" / "project" / "profiles" / "public-docs-sync").mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)

    (repo_root / "README.md").write_text(
        "\n".join(
            [
                "# Project",
                "",
                "| Setting | Default | Purpose |",
                "| --- | --- | --- |",
                "| `EnableThing` | `false` | Turn the feature on. |",
                "",
                "See the [Guide](./missing.md).",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "CONTRIBUTING.md").write_text("Public docs live in README.old.md\n", encoding="utf-8")
    (repo_root / "LOG_REPORTING.md").write_text("# Log Reporting\n", encoding="utf-8")
    (repo_root / "PERF_REPORTING.md").write_text("# Perf Reporting\n", encoding="utf-8")
    (repo_root / "MAINTAINING.md").write_text("# Maintaining\n", encoding="utf-8")
    (repo_root / ".github" / "pull_request_template.md").write_text("## Summary\n", encoding="utf-8")
    (repo_root / ".github" / "software-evidence-schema.md").write_text("# Schema\n", encoding="utf-8")
    (repo_root / ".github" / "software-investigation-workflow.md").write_text("# Workflow\n", encoding="utf-8")
    (repo_root / ".github" / "workflows").mkdir(exist_ok=True)
    (repo_root / ".github" / "workflows" / "release.yml").write_text("name: release\n", encoding="utf-8")
    write_json(
        repo_root / ".codex" / "project" / "profiles" / "public-docs-sync" / "profile.json",
        {
            "name": "public-docs-sync",
            "summary": "smoke profile",
            "bindings": {
                "primary_readme_path": "README.md",
                "publish_config_path": "ExampleProduct/Properties/PublishConfiguration.xml",
                "settings_source_path": "ExampleProduct/Setting.cs",
            },
            "packet_defaults": {
                "review_docs": {
                    "claims_packet": [
                        "README.md",
                        "ExampleProduct/Properties/PublishConfiguration.xml",
                    ]
                },
                "source_path_globs": {}
            },
            "extra": {
                "public_docs_sync": {
                    "audited_public_doc_inventory": [
                        "README.md",
                        "LOG_REPORTING.md",
                        "PERF_REPORTING.md",
                        "CONTRIBUTING.md",
                        "MAINTAINING.md",
                        ".github/pull_request_template.md",
                        ".github/software-evidence-schema.md",
                        ".github/software-investigation-workflow.md",
                        ".github/workflows/release.yml",
                        "ExampleProduct/Properties/PublishConfiguration.xml",
                    ]
                }
            },
        },
    )
    (repo_root / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").write_text(
        "\n".join(
            [
                'name: "Bug Report"',
                'description: "Tell us what broke."',
                'title: "Bug: "',
                'labels: ["bug"]',
                "body:",
                "  - type: textarea",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (repo_root / "ExampleProduct" / "Setting.cs").write_text(
        "\n".join(
            [
                "public class Setting {",
                "    public bool EnableThing { get; set; } = true;",
                '    public override void SetDefaults() {',
                "        EnableThing = true;",
                "    }",
                '    GetOptionLabelLocaleID(nameof(Setting.EnableThing)), "Enable Thing"',
                '    GetOptionDescLocaleID(nameof(Setting.EnableThing)), "Turn the feature on."',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "ExampleProduct" / "Properties").mkdir(exist_ok=True)
    (repo_root / "ExampleProduct" / "Properties" / "PublishConfiguration.xml").write_text(
        "<Configuration><DisplayName Value=\"ExampleProduct\" /></Configuration>\n",
        encoding="utf-8",
    )

    run_git(repo_root, ["init"])
    run_git(repo_root, ["config", "user.email", "smoke@example.test"])
    run_git(repo_root, ["config", "user.name", "Smoke Test"])
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "Initial smoke fixture"])


def build_plan(context: dict, lint: dict) -> dict:
    actions = [
        {
            "type": "relative_link_fix",
            "summary": "Fix the README guide link.",
            "path": "README.md",
            "details": {
                "target": "./missing.md",
                "replacement_target": "./docs/guide.md",
            },
        },
        {
            "type": "public_doc_reference_sync",
            "summary": "Update CONTRIBUTING to point at the current README.",
            "path": "CONTRIBUTING.md",
            "details": {
                "match_text": "README.old.md",
                "replacement_text": "README.md",
            },
        },
        {
            "type": "issue_template_metadata_sync",
            "summary": "Sync bug-report labels.",
            "path": ".github/ISSUE_TEMPLATE/bug_report.yml",
            "details": {
                "field": "labels",
                "value": ["bug", "player-report"],
            },
        },
    ]
    active_packets = [
        name
        for name, packet in (context.get("packet_candidates") or {}).items()
        if isinstance(packet, dict) and packet.get("active")
    ]
    return {
        "context_id": context["context_id"],
        "context_fingerprint": context["context_fingerprint"],
        "overall_confidence": "high",
        "doc_update_status": "completed",
        "allow_marker_update": True,
        "actions": actions,
        "stop_reasons": [],
        "selected_packets": active_packets,
        "remaining_manual_reviews": [],
    }


def main() -> int:
    temp_root = Path.cwd() / ".codex" / "tmp" / "packet-workflow" / "public-docs-sync"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root, prefix="smoke-") as tmp_dir:
        root = Path(tmp_dir)
        repo_root = root / "repo"
        repo_root.mkdir()
        create_repo(repo_root)

        context_path = root / "context.json"
        lint_path = root / "lint.json"
        plan_path = root / "plan.json"
        validation_path = root / "validation.json"
        apply_result_path = root / "apply-result.json"
        build_result_path = root / "build-result.json"
        eval_log_path = root / "eval-log.json"
        packet_dir = root / "packets"
        state_file = root / "state.json"

        run_python(
            [
                str(SCRIPT_DIR / "collect_public_docs_sync_context.py"),
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
                "--full",
                "--state-file",
                str(state_file),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "lint_public_docs_sync.py"),
                "--context",
                str(context_path),
                "--output",
                str(lint_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "build_public_docs_sync_packets.py"),
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

        context = load_json(context_path)
        lint = load_json(lint_path)
        plan = build_plan(context, lint)
        write_json(plan_path, plan)

        run_python(
            [
                str(SCRIPT_DIR / "validate_public_docs_sync.py"),
                "--context",
                str(context_path),
                "--plan",
                str(plan_path),
                "--output",
                str(validation_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "apply_public_docs_sync.py"),
                "--validation",
                str(validation_path),
                "--dry-run",
                "--state-file",
                str(state_file),
                "--result-output",
                str(apply_result_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
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
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "build",
                "--result",
                str(build_result_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "validate",
                "--result",
                str(validation_path),
            ]
        )
        run_python(
            [
                str(SCRIPT_DIR / "write_evaluation_log.py"),
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "apply",
                "--result",
                str(apply_result_path),
            ]
        )

        orchestrator = load_json(packet_dir / "orchestrator.json")
        packet_metrics = load_json(packet_dir / "packet_metrics.json")
        apply_result = load_json(apply_result_path)
        eval_log = load_json(eval_log_path)

        assert orchestrator["orchestrator_profile"] == "standard"
        assert "packet_size_bytes" not in orchestrator
        assert packet_metrics["estimated_packet_tokens"] < packet_metrics["estimated_local_only_tokens"]
        assert packet_metrics["estimated_delegation_savings"] > 0
        assert apply_result["dry_run"] is True
        assert apply_result["marker_written"] is False
        assert eval_log["skill_specific"]["data"]["packet_count"] == packet_metrics["packet_count"]
        assert not state_file.exists()

        print(
            json.dumps(
                {
                    "smoke": "passed",
                    "packet_count": packet_metrics["packet_count"],
                    "estimated_local_only_tokens": packet_metrics["estimated_local_only_tokens"],
                    "estimated_packet_tokens": packet_metrics["estimated_packet_tokens"],
                    "estimated_delegation_savings": packet_metrics["estimated_delegation_savings"],
                    "raw_reread_count": 0,
                    "common_path_sufficient": True,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


