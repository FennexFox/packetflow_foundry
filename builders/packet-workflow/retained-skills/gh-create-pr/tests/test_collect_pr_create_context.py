from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CollectPrCreateContextTests(unittest.TestCase):
    def test_import_resolves_builder_scripts_from_vendored_foundry_for_root_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            override_scripts_dir = repo_root / ".agents" / "skills" / "gh-create-pr" / "scripts"
            builder_scripts_dir = (
                repo_root
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "scripts"
            )

            write_text(
                override_scripts_dir / "collect_pr_create_context.py",
                (SCRIPT_DIR / "collect_pr_create_context.py").read_text(encoding="utf-8"),
            )
            write_text(
                override_scripts_dir / "pr_create_tools.py",
                "def build_context(**_kwargs):\n"
                "    return {\"builder_compatibility\": {\"status\": \"current\"}}\n",
            )
            write_text(
                builder_scripts_dir / "packet_workflow_versioning.py",
                "def classify_builder_compatibility(**_kwargs):\n"
                "    return {\"status\": \"current\"}\n\n"
                "def extract_profile_versioning(_value):\n"
                "    return None\n\n"
                "def extract_skill_builder_versioning(_value):\n"
                "    return None\n\n"
                "def format_runtime_warning(_value):\n"
                "    return \"warning\"\n\n"
                "def load_builder_versioning():\n"
                "    return {\"builder_family\": \"packet-workflow\", \"builder_semver\": \"1.0.0\"}\n\n"
                "def load_json_document(_path):\n"
                "    return {}\n",
            )

            module_name = "temp_collect_pr_create_context"
            original_sys_path = list(sys.path)
            try:
                sys.path.insert(0, str(override_scripts_dir))
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    override_scripts_dir / "collect_pr_create_context.py",
                )
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            finally:
                sys.path[:] = original_sys_path
                sys.modules.pop(module_name, None)

        self.assertEqual(module.BUILDER_SCRIPTS_DIR, builder_scripts_dir.resolve())

    def test_main_passes_explicit_issue_hints_to_build_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            override_scripts_dir = repo_root / ".agents" / "skills" / "gh-create-pr" / "scripts"
            builder_scripts_dir = (
                repo_root
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "scripts"
            )
            skill_root = override_scripts_dir.parent

            write_text(
                override_scripts_dir / "collect_pr_create_context.py",
                (SCRIPT_DIR / "collect_pr_create_context.py").read_text(encoding="utf-8"),
            )
            write_text(
                override_scripts_dir / "pr_create_tools.py",
                "def build_context(**kwargs):\n"
                "    return {\n"
                "        \"builder_compatibility\": {\"status\": \"current\"},\n"
                "        \"captured_issue_hints\": kwargs.get(\"issue_hints\"),\n"
                "    }\n",
            )
            write_text(
                skill_root / "profiles" / "default" / "profile.json",
                "{\n"
                "  \"name\": \"default\",\n"
                "  \"summary\": \"Default profile\"\n"
                "}\n",
            )
            write_text(
                builder_scripts_dir / "packet_workflow_versioning.py",
                "def classify_builder_compatibility(**_kwargs):\n"
                "    return {\"status\": \"current\"}\n\n"
                "def extract_profile_versioning(_value):\n"
                "    return None\n\n"
                "def extract_skill_builder_versioning(_value):\n"
                "    return None\n\n"
                "def format_runtime_warning(_value):\n"
                "    return \"warning\"\n\n"
                "def load_builder_versioning():\n"
                "    return {\"builder_family\": \"packet-workflow\", \"builder_semver\": \"1.0.0\"}\n\n"
                "def load_json_document(_path):\n"
                "    return {}\n",
            )

            module_name = "temp_collect_pr_create_context_issue_hints"
            original_sys_path = list(sys.path)
            original_argv = list(sys.argv)
            original_pr_create_tools = sys.modules.pop("pr_create_tools", None)
            original_versioning = sys.modules.pop("packet_workflow_versioning", None)
            try:
                sys.path.insert(0, str(override_scripts_dir))
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    override_scripts_dir / "collect_pr_create_context.py",
                )
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                output_path = repo_root / "context.json"
                sys.argv = [
                    "collect_pr_create_context.py",
                    "--repo-root",
                    str(repo_root),
                    "--issue-hint",
                    "#15",
                    "--issue-hint",
                    "27",
                    "--output",
                    str(output_path),
                ]
                exit_code = module.main()
            finally:
                sys.path[:] = original_sys_path
                sys.argv[:] = original_argv
                if original_pr_create_tools is not None:
                    sys.modules["pr_create_tools"] = original_pr_create_tools
                if original_versioning is not None:
                    sys.modules["packet_workflow_versioning"] = original_versioning
                sys.modules.pop(module_name, None)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["captured_issue_hints"], ["#15", "27"])


if __name__ == "__main__":
    unittest.main()
