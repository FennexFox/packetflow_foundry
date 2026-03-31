from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
