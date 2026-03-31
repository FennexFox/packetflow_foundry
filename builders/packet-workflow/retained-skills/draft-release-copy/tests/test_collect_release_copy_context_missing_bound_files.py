import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_release_copy_context as collector


class CollectReleaseCopyContextMainTests(unittest.TestCase):
    def test_main_reports_missing_required_binding_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "README.md").write_text("# Repo\n", encoding="utf-8")

            stderr = io.StringIO()
            output_path = repo_root / "out" / "context.json"
            argv = [
                "collect_release_copy_context.py",
                "--repo-root",
                str(repo_root),
                "--profile",
                str(collector.retained_default_repo_profile_path()),
                "--output",
                str(output_path),
            ]

            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
                exit_code = collector.main()

            self.assertEqual(exit_code, 1)
            error_text = stderr.getvalue()
            self.assertIn("collect_release_copy_context.py:", error_text)
            self.assertIn("bindings.publish_config_path", error_text)
            self.assertIn("missing required repo profile binding", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_main_reports_missing_required_bound_file_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            profile_path = repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json"
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(
                json.dumps(
                    {
                        "bindings": {
                            "primary_readme_path": "README.md",
                            "publish_config_path": "release/PublishConfiguration.xml",
                            "settings_source_path": "src/Setting.cs",
                        },
                        "extra": {
                            "release_copy": {
                                "maintaining_path": "MAINTAINING.md",
                                "release_checklist_template_path": ".github/ISSUE_TEMPLATE/release_checklist.yml",
                                "release_workflow_path": ".github/workflows/release.yml",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (repo_root / "README.md").write_text("# Repo\n", encoding="utf-8")
            (repo_root / "MAINTAINING.md").write_text("## Release Operations\n\n- step\n", encoding="utf-8")
            checklist_path = repo_root / ".github" / "ISSUE_TEMPLATE" / "release_checklist.yml"
            checklist_path.parent.mkdir(parents=True, exist_ok=True)
            checklist_path.write_text("name: Release checklist\n", encoding="utf-8")
            workflow_path = repo_root / ".github" / "workflows" / "release.yml"
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            workflow_path.write_text("name: release\n", encoding="utf-8")
            settings_path = repo_root / "src" / "Setting.cs"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text("namespace Example {}\n", encoding="utf-8")

            stderr = io.StringIO()
            output_path = repo_root / "out" / "context.json"
            argv = [
                "collect_release_copy_context.py",
                "--repo-root",
                str(repo_root),
                "--output",
                str(output_path),
            ]

            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
                exit_code = collector.main()

            self.assertEqual(exit_code, 1)
            error_text = stderr.getvalue()
            self.assertIn("collect_release_copy_context.py:", error_text)
            self.assertIn("bindings.publish_config_path", error_text)
            self.assertIn("missing file", error_text)
            self.assertNotIn("Traceback", error_text)


if __name__ == "__main__":
    unittest.main()
