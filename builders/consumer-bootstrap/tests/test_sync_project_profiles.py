from __future__ import annotations

import io
import json
import py_compile
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
PACKET_WORKFLOW_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "packet-workflow" / "scripts"
REWORD_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "builders"
    / "packet-workflow"
    / "retained-skills"
    / "reword-recent-commits"
    / "scripts"
)
for candidate in (SCRIPT_DIR, PACKET_WORKFLOW_SCRIPT_DIR, REWORD_SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import init_consumer_codex as bootstrap
import packet_workflow_versioning as versioning
import sync_project_profiles as sync_profiles
import collect_recent_commits as reword_collect


def current_builder_version() -> dict[str, object]:
    return dict(versioning.load_builder_versioning())


def deep_merge(target: dict[str, object], updates: dict[str, object]) -> dict[str, object]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)  # type: ignore[index]
            continue
        target[key] = value
    return target


def create_repo_root(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    return repo


def create_packet_workflow_wrapper(wrapper_root: Path, skill_name: str, retained_relative: str) -> Path:
    wrapper_dir = wrapper_root / skill_name
    (wrapper_dir / "agents").mkdir(parents=True, exist_ok=True)
    (wrapper_dir / "SKILL.md").write_text(
        "\n".join(
            [
                f"---\nname: {skill_name}\ndescription: test wrapper\n---",
                "",
                f"# {skill_name}",
                "",
                f"Thin entrypoint for the foundry retained `{skill_name}` kernel.",
                "",
                f"- keep authoritative retained workflow assets in `{retained_relative}`",
                "",
                f"Use this skill by reading and following the retained kernel instructions at `{retained_relative}SKILL.md`.",
                "",
                f"- treat `{retained_relative}` as the source of truth",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (wrapper_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Test"\n',
        encoding="utf-8",
    )
    return wrapper_dir


def create_generic_wrapper(wrapper_root: Path, skill_name: str) -> Path:
    wrapper_dir = wrapper_root / skill_name
    (wrapper_dir / "agents").mkdir(parents=True, exist_ok=True)
    (wrapper_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: generic wrapper\n---\n",
        encoding="utf-8",
    )
    (wrapper_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Generic"\n',
        encoding="utf-8",
    )
    return wrapper_dir


def create_retained_skill(
    repo_root: Path,
    skill_name: str,
    *,
    skill_versioning: dict[str, object] | None = None,
    profile_versioning: dict[str, object] | None = None,
    profile_overrides: dict[str, object] | None = None,
) -> Path:
    retained_dir = repo_root / "builders" / "packet-workflow" / "retained-skills" / skill_name
    (retained_dir / "profiles" / "default").mkdir(parents=True, exist_ok=True)
    (retained_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: retained skill\n---\n",
        encoding="utf-8",
    )

    builder_version = current_builder_version()
    spec_payload: dict[str, object] = {
        "skill_name": skill_name,
        "description": "fixture",
        "domain_slug": "fixture",
        "workflow_family": "repo-audit",
        "archetype": "audit-only",
        "primary_goal": "fixture",
        "trigger_phrases": ["fixture"],
        "builder_versioning": skill_versioning or builder_version,
    }
    (retained_dir / "builder-spec.json").write_text(
        json.dumps(spec_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    profile_payload: dict[str, object] = {
        "name": "default",
        "summary": f"Retained default scaffold for {skill_name}.",
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
                "task_packet": ["README.md"],
            },
            "source_path_globs": {
                "task_packet": ["src/**"],
            },
        },
        "lint_rules": {
            "require_readme_settings_table": False,
            "missing_review_docs_are_errors": False,
        },
        "extra": {
            "sample": {
                "owner": "docs",
            }
        },
        "notes": [
            "Retained placeholder note.",
        ],
        "profile_path": "profiles/default/profile.json",
        "metadata": {
            "versioning": profile_versioning
            or {
                "builder_family": builder_version["builder_family"],
                "builder_semver": builder_version["builder_semver"],
                "compatibility_epoch": builder_version["compatibility_epoch"],
                "repo_profile_schema_version": builder_version["repo_profile_schema_version"],
            }
        },
    }
    if profile_overrides:
        deep_merge(profile_payload, profile_overrides)
    (retained_dir / "profiles" / "default" / "profile.json").write_text(
        json.dumps(profile_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return retained_dir


def create_vendor_packet_workflow_skill(repo: Path, skill_name: str) -> None:
    vendor_root = repo / ".codex" / "vendor" / "packetflow_foundry"
    create_packet_workflow_wrapper(
        vendor_root / ".agents" / "skills",
        skill_name,
        f"../../../builders/packet-workflow/retained-skills/{skill_name}/",
    )
    create_retained_skill(vendor_root, skill_name)
    (vendor_root / ".codex" / "agents").mkdir(parents=True, exist_ok=True)


def write_project_profile(
    repo: Path,
    skill_name: str,
    payload: dict[str, object],
) -> Path:
    if skill_name == "default":
        path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
    else:
        path = repo / ".codex" / "project" / "profiles" / skill_name / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def run_bootstrap_main(repo: Path) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(
            sys,
            "argv",
            [
                "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            ],
        ),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        code = bootstrap.main()
    return code, stdout.getvalue(), stderr.getvalue()


def run_sync_main(repo: Path, *extra_args: str) -> tuple[int, str, str, dict[str, object]]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    report_path = repo / sync_profiles.DEFAULT_REPORT_RELATIVE
    with (
        mock.patch.object(
            sys,
            "argv",
            [
                "sync_project_profiles.py",
                "--repo-root",
                str(repo),
                *extra_args,
            ],
        ),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        code = sync_profiles.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return code, stdout.getvalue(), stderr.getvalue(), report


class ProjectProfileSyncTests(unittest.TestCase):
    def test_script_compiles(self) -> None:
        py_compile.compile(
            str(SCRIPT_DIR / "sync_project_profiles.py"),
            doraise=True,
        )

    def test_discover_packet_workflow_wrapper_in_direct_repo_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")

            discovered = sync_profiles.discover_packet_workflow_wrappers(repo)

            self.assertEqual(list(discovered), ["demo-skill"])
            self.assertEqual(
                discovered["demo-skill"]["retained_skill_dir"],
                (
                    repo
                    / "builders"
                    / "packet-workflow"
                    / "retained-skills"
                    / "demo-skill"
                ).resolve().as_posix(),
            )

    def test_discover_packet_workflow_wrapper_in_vendored_layout_after_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_vendor_packet_workflow_skill(repo, "demo-skill")

            code, _, _ = run_bootstrap_main(repo)
            self.assertEqual(code, 0)

            discovered = sync_profiles.discover_packet_workflow_wrappers(repo)

            self.assertEqual(list(discovered), ["demo-skill"])
            self.assertEqual(
                discovered["demo-skill"]["retained_skill_dir"],
                (
                    repo
                    / ".codex"
                    / "vendor"
                    / "packetflow_foundry"
                    / "builders"
                    / "packet-workflow"
                    / "retained-skills"
                    / "demo-skill"
                ).resolve().as_posix(),
            )

    def test_discover_ignores_non_packet_workflow_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")
            create_generic_wrapper(repo / ".agents" / "skills", "generic-skill")

            discovered = sync_profiles.discover_packet_workflow_wrappers(repo)

            self.assertEqual(list(discovered), ["demo-skill"])

    def test_discover_ignores_wrapper_with_absolute_retained_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            wrapper_root = repo / ".agents" / "skills"
            create_packet_workflow_wrapper(
                wrapper_root,
                "demo-skill",
                "C:/external/builders/packet-workflow/retained-skills/demo-skill/",
            )

            discovered = sync_profiles.discover_packet_workflow_wrappers(repo)

            self.assertEqual(discovered, {})

    def test_discover_ignores_wrapper_when_retained_path_resolves_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = create_repo_root(root)
            wrapper_dir = create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            external_retained = create_retained_skill(root / "external-foundry", "demo-skill")
            real_resolve = Path.resolve

            def fake_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                if path == wrapper_dir / "../../../builders/packet-workflow/retained-skills/demo-skill/":
                    return external_retained.resolve()
                return real_resolve(path, *args, **kwargs)

            with mock.patch.object(Path, "resolve", fake_resolve):
                discovered = sync_profiles.discover_packet_workflow_wrappers(repo)

            self.assertEqual(discovered, {})

    def test_sync_creates_missing_default_and_skill_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 0)
            default_profile = json.loads(
                (repo / bootstrap.PROJECT_PROFILE_RELATIVE).read_text(encoding="utf-8")
            )
            skill_profile = json.loads(
                (
                    repo / ".codex" / "project" / "profiles" / "demo-skill" / "profile.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(default_profile["kind"], bootstrap.PROJECT_LOCAL_PROFILE_KIND)
            self.assertEqual(skill_profile["kind"], bootstrap.PROJECT_LOCAL_PROFILE_KIND)
            self.assertEqual(skill_profile["name"], "demo-skill")
            self.assertEqual(
                skill_profile["profile_path"],
                ".codex/project/profiles/demo-skill/profile.json",
            )
            self.assertIn("consumer repository", skill_profile["summary"])
            self.assertEqual(report["summary"]["created"], 2)

    def test_sync_safe_merges_missing_keys_and_preserves_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")

            builder_version = current_builder_version()
            existing_payload = {
                "kind": "project-local-scaffold-profile",
                "name": "wrong-name",
                "profile_path": "wrong/path.json",
                "summary": "Existing project local profile.",
                "repo_match": {
                    "root_markers": [".git"],
                    "remote_patterns": [],
                },
                "bindings": {
                    "primary_readme_path": "docs/README.md",
                },
                "packet_defaults": {
                    "review_docs": {
                        "task_packet": ["docs/OVERVIEW.md"],
                    }
                },
                "lint_rules": {
                    "require_readme_settings_table": True,
                },
                "metadata": {
                    "versioning": {
                        "builder_family": builder_version["builder_family"],
                        "builder_semver": builder_version["builder_semver"],
                        "compatibility_epoch": builder_version["compatibility_epoch"],
                        "repo_profile_schema_version": builder_version["repo_profile_schema_version"],
                    }
                },
            }
            profile_path = write_project_profile(repo, "demo-skill", existing_payload)

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 0)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["kind"], bootstrap.PROJECT_LOCAL_PROFILE_KIND)
            self.assertEqual(profile["name"], "demo-skill")
            self.assertEqual(
                profile["profile_path"],
                ".codex/project/profiles/demo-skill/profile.json",
            )
            self.assertEqual(profile["bindings"]["primary_readme_path"], "docs/README.md")
            self.assertEqual(
                profile["packet_defaults"]["review_docs"]["task_packet"],
                ["docs/OVERVIEW.md"],
            )
            self.assertEqual(
                profile["packet_defaults"]["source_path_globs"]["task_packet"],
                ["src/**"],
            )
            self.assertEqual(profile["extra"]["sample"]["owner"], "docs")
            self.assertEqual(report["summary"]["updated"], 1)

    def test_sync_updates_semver_only_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            builder_version = current_builder_version()
            payload = {
                "kind": bootstrap.PROJECT_LOCAL_PROFILE_KIND,
                "name": "default",
                "profile_path": bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
                "summary": "Project-local default scaffold.",
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
                    "review_docs": {},
                    "source_path_globs": {},
                },
                "lint_rules": {
                    "require_readme_settings_table": False,
                    "missing_review_docs_are_errors": False,
                },
                "notes": [],
                "metadata": {
                    "versioning": {
                        "builder_family": builder_version["builder_family"],
                        "builder_semver": "0.0.9",
                        "compatibility_epoch": builder_version["compatibility_epoch"],
                        "repo_profile_schema_version": builder_version["repo_profile_schema_version"],
                    }
                },
            }
            profile_path = write_project_profile(repo, "default", payload)

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 0)
            updated = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(
                updated["metadata"]["versioning"]["builder_semver"],
                builder_version["builder_semver"],
            )
            self.assertEqual(report["profiles"][0]["action"], "updated")

    def test_sync_updates_legacy_default_profile_without_versioning_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            payload = {
                "kind": bootstrap.PROJECT_LOCAL_PROFILE_KIND,
                "name": "default",
                "profile_path": bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
                "summary": "Legacy default profile.",
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
                    "review_docs": {},
                    "source_path_globs": {},
                },
                "lint_rules": {
                    "require_readme_settings_table": False,
                    "missing_review_docs_are_errors": False,
                },
                "notes": [],
            }
            profile_path = write_project_profile(repo, "default", payload)

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 0)
            updated = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertIn("metadata", updated)
            self.assertIn("versioning", updated["metadata"])
            self.assertEqual(report["profiles"][0]["action"], "updated")
            self.assertEqual(
                report["profiles"][0]["compatibility_status"],
                versioning.STATUS_MISSING_PROFILE_VERSIONING,
            )

    def test_sync_reports_invalid_json_as_manual_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            profile_path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text("{\n", encoding="utf-8")

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(report["profiles"][0]["action"], "manual_migration_required")

    def test_sync_reports_stale_skill_profile_as_manual_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")
            builder_version = current_builder_version()
            stale_payload = {
                "kind": bootstrap.PROJECT_LOCAL_PROFILE_KIND,
                "name": "demo-skill",
                "profile_path": ".codex/project/profiles/demo-skill/profile.json",
                "summary": "Stale profile.",
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
                        "task_packet": ["README.md"],
                    },
                    "source_path_globs": {
                        "task_packet": ["src/**"],
                    },
                },
                "lint_rules": {
                    "require_readme_settings_table": False,
                    "missing_review_docs_are_errors": False,
                },
                "notes": [],
                "metadata": {
                    "versioning": {
                        "builder_family": builder_version["builder_family"],
                        "builder_semver": builder_version["builder_semver"],
                        "compatibility_epoch": builder_version["compatibility_epoch"],
                        "repo_profile_schema_version": 0,
                    }
                },
            }
            write_project_profile(repo, "demo-skill", stale_payload)

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 1)
            skill_report = next(
                item for item in report["profiles"] if item["skill_name"] == "demo-skill"
            )
            self.assertEqual(skill_report["action"], "manual_migration_required")
            self.assertEqual(skill_report["compatibility_status"], "stale-profile")

    def test_sync_blocks_stale_retained_profile_source_before_scaffolding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            builder_version = current_builder_version()
            create_retained_skill(
                repo,
                "demo-skill",
                profile_versioning={
                    "builder_family": builder_version["builder_family"],
                    "builder_semver": builder_version["builder_semver"],
                    "compatibility_epoch": builder_version["compatibility_epoch"],
                    "repo_profile_schema_version": 0,
                },
            )

            code, _, _, report = run_sync_main(repo)

            self.assertEqual(code, 1)
            skill_report = next(
                item for item in report["profiles"] if item["skill_name"] == "demo-skill"
            )
            self.assertEqual(skill_report["action"], "manual_migration_required")
            self.assertEqual(skill_report["compatibility_status"], "stale-profile")
            self.assertFalse(
                (
                    repo
                    / ".codex"
                    / "project"
                    / "profiles"
                    / "demo-skill"
                    / "profile.json"
                ).exists()
            )

    def test_sync_reports_ahead_default_profile_as_manual_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            builder_version = current_builder_version()
            ahead_payload = {
                "kind": bootstrap.PROJECT_LOCAL_PROFILE_KIND,
                "name": "default",
                "profile_path": bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
                "summary": "Ahead profile.",
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
                    "review_docs": {},
                    "source_path_globs": {},
                },
                "lint_rules": {
                    "require_readme_settings_table": False,
                    "missing_review_docs_are_errors": False,
                },
                "notes": [],
                "metadata": {
                    "versioning": {
                        "builder_family": builder_version["builder_family"],
                        "builder_semver": "9.9.9",
                        "compatibility_epoch": builder_version["compatibility_epoch"],
                        "repo_profile_schema_version": builder_version["repo_profile_schema_version"],
                    }
                },
            }
            write_project_profile(repo, "default", ahead_payload)

            code, stdout, _, report = run_sync_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(report["profiles"][0]["action"], "manual_migration_required")
            self.assertEqual(report["profiles"][0]["compatibility_status"], "ahead-of-builder")
            self.assertIn("[ERROR] Synced project-local profiles with blocking items", stdout)
            self.assertNotIn("[OK] Synced project-local profiles", stdout)

    def test_dry_run_report_matches_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")

            dry_code, _, _, dry_report = run_sync_main(repo, "--dry-run")
            self.assertEqual(dry_code, 0)
            self.assertFalse((repo / bootstrap.PROJECT_PROFILE_RELATIVE).exists())
            self.assertFalse(
                (repo / ".codex" / "project" / "profiles" / "demo-skill" / "profile.json").exists()
            )

            apply_code, _, _, apply_report = run_sync_main(repo)

            self.assertEqual(apply_code, 0)
            self.assertEqual(
                [item["action"] for item in dry_report["profiles"]],
                [item["action"] for item in apply_report["profiles"]],
            )

    def test_sync_success_prints_ok_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_packet_workflow_wrapper(
                repo / ".agents" / "skills",
                "demo-skill",
                "../../../builders/packet-workflow/retained-skills/demo-skill/",
            )
            create_retained_skill(repo, "demo-skill")

            code, stdout, _, _ = run_sync_main(repo)

            self.assertEqual(code, 0)
            self.assertIn("[OK] Synced project-local profiles", stdout)

    def test_sync_after_bootstrap_preserves_skill_profile_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_repo_root(Path(tmp))
            create_vendor_packet_workflow_skill(repo, "reword-recent-commits")

            bootstrap_code, _, _ = run_bootstrap_main(repo)
            self.assertEqual(bootstrap_code, 0)

            sync_code, _, _, _ = run_sync_main(repo)
            self.assertEqual(sync_code, 0)

            skill_profile = (
                repo
                / ".codex"
                / "project"
                / "profiles"
                / "reword-recent-commits"
                / "profile.json"
            )
            self.assertEqual(reword_collect.default_repo_profile_path(repo), skill_profile.resolve())


if __name__ == "__main__":
    unittest.main()
