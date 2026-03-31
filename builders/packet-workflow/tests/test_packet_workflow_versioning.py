from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_skill_versions as check_versions
import packet_workflow_versioning as versioning
import stamp_skill_versions as stamp_versions


def builder_version() -> dict[str, object]:
    return dict(versioning.load_builder_versioning())


def profile_version_block(
    *,
    semver: str | None = None,
    compatibility_epoch: int | None = None,
    repo_profile_schema_version: int | None = None,
) -> dict[str, object]:
    current = builder_version()
    return {
        "builder_family": current["builder_family"],
        "builder_semver": semver or str(current["builder_semver"]),
        "compatibility_epoch": (
            int(current["compatibility_epoch"])
            if compatibility_epoch is None
            else compatibility_epoch
        ),
        "repo_profile_schema_version": (
            int(current["repo_profile_schema_version"])
            if repo_profile_schema_version is None
            else repo_profile_schema_version
        ),
    }


def skill_version_block(
    *,
    semver: str | None = None,
    compatibility_epoch: int | None = None,
    builder_spec_schema_version: int | None = None,
    repo_profile_schema_version: int | None = None,
) -> dict[str, object]:
    current = builder_version()
    return {
        "builder_family": current["builder_family"],
        "builder_semver": semver or str(current["builder_semver"]),
        "compatibility_epoch": (
            int(current["compatibility_epoch"])
            if compatibility_epoch is None
            else compatibility_epoch
        ),
        "builder_spec_schema_version": (
            int(current["builder_spec_schema_version"])
            if builder_spec_schema_version is None
            else builder_spec_schema_version
        ),
        "repo_profile_schema_version": (
            int(current["repo_profile_schema_version"])
            if repo_profile_schema_version is None
            else repo_profile_schema_version
        ),
    }


def write_skill_fixture(
    root: Path,
    name: str,
    *,
    skill_versioning: dict[str, object] | None,
    profile_versioning: dict[str, object] | None,
) -> Path:
    skill_dir = root / name
    (skill_dir / "profiles" / "default").mkdir(parents=True, exist_ok=True)
    spec_payload: dict[str, object] = {
        "skill_name": name,
        "description": "fixture",
        "domain_slug": "fixture",
        "workflow_family": "repo-audit",
        "archetype": "audit-only",
        "primary_goal": "fixture",
        "trigger_phrases": ["fixture"],
    }
    if skill_versioning is not None:
        spec_payload["builder_versioning"] = dict(skill_versioning)
    (skill_dir / "builder-spec.json").write_text(
        json.dumps(spec_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    profile_payload: dict[str, object] = {
        "name": "default",
        "summary": "fixture",
        "repo_match": {"root_markers": [], "remote_patterns": []},
        "bindings": {
            "primary_readme_path": "README.md",
            "settings_source_path": None,
            "publish_config_path": None,
        },
        "packet_defaults": {"review_docs": {}, "source_path_globs": {}},
        "lint_rules": {
            "require_readme_settings_table": False,
            "missing_review_docs_are_errors": False,
        },
        "notes": [],
        "profile_path": "profiles/default/profile.json",
    }
    if profile_versioning is not None:
        profile_payload["metadata"] = {"versioning": dict(profile_versioning)}
    (skill_dir / "profiles" / "default" / "profile.json").write_text(
        json.dumps(profile_payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return skill_dir


class PacketWorkflowVersioningTests(unittest.TestCase):
    def test_cli_defaults_use_canonical_retained_skills_root(self) -> None:
        expected = str(versioning.canonical_retained_skills_root())
        with mock.patch.object(sys, "argv", ["check_skill_versions.py"]):
            self.assertEqual(check_versions.parse_args().skills_root, expected)
        with mock.patch.object(sys, "argv", ["stamp_skill_versions.py"]):
            self.assertEqual(stamp_versions.parse_args().skills_root, expected)

    def test_evaluate_skill_dir_reports_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "current-skill",
                skill_versioning=skill_version_block(),
                profile_versioning=profile_version_block(),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_CURRENT)
            self.assertFalse(report["blocking"])

    def test_evaluate_skill_dir_reports_semver_behind_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "semver-behind-skill",
                skill_versioning=skill_version_block(semver="0.0.9"),
                profile_versioning=profile_version_block(semver="0.0.9"),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_SEMVER_BEHIND_COMPATIBLE)
            self.assertFalse(report["blocking"])

    def test_evaluate_skill_dir_reports_stale_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "stale-skill",
                skill_versioning=skill_version_block(compatibility_epoch=0),
                profile_versioning=profile_version_block(),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_STALE_SKILL)
            self.assertTrue(report["blocking"])

    def test_evaluate_skill_dir_reports_stale_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "stale-profile",
                skill_versioning=skill_version_block(),
                profile_versioning=profile_version_block(repo_profile_schema_version=0),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_STALE_PROFILE)
            self.assertTrue(report["blocking"])

    def test_evaluate_skill_dir_reports_missing_skill_versioning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "missing-skill-versioning",
                skill_versioning=None,
                profile_versioning=profile_version_block(),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_MISSING_SKILL_VERSIONING)
            self.assertTrue(report["blocking"])

    def test_evaluate_skill_dir_reports_missing_profile_versioning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "missing-profile-versioning",
                skill_versioning=skill_version_block(),
                profile_versioning=None,
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_MISSING_PROFILE_VERSIONING)
            self.assertTrue(report["blocking"])

    def test_evaluate_skill_dir_reports_ahead_of_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = write_skill_fixture(
                Path(tmp),
                "ahead-skill",
                skill_versioning=skill_version_block(semver="9.9.9"),
                profile_versioning=profile_version_block(),
            )
            report = versioning.evaluate_skill_dir(skill_dir)
            self.assertEqual(report["status"], versioning.STATUS_AHEAD_OF_BUILDER)
            self.assertTrue(report["blocking"])

    def test_check_skill_versions_builds_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill_fixture(
                root,
                "current-skill",
                skill_versioning=skill_version_block(),
                profile_versioning=profile_version_block(),
            )
            write_skill_fixture(
                root,
                "missing-profile",
                skill_versioning=skill_version_block(),
                profile_versioning=None,
            )
            report = check_versions.build_report(root)
            self.assertEqual(report["blocking_count"], 1)
            self.assertEqual(report["summary"][versioning.STATUS_CURRENT], 1)
            self.assertEqual(report["summary"][versioning.STATUS_MISSING_PROFILE_VERSIONING], 1)

    def test_stamp_skill_versions_updates_semver_only_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = write_skill_fixture(
                root,
                "semver-behind",
                skill_versioning=skill_version_block(semver="0.0.9"),
                profile_versioning=profile_version_block(semver="0.0.9"),
            )
            result = stamp_versions.stamp_skill(skill_dir, builder_version=builder_version())
            self.assertEqual(result["status_before"], versioning.STATUS_SEMVER_BEHIND_COMPATIBLE)

            spec_payload = json.loads((skill_dir / "builder-spec.json").read_text(encoding="utf-8"))
            profile_payload = json.loads(
                (skill_dir / "profiles" / "default" / "profile.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                spec_payload["builder_versioning"]["builder_semver"],
                builder_version()["builder_semver"],
            )
            self.assertEqual(
                profile_payload["metadata"]["versioning"]["builder_semver"],
                builder_version()["builder_semver"],
            )

    def test_stamp_skill_versions_rejects_schema_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = write_skill_fixture(
                root,
                "stale-skill",
                skill_versioning=skill_version_block(compatibility_epoch=0),
                profile_versioning=profile_version_block(),
            )
            with self.assertRaisesRegex(
                SystemExit, "Refusing to stamp stale-skill: compatibility status is stale-skill"
            ):
                stamp_versions.stamp_skill(skill_dir, builder_version=builder_version())


if __name__ == "__main__":
    unittest.main()
