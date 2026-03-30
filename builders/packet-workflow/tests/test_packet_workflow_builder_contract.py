from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_AGENTS_DIR = Path(__file__).resolve().parent / "fixtures" / "agents"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import init_packet_skill as builder


def sample_spec() -> dict[str, object]:
    return {
        "skill_name": "packet-explorer-smoke",
        "description": "Verify packet explorer support in generated packet workflow skills.",
        "domain_slug": "builder-tests",
        "workflow_family": "repo-audit",
        "archetype": "audit-and-apply",
        "primary_goal": "Keep packet explorer routing normalized in generated scaffolds.",
        "trigger_phrases": ["test packet workflow builder"],
        "task_packet_names": ["rules_packet", "runtime_packet"],
        "preferred_worker_families": {
            "context_findings": ["repo_mapper", "packet_explorer", "docs_verifier"],
            "candidate_producers": [
                "evidence_summarizer",
                "large_diff_auditor",
                "log_triager",
            ],
            "verifiers": ["docs_verifier"],
        },
        "packet_worker_map": {
            "runtime_packet": ["packet_explorer"],
            "rules_packet": ["docs_verifier"],
        },
        "repo_profile": {
            "name": "sample-repo",
            "summary": "Bind the generated core to one sample repository layout.",
            "bindings": {
                "primary_readme_path": "README.md",
                "settings_source_path": "src/Settings.cs",
                "publish_config_path": "src/Properties/PublishConfiguration.xml",
            },
            "packet_defaults": {
                "review_docs": {
                    "rules_packet": ["README.md", "docs/rules.md"],
                    "runtime_packet": ["docs/runtime.md"],
                },
                "source_path_globs": {
                    "rules_packet": ["docs/**/*.md"],
                    "runtime_packet": ["src/**/*.cs"],
                },
            },
            "lint_rules": {
                "require_readme_settings_table": True,
                "missing_review_docs_are_errors": True,
            },
            "notes": [
                "Replace sample packet defaults before using this scaffold in production.",
            ],
        },
    }


def run_python(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class PacketWorkflowBuilderContractTests(unittest.TestCase):
    def test_retained_skill_builder_specs_generate_core_contract_and_profile(self) -> None:
        foundry_root = builder.foundry_root_dir()
        retained_specs = [
            foundry_root / "skills" / "gh-address-review-threads" / "builder-spec.json",
            foundry_root / "skills" / "gh-fix-pr-writeup" / "builder-spec.json",
            foundry_root / "skills" / "git-split-and-commit" / "builder-spec.json",
            foundry_root / "skills" / "reword-recent-commits" / "builder-spec.json",
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            for spec_path in retained_specs:
                run_python(
                    SCRIPT_DIR / "init_packet_skill.py",
                    "--spec",
                    str(spec_path),
                    "--output-dir",
                    str(output_root),
                )
                skill_dir = output_root / spec_path.parent.name
                self.assertTrue((skill_dir / "references" / "core-contract.md").is_file())
                self.assertTrue((skill_dir / "profiles" / "default" / "profile.json").is_file())

    def test_builder_uses_root_core_assets(self) -> None:
        foundry_root = builder.foundry_root_dir()
        self.assertEqual(builder.managed_agents_dir(), foundry_root / "agents")
        self.assertEqual(
            builder.templates_dir(),
            foundry_root / "core" / "templates" / "packet-workflow",
        )
        review_mode_defaults = json.loads(
            (
                foundry_root
                / "core"
                / "defaults"
                / "packet-workflow"
                / "review-modes.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            builder.DEFAULT_REVIEW_MODE_OVERRIDES,
            review_mode_defaults["default_override_signals"],
        )

    def test_skill_subtree_stays_thin(self) -> None:
        skill_dir = builder.foundry_root_dir() / "skills" / "packet-workflow-skill-builder"
        files = sorted(
            str(path.relative_to(skill_dir)).replace("\\", "/")
            for path in skill_dir.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, ["SKILL.md", "agents/openai.yaml"])

    def test_managed_agent_registry_contains_packet_explorer(self) -> None:
        self.assertIn("packet_explorer", builder.KNOWN_WORKER_AGENT_TYPES)
        resolved = builder.validate_managed_agent_registry(FIXTURE_AGENTS_DIR)
        self.assertEqual(resolved, FIXTURE_AGENTS_DIR.resolve())

    def test_managed_agents_dir_resolution_prefers_override_then_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            override_dir = tmp_root / "override-agents"
            env_dir = tmp_root / "env-agents"
            codex_home = tmp_root / "codex-home"
            standard_dir = tmp_root / "standard-agents"
            override_dir.mkdir()
            env_dir.mkdir()
            (codex_home / "agents").mkdir(parents=True)
            standard_dir.mkdir()

            with (
                mock.patch.object(builder, "managed_agents_dir", return_value=standard_dir),
                mock.patch.object(
                    builder,
                    "managed_agents_fixture_dir",
                    return_value=FIXTURE_AGENTS_DIR,
                ),
            ):
                resolved = builder.resolve_managed_agents_dir(
                    override_dir,
                    env={
                        builder.MANAGED_AGENTS_DIR_ENV_VAR: str(env_dir),
                        builder.CODEX_HOME_ENV_VAR: str(codex_home),
                    },
                )
                self.assertEqual(resolved, override_dir.resolve())

                resolved = builder.resolve_managed_agents_dir(
                    env={
                        builder.MANAGED_AGENTS_DIR_ENV_VAR: str(env_dir),
                        builder.CODEX_HOME_ENV_VAR: str(codex_home),
                    }
                )
                self.assertEqual(resolved, env_dir.resolve())

                resolved = builder.resolve_managed_agents_dir(
                    env={builder.CODEX_HOME_ENV_VAR: str(codex_home)}
                )
                self.assertEqual(resolved, (codex_home / "agents").resolve())

    def test_managed_agents_dir_resolution_falls_back_to_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_standard = Path(tmp) / "missing-standard-agents"
            with (
                mock.patch.object(
                    builder,
                    "managed_agents_dir",
                    return_value=missing_standard,
                ),
                mock.patch.object(
                    builder,
                    "managed_agents_fixture_dir",
                    return_value=FIXTURE_AGENTS_DIR,
                ),
            ):
                resolved = builder.resolve_managed_agents_dir(env={})
                self.assertEqual(resolved, FIXTURE_AGENTS_DIR.resolve())
                validated = builder.validate_managed_agent_registry(env={})
                self.assertEqual(validated, FIXTURE_AGENTS_DIR.resolve())

    def test_derive_spec_normalizes_packet_explorer_routing(self) -> None:
        spec = builder.derive_spec(sample_spec())

        self.assertEqual(spec["orchestrator_profile"], "standard")
        self.assertTrue(spec["needs_validate"])
        self.assertEqual(
            spec["preferred_worker_families"]["context_findings"],
            ["repo_mapper", "packet_explorer", "docs_verifier"],
        )
        self.assertEqual(
            spec["packet_worker_map"],
            {
                "rules_packet": ["docs_verifier"],
                "runtime_packet": ["packet_explorer"],
            },
        )
        self.assertEqual(
            spec["worker_selection_guidance"]["routing_authority"],
            "packet_worker_map",
        )
        self.assertEqual(
            builder.surfaced_optional_worker_list_for_docs(spec),
            ["repo_mapper"],
        )
        self.assertEqual(spec["repo_profile"]["name"], "sample-repo")
        self.assertEqual(
            spec["repo_profile"]["profile_path"],
            "profiles/sample-repo/profile.json",
        )
        self.assertEqual(
            spec["repo_profile"]["bindings"]["settings_source_path"],
            "src/Settings.cs",
        )
        self.assertTrue(
            spec["repo_profile"]["lint_rules"]["missing_review_docs_are_errors"]
        )

    def test_invalid_orchestrator_profile_is_rejected(self) -> None:
        bad_spec = sample_spec()
        bad_spec["orchestrator_profile"] = "everything"
        with self.assertRaisesRegex(ValueError, "orchestrator_profile must be one of"):
            builder.derive_spec(bad_spec)

    def test_repo_profile_rejects_unknown_packet_defaults(self) -> None:
        bad_spec = sample_spec()
        bad_spec["repo_profile"] = {
            "packet_defaults": {
                "review_docs": {
                    "unknown-packet": ["README.md"],
                }
            }
        }
        with self.assertRaisesRegex(
            ValueError, "repo_profile.packet_defaults.review_docs contains unknown packet name"
        ):
            builder.derive_spec(bad_spec)

    def test_needs_apply_requires_needs_validate(self) -> None:
        bad_spec = sample_spec()
        bad_spec["needs_validate"] = False
        with self.assertRaisesRegex(
            ValueError, "needs_apply=true requires needs_validate=true"
        ):
            builder.derive_spec(bad_spec)

    def test_worker_instruction_and_generated_docs_surface_packet_explorer(self) -> None:
        spec = builder.derive_spec(sample_spec())
        worker_instruction = builder.worker_instruction_map(spec)["packet_explorer"]

        self.assertIn("Read global_packet.json first", worker_instruction)
        self.assertIn("exactly one focused packet or one batch packet", worker_instruction)

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            builder.generate_files(skill_dir, spec)

            skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            core_contract = (skill_dir / "references" / "core-contract.md").read_text(
                encoding="utf-8"
            )
            agents_yaml = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            profile_json = json.loads(
                (skill_dir / "profiles" / "sample-repo" / "profile.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertIn("packet_explorer", skill_md)
            self.assertIn("runtime_packet", skill_md)
            self.assertIn("Orchestrator profile: `standard`.", skill_md)
            self.assertIn("profiles/sample-repo/profile.json", skill_md)
            self.assertIn("references/core-contract.md", skill_md)
            self.assertIn("data-only", skill_md)
            self.assertIn("profiles/sample-repo/profile.json", core_contract)
            self.assertIn("data-only", core_contract)
            self.assertIn('display_name: "Packet Explorer Smoke"', agents_yaml)
            self.assertEqual(profile_json["name"], "sample-repo")
            self.assertEqual(
                profile_json["bindings"]["publish_config_path"],
                "src/Properties/PublishConfiguration.xml",
            )

    def test_standard_scaffold_uses_validation_only_apply_contract(self) -> None:
        spec = builder.derive_spec(sample_spec())

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            scripts_dir = skill_dir / "scripts"
            for script in scripts_dir.glob("*.py"):
                py_compile.compile(str(script), doraise=True)

            apply_script = (scripts_dir / "apply_builder_tests.py").read_text(
                encoding="utf-8"
            )
            self.assertIn("--validation", apply_script)
            self.assertNotIn("--plan", apply_script)
            self.assertNotIn("--context", apply_script)

            context_path = Path(tmp) / "context.json"
            packets_dir = Path(tmp) / "packets"
            build_result_path = Path(tmp) / "build-result.json"
            plan_path = Path(tmp) / "plan.json"
            validation_path = Path(tmp) / "validation.json"
            apply_result_path = Path(tmp) / "apply-result.json"

            run_python(
                scripts_dir / "collect_builder_tests_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
            )
            context = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(context["repo_profile_name"], "sample-repo")
            self.assertEqual(
                context["repo_profile"]["bindings"]["primary_readme_path"],
                "README.md",
            )
            run_python(
                scripts_dir / "build_builder_tests_packets.py",
                "--context",
                str(context_path),
                "--output-dir",
                str(packets_dir),
                "--result-output",
                str(build_result_path),
            )

            self.assertFalse((packets_dir / "synthesis_packet.json").exists())
            self.assertFalse((packets_dir / "packet_metrics.json").exists())

            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))
            self.assertEqual(build_result["orchestrator_profile"], "standard")
            self.assertEqual(build_result["repo_profile_name"], "sample-repo")

            orchestrator = json.loads(
                (packets_dir / "orchestrator.json").read_text(encoding="utf-8")
            )
            global_packet = json.loads(
                (packets_dir / "global_packet.json").read_text(encoding="utf-8")
            )
            self.assertEqual(orchestrator["repo_profile_name"], "sample-repo")
            self.assertEqual(
                global_packet["repo_profile"]["packet_defaults"]["review_docs"][
                    "rules_packet"
                ],
                ["README.md", "docs/rules.md"],
            )

            plan_path.write_text(
                json.dumps(
                    {
                        "skill_name": spec["skill_name"],
                        "context_id": context["context_id"],
                        "selected_packets": ["rules_packet"],
                        "actions": [],
                        "stop_reasons": [],
                        "overall_confidence": "medium",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            run_python(
                scripts_dir / "validate_builder_tests.py",
                "--context",
                str(context_path),
                "--plan",
                str(plan_path),
                "--output",
                str(validation_path),
            )
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertTrue(validation["valid"])
            self.assertTrue(validation["can_apply"])
            self.assertIn("normalized_plan", validation)
            self.assertIn("normalized_plan_fingerprint", validation)
            self.assertIn("apply_gate_status", validation)

            run_python(
                scripts_dir / "apply_builder_tests.py",
                "--validation",
                str(validation_path),
                "--dry-run",
                "--result-output",
                str(apply_result_path),
            )
            apply_result = json.loads(apply_result_path.read_text(encoding="utf-8"))
            self.assertTrue(apply_result["validation_boundary_enforced"])
            self.assertTrue(apply_result["dry_run"])

    def test_packet_heavy_profile_emits_synthesis_and_metrics_sidecar(self) -> None:
        raw_spec = sample_spec()
        raw_spec["skill_name"] = "packet-heavy-smoke"
        raw_spec["orchestrator_profile"] = "packet-heavy-orchestrator"
        spec = builder.derive_spec(raw_spec)

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            scripts_dir = skill_dir / "scripts"
            for script in scripts_dir.glob("*.py"):
                py_compile.compile(str(script), doraise=True)

            context_path = Path(tmp) / "context.json"
            packets_dir = Path(tmp) / "packets"
            build_result_path = Path(tmp) / "build-result.json"
            eval_log_path = Path(tmp) / "eval-log.json"

            run_python(
                scripts_dir / "collect_builder_tests_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
            )
            run_python(
                scripts_dir / "build_builder_tests_packets.py",
                "--context",
                str(context_path),
                "--output-dir",
                str(packets_dir),
                "--result-output",
                str(build_result_path),
            )

            orchestrator = json.loads(
                (packets_dir / "orchestrator.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                orchestrator["shared_local_packet"], "synthesis_packet.json"
            )
            self.assertIn("common_path_contract", orchestrator)
            self.assertNotIn("estimated_local_only_tokens", orchestrator)
            self.assertTrue((packets_dir / "synthesis_packet.json").exists())
            self.assertTrue((packets_dir / "packet_metrics.json").exists())

            packet_metrics = json.loads(
                (packets_dir / "packet_metrics.json").read_text(encoding="utf-8")
            )
            self.assertIn("packet_count", packet_metrics)
            self.assertIn("estimated_delegation_savings", packet_metrics)

            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))
            self.assertEqual(
                build_result["shared_local_packet"], "synthesis_packet.json"
            )
            self.assertIn("packet_metrics", build_result)
            self.assertEqual(build_result["repo_profile_name"], "sample-repo")

            run_python(
                scripts_dir / "write_evaluation_log.py",
                "init",
                "--context",
                str(context_path),
                "--orchestrator",
                str(packets_dir / "orchestrator.json"),
                "--output",
                str(eval_log_path),
            )
            run_python(
                scripts_dir / "write_evaluation_log.py",
                "phase",
                "--log",
                str(eval_log_path),
                "--phase",
                "build",
                "--result",
                str(build_result_path),
            )
            eval_log = json.loads(eval_log_path.read_text(encoding="utf-8"))
            self.assertIn(
                "packet_metrics",
                eval_log["skill_specific"]["data"],
            )
            self.assertEqual(eval_log["measurement"]["token_source"], "estimated")


if __name__ == "__main__":
    unittest.main()
