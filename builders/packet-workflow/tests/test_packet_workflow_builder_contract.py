from __future__ import annotations

import importlib.util
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


def current_builder_versioning() -> dict[str, object]:
    return dict(builder.CURRENT_BUILDER_VERSIONING)


def sample_spec() -> dict[str, object]:
    return {
        "builder_versioning": current_builder_versioning(),
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
            "extra": {
                "release_copy": {
                    "maintaining_path": "MAINTAINING.md",
                    "release_workflow_path": ".github/workflows/release.yml",
                }
            },
            "notes": [
                "Replace sample packet defaults before using this scaffold in production.",
            ],
        },
    }


def weekly_update_like_spec() -> dict[str, object]:
    return {
        "builder_versioning": current_builder_versioning(),
        "skill_name": "weekly-update-like-smoke",
        "description": (
            "Verify weekly-update-like retained hierarchical packet workflow support."
        ),
        "domain_slug": "weekly_update_like",
        "workflow_family": "repo-audit",
        "archetype": "plan-validate-apply",
        "primary_goal": (
            "prepare a validated weekly operational summary from decision-ready packets"
        ),
        "trigger_phrases": ["build weekly update"],
        "task_packet_names": [
            "mapping_packet",
            "changes_packet",
            "incidents_packet",
            "risks_packet",
        ],
        "orchestrator_profile": "standard",
        "decision_ready_packets": True,
        "worker_return_contract": "classification-oriented",
        "worker_output_shape": "hierarchical",
        "candidate_field_bundles": [
            {
                "name": "identity",
                "description": "Stable candidate identity and source information.",
                "required": True,
                "fields": ["candidate_id", "source_type", "source_id", "title"],
            },
            {
                "name": "proposal",
                "description": "Proposal-grade summary and classification rationale.",
                "required": True,
                "fields": [
                    "summary",
                    "proposed_classification",
                    "classification_rationale",
                ],
            },
            {
                "name": "evidence",
                "description": "Decision-ready citations and reread control.",
                "required": True,
                "fields": ["source_refs", "confidence", "raw_reread_reason"],
            },
        ],
        "worker_footer_fields": [
            "packet_ids",
            "candidate_ids",
            "primary_outcome",
            "overall_confidence",
            "coverage_gaps",
            "overall_risk",
        ],
        "reread_reason_values": [
            "conflicting_signals",
            "insufficient_excerpt_quality",
        ],
        "packet_worker_map": {
            "mapping_packet": ["repo_mapper"],
            "changes_packet": ["large_diff_auditor"],
            "incidents_packet": ["log_triager"],
            "risks_packet": ["evidence_summarizer"],
        },
        "domain_overlay": {
            "proposal_enum_values": [
                "actual_incident",
                "blocker_or_risk",
                "artifact_only",
                "ignore",
            ],
            "reference_only_candidate_values": ["artifact_only"],
            "output_inclusion_rules": {
                "standalone": ["actual_incident", "blocker_or_risk"],
                "reference_only": ["artifact_only"],
                "excluded": ["ignore"],
            },
        },
        "repo_profile": {
            "name": "default",
            "summary": (
                "Default reusable profile scaffold for weekly-update workflows. "
                "Replace review docs, path hints, and repo conventions in "
                "project-local profiles when vendored."
            ),
            "repo_match": {
                "root_markers": [".git", "README.md"],
                "remote_patterns": [],
            },
            "bindings": {
                "primary_readme_path": "README.md",
                "settings_source_path": None,
                "publish_config_path": None,
            },
            "packet_defaults": {
                "review_docs": {
                    "mapping_packet": ["README.md", "CONTRIBUTING.md"],
                    "changes_packet": ["README.md", "CONTRIBUTING.md"],
                    "incidents_packet": ["README.md", "CONTRIBUTING.md"],
                    "risks_packet": ["README.md", "CONTRIBUTING.md"],
                },
                "source_path_globs": {
                    "mapping_packet": ["**/*"],
                    "changes_packet": ["**/*"],
                    "incidents_packet": ["**/*"],
                    "risks_packet": ["**/*"],
                },
            },
            "lint_rules": {
                "require_readme_settings_table": False,
                "missing_review_docs_are_errors": False,
            },
            "extra": {
                "weekly_update": {
                    "state": {"namespace": "weekly-update"},
                    "review_markers": {
                        "acknowledged": ["phase=ack"],
                        "resolved": ["phase=complete"],
                    },
                    "release_issue": {
                        "title_regex": r"^\[Release\]\s*(?P<tag>v[0-9A-Za-z._-]+)",
                    },
                    "priority_markers": {
                        "regex": r"\[(?:P[0-3]|medium|high|low)\]",
                    },
                }
            },
            "notes": [
                "Keep repo-specific weekly-update conventions in project-local "
                "profile data when vendored.",
            ],
        },
    }


def run_python(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def load_module_from_path(module_name: str, script_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(script_path.parent))
        except ValueError:
            pass
    return module


EXECUTION_ROOTS_HEADER = "## Execution Roots"
PYTHON_BIN_SKILL_PREFIX = "<python-bin> -B <skill-dir>/scripts/"
FORBIDDEN_OPERATOR_DOC_PATTERNS = ("python scripts/", "py -3")


def assert_skill_md_execution_contract(
    testcase: unittest.TestCase, skill_md: str, *, source: Path | str
) -> None:
    label = str(source)
    testcase.assertIn(EXECUTION_ROOTS_HEADER, skill_md, label)
    testcase.assertIn(PYTHON_BIN_SKILL_PREFIX, skill_md, label)
    for pattern in FORBIDDEN_OPERATOR_DOC_PATTERNS:
        testcase.assertNotIn(pattern, skill_md, label)


def operator_doc_scan_targets(foundry_root: Path) -> list[Path]:
    scan_roots = [
        foundry_root / "builders",
        foundry_root / "core",
    ]
    allowed_suffixes = {".md", ".py", ".tmpl"}
    excluded_parts = {"__pycache__", ".git", "tests"}
    targets: list[Path] = []
    for root in scan_roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in allowed_suffixes:
                continue
            if any(part in excluded_parts for part in path.parts):
                continue
            targets.append(path)
    return targets


class PacketWorkflowBuilderContractTests(unittest.TestCase):
    def test_retained_skill_builder_specs_generate_core_contract_and_profile(self) -> None:
        foundry_root = builder.foundry_root_dir()
        retained_specs = [
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "draft-release-copy"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "gh-create-pr"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "gh-address-review-threads"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "gh-fix-pr-writeup"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "git-split-and-commit"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "public-docs-sync"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "reword-recent-commits"
            / "builder-spec.json",
            foundry_root
            / "builders"
            / "packet-workflow"
            / "retained-skills"
            / "weekly-update"
            / "builder-spec.json",
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
                    "--managed-agents-dir",
                    str(FIXTURE_AGENTS_DIR),
                )
                retained_dir = (
                    output_root
                    / "builders"
                    / "packet-workflow"
                    / "retained-skills"
                    / spec_path.parent.name
                )
                wrapper_dir = output_root / ".agents" / "skills" / spec_path.parent.name
                self.assertTrue((retained_dir / "references" / "core-contract.md").is_file())
                self.assertTrue(
                    (retained_dir / "profiles" / "default" / "profile.json").is_file()
                )
                assert_skill_md_execution_contract(
                    self,
                    (retained_dir / "SKILL.md").read_text(encoding="utf-8"),
                    source=retained_dir / "SKILL.md",
                )
                wrapper_files = sorted(
                    str(path.relative_to(wrapper_dir)).replace("\\", "/")
                    for path in wrapper_dir.rglob("*")
                    if path.is_file()
                )
                self.assertEqual(wrapper_files, ["SKILL.md", "agents/openai.yaml"])

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
        self.assertEqual(
            builder.CURRENT_BUILDER_VERSIONING,
            json.loads(
                (foundry_root / "builders" / "packet-workflow" / "version.json").read_text(
                    encoding="utf-8"
                )
            ),
        )

    def test_skill_subtree_stays_thin(self) -> None:
        skills_root = builder.foundry_root_dir() / ".agents" / "skills"
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            with self.subTest(skill=skill_dir.name):
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
        self.assertEqual(spec["builder_versioning"], current_builder_versioning())
        self.assertEqual(
            spec["repo_profile"]["metadata"]["versioning"],
            {
                "builder_family": current_builder_versioning()["builder_family"],
                "builder_semver": current_builder_versioning()["builder_semver"],
                "compatibility_epoch": current_builder_versioning()["compatibility_epoch"],
                "repo_profile_schema_version": current_builder_versioning()[
                    "repo_profile_schema_version"
                ],
            },
        )
        self.assertEqual(
            spec["repo_profile"]["bindings"]["settings_source_path"],
            "src/Settings.cs",
        )
        self.assertEqual(
            spec["repo_profile"]["extra"]["release_copy"]["maintaining_path"],
            "MAINTAINING.md",
        )
        self.assertTrue(
            spec["repo_profile"]["lint_rules"]["missing_review_docs_are_errors"]
        )

    def test_invalid_orchestrator_profile_is_rejected(self) -> None:
        bad_spec = sample_spec()
        bad_spec["orchestrator_profile"] = "everything"
        with self.assertRaisesRegex(ValueError, "orchestrator_profile must be one of"):
            builder.derive_spec(bad_spec)

    def test_missing_builder_versioning_is_rejected(self) -> None:
        bad_spec = sample_spec()
        bad_spec.pop("builder_versioning")
        with self.assertRaisesRegex(
            ValueError, "builder_versioning is required and must be a valid object"
        ):
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

    def test_weekly_update_like_retained_shape_generates_hierarchical_packets(self) -> None:
        spec = builder.derive_spec(weekly_update_like_spec())

        self.assertEqual(spec["archetype"], "plan-validate-apply")
        self.assertTrue(spec["decision_ready_packets"])
        self.assertEqual(spec["worker_return_contract"], "classification-oriented")
        self.assertEqual(spec["worker_output_shape"], "hierarchical")
        self.assertEqual(
            spec["repo_profile"]["extra"]["weekly_update"]["state"]["namespace"],
            "weekly-update",
        )

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

            run_python(
                scripts_dir / "collect_weekly_update_like_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(context_path),
            )
            run_python(
                scripts_dir / "build_weekly_update_like_packets.py",
                "--context",
                str(context_path),
                "--output-dir",
                str(packets_dir),
                "--result-output",
                str(build_result_path),
            )

            context = json.loads(context_path.read_text(encoding="utf-8"))
            orchestrator = json.loads(
                (packets_dir / "orchestrator.json").read_text(encoding="utf-8")
            )
            global_packet = json.loads(
                (packets_dir / "global_packet.json").read_text(encoding="utf-8")
            )

            self.assertEqual(context["repo_profile_name"], "default")
            self.assertEqual(context["builder_compatibility"]["status"], "current")
            self.assertEqual(orchestrator["repo_profile_name"], "default")
            self.assertTrue(orchestrator["decision_ready_packets"])
            self.assertEqual(
                orchestrator["worker_return_contract"], "classification-oriented"
            )
            self.assertEqual(orchestrator["worker_output_shape"], "hierarchical")
            self.assertEqual(
                global_packet["domain_overlay"]["proposal_enum_values"],
                ["actual_incident", "blocker_or_risk", "artifact_only", "ignore"],
            )
            self.assertEqual(
                global_packet["repo_profile"]["extra"]["weekly_update"]["state"][
                    "namespace"
                ],
                "weekly-update",
            )

    def test_candidate_field_bundles_require_classification_oriented(self) -> None:
        bad_spec = sample_spec()
        bad_spec["candidate_field_bundles"] = [
            {
                "name": "candidate",
                "description": "Candidate data.",
                "required": True,
                "fields": ["summary"],
            }
        ]
        with self.assertRaisesRegex(
            ValueError,
            "candidate_field_bundles requires worker_return_contract=classification-oriented",
        ):
            builder.derive_spec(bad_spec)

    def test_classification_oriented_requires_decision_ready_packets(self) -> None:
        bad_spec = sample_spec()
        bad_spec["worker_return_contract"] = "classification-oriented"
        with self.assertRaisesRegex(
            ValueError,
            "worker_return_contract=classification-oriented requires decision_ready_packets=true",
        ):
            builder.derive_spec(bad_spec)

    def test_worker_footer_fields_require_decision_ready_packets(self) -> None:
        bad_spec = sample_spec()
        bad_spec["worker_footer_fields"] = ["packet_ids", "primary_outcome"]
        with self.assertRaisesRegex(
            ValueError,
            "worker_footer_fields requires decision_ready_packets=true",
        ):
            builder.derive_spec(bad_spec)

    def test_worker_footer_fields_require_hierarchical_output(self) -> None:
        bad_spec = weekly_update_like_spec()
        bad_spec["worker_output_shape"] = "flat"
        with self.assertRaisesRegex(
            ValueError,
            "worker_footer_fields requires worker_output_shape=hierarchical",
        ):
            builder.derive_spec(bad_spec)

    def test_domain_overlay_requires_classification_oriented(self) -> None:
        bad_spec = sample_spec()
        bad_spec["domain_overlay"] = {
            "proposal_enum_values": ["accept", "reject"],
            "output_inclusion_rules": {"standalone": ["accept"], "excluded": ["reject"]},
        }
        with self.assertRaisesRegex(
            ValueError,
            "domain_overlay requires worker_return_contract=classification-oriented",
        ):
            builder.derive_spec(bad_spec)

    def test_hierarchical_output_requires_usable_candidate_bundles(self) -> None:
        bad_spec = weekly_update_like_spec()
        bad_spec["candidate_field_bundles"] = []
        with self.assertRaisesRegex(
            ValueError,
            "worker_output_shape=hierarchical requires candidate_field_bundles or required_candidate_fields",
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
            self.assertIn(".codex/project/profiles/packet-explorer-smoke/profile.json", skill_md)
            self.assertIn("references/core-contract.md", skill_md)
            self.assertIn("data-only", skill_md)
            self.assertIn(
                ".codex/tmp/packet-workflow/packet-explorer-smoke/<run-id>/",
                skill_md,
            )
            self.assertIn(
                "~/.codex/tmp/evaluation_logs/packet-explorer-smoke/<run-id>.json",
                skill_md,
            )
            self.assertIn(".codex/tmp/", skill_md)
            self.assertIn("profiles/sample-repo/profile.json", core_contract)
            self.assertIn(".codex/project/profiles/packet-explorer-smoke/profile.json", core_contract)
            self.assertIn("data-only", core_contract)
            self.assertIn('display_name: "Packet Explorer Smoke"', agents_yaml)
            self.assertEqual(profile_json["name"], "sample-repo")
            self.assertEqual(
                profile_json["metadata"]["versioning"]["builder_semver"],
                current_builder_versioning()["builder_semver"],
            )
            self.assertEqual(
                profile_json["bindings"]["publish_config_path"],
                "src/Properties/PublishConfiguration.xml",
            )
            assert_skill_md_execution_contract(self, skill_md, source=skill_dir / "SKILL.md")

    def test_retained_skill_docs_use_python_bin_execution_contract(self) -> None:
        retained_root = (
            builder.foundry_root_dir()
            / "builders"
            / "packet-workflow"
            / "retained-skills"
        )
        for skill_md_path in sorted(retained_root.glob("*/SKILL.md")):
            with self.subTest(skill=skill_md_path.parent.name):
                assert_skill_md_execution_contract(
                    self,
                    skill_md_path.read_text(encoding="utf-8"),
                    source=skill_md_path,
                )

    def test_repo_operator_docs_do_not_prescribe_python_shims(self) -> None:
        foundry_root = builder.foundry_root_dir()
        violations: list[str] = []
        for path in operator_doc_scan_targets(foundry_root):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_OPERATOR_DOC_PATTERNS:
                if pattern in text:
                    violations.append(f"{path}: {pattern}")
        self.assertEqual(violations, [])

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
            self.assertEqual(context["builder_compatibility"]["status"], "current")
            self.assertEqual(
                context["builder_compatibility"]["current_builder_semver"],
                current_builder_versioning()["builder_semver"],
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

    def test_generated_collector_warns_but_returns_context_for_stale_profile(self) -> None:
        spec = builder.derive_spec(sample_spec())

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            profile_path = skill_dir / "profiles" / "sample-repo" / "profile.json"
            profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_payload["metadata"]["versioning"]["repo_profile_schema_version"] = 0
            profile_path.write_text(
                json.dumps(profile_payload, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

            result = run_python(
                skill_dir / "scripts" / "collect_builder_tests_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(Path(tmp) / "context.json"),
                "--profile",
                str(profile_path),
            )
            context = json.loads((Path(tmp) / "context.json").read_text(encoding="utf-8"))
            self.assertEqual(context["builder_compatibility"]["status"], "stale-profile")
            self.assertIn("status=stale-profile", result.stderr)

    def test_generated_collector_warns_but_returns_context_for_invalid_profile_semver(self) -> None:
        spec = builder.derive_spec(sample_spec())

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            profile_path = skill_dir / "profiles" / "sample-repo" / "profile.json"
            profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_payload["metadata"]["versioning"]["builder_semver"] = "not-semver"
            profile_path.write_text(
                json.dumps(profile_payload, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

            result = run_python(
                skill_dir / "scripts" / "collect_builder_tests_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(Path(tmp) / "context.json"),
                "--profile",
                str(profile_path),
            )
            context = json.loads((Path(tmp) / "context.json").read_text(encoding="utf-8"))
            self.assertEqual(context["builder_compatibility"]["status"], "missing-profile-versioning")
            self.assertIn("status=missing-profile-versioning", result.stderr)

    def test_generated_collector_warns_but_returns_context_for_non_string_profile_semver(
        self,
    ) -> None:
        spec = builder.derive_spec(sample_spec())

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            profile_path = skill_dir / "profiles" / "sample-repo" / "profile.json"
            profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_payload["metadata"]["versioning"]["builder_semver"] = 1
            profile_path.write_text(
                json.dumps(profile_payload, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )

            result = run_python(
                skill_dir / "scripts" / "collect_builder_tests_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(Path(tmp) / "context.json"),
                "--profile",
                str(profile_path),
            )
            context = json.loads((Path(tmp) / "context.json").read_text(encoding="utf-8"))
            self.assertEqual(context["builder_compatibility"]["status"], "missing-profile-versioning")
            self.assertIn("status=missing-profile-versioning", result.stderr)

    def test_generated_collector_prefers_project_local_skill_profile(self) -> None:
        spec = builder.derive_spec(sample_spec())

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / str(spec["skill_name"])
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            builder.generate_files(skill_dir, spec)

            skill_profile = (
                repo_root
                / ".codex"
                / "project"
                / "profiles"
                / str(spec["skill_name"])
                / "profile.json"
            )
            default_profile = (
                repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json"
            )
            retained_profile = skill_dir / "profiles" / "sample-repo" / "profile.json"
            collector = load_module_from_path(
                "collect_builder_tests_context_dynamic",
                skill_dir / "scripts" / "collect_builder_tests_context.py",
            )

            skill_profile.parent.mkdir(parents=True, exist_ok=True)
            skill_profile.write_text("{}", encoding="utf-8")
            default_profile.parent.mkdir(parents=True, exist_ok=True)
            default_profile.write_text("{}", encoding="utf-8")

            self.assertEqual(
                collector.default_repo_profile_path(repo_root),
                skill_profile.resolve(),
            )
            self.assertEqual(
                collector.resolve_profile_path(
                    ".codex/project/profiles/default/profile.json",
                    repo_root,
                ),
                default_profile.resolve(),
            )
            self.assertEqual(
                collector.resolve_profile_path("profiles/sample-repo/profile.json", repo_root),
                retained_profile.resolve(),
            )

            skill_profile.unlink()
            self.assertEqual(
                collector.default_repo_profile_path(repo_root),
                default_profile.resolve(),
            )

            default_profile.unlink()
            self.assertEqual(
                collector.default_repo_profile_path(repo_root),
                retained_profile.resolve(),
            )

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


