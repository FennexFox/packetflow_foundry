import tempfile
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_release_copy_context as collector


class CollectReleaseCopyContextProfileResolutionTests(unittest.TestCase):
    def test_default_repo_profile_path_prefers_project_local_skill_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            project_profile = (
                repo_root / ".codex" / "project" / "profiles" / "draft-release-copy" / "profile.json"
            )
            project_profile.parent.mkdir(parents=True, exist_ok=True)
            project_profile.write_text("{}", encoding="utf-8")

            resolved = collector.default_repo_profile_path(repo_root)

            self.assertEqual(resolved, project_profile.resolve())

    def test_default_repo_profile_path_falls_back_to_project_default_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            default_profile = repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json"
            default_profile.parent.mkdir(parents=True, exist_ok=True)
            default_profile.write_text("{}", encoding="utf-8")

            resolved = collector.default_repo_profile_path(repo_root)

            self.assertEqual(resolved, default_profile.resolve())

    def test_default_repo_profile_path_falls_back_to_retained_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            resolved = collector.default_repo_profile_path(repo_root)

            self.assertEqual(resolved, collector.retained_default_repo_profile_path())

    def test_resolve_profile_path_prefers_repo_relative_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            project_profile = (
                repo_root / ".codex" / "project" / "profiles" / "draft-release-copy" / "profile.json"
            )
            project_profile.parent.mkdir(parents=True, exist_ok=True)
            project_profile.write_text("{}", encoding="utf-8")

            resolved = collector.resolve_profile_path(
                ".codex/project/profiles/draft-release-copy/profile.json",
                repo_root,
            )

            self.assertEqual(resolved, project_profile.resolve())

    def test_resolve_profile_path_accepts_skill_relative_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            resolved = collector.resolve_profile_path("profiles/default/profile.json", repo_root)

            self.assertEqual(resolved, collector.retained_default_repo_profile_path())

if __name__ == "__main__":
    unittest.main()
