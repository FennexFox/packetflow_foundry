from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_SCRIPT_DIRS = [
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "draft-release-copy" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "gh-address-review-threads" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "gh-create-pr" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "gh-fix-pr-writeup" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "git-split-and-commit" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "public-docs-sync" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "reword-recent-commits" / "scripts",
    REPO_ROOT / "builders" / "packet-workflow" / "retained-skills" / "weekly-update" / "scripts",
]
for script_dir in SKILL_SCRIPT_DIRS:
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

import collect_pr_context as gh_fix_pr_writeup_collect
import collect_pr_create_context as gh_create_pr_collect
import collect_public_docs_sync_context as public_docs_sync_collect
import collect_recent_commits as reword_recent_commits_collect
import collect_release_copy_context as draft_release_copy_collect
import collect_review_threads as gh_address_review_threads_collect
import collect_worktree_context as git_split_and_commit_collect
import weekly_update_lib as weekly_update_lib


MODULES = [
    draft_release_copy_collect,
    gh_address_review_threads_collect,
    gh_create_pr_collect,
    gh_fix_pr_writeup_collect,
    git_split_and_commit_collect,
    public_docs_sync_collect,
    reword_recent_commits_collect,
    weekly_update_lib,
]


class ProjectLocalProfileResolutionTests(unittest.TestCase):
    def test_default_repo_profile_path_prefers_skill_specific_then_default_then_retained(self) -> None:
        for module in MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as tmpdir:
                    repo_root = Path(tmpdir)
                    skill_profile = (
                        repo_root
                        / ".codex"
                        / "project"
                        / "profiles"
                        / module.skill_root().name
                        / "profile.json"
                    )
                    default_profile = (
                        repo_root / ".codex" / "project" / "profiles" / "default" / "profile.json"
                    )

                    skill_profile.parent.mkdir(parents=True, exist_ok=True)
                    skill_profile.write_text("{}", encoding="utf-8")
                    self.assertEqual(
                        module.default_repo_profile_path(repo_root),
                        skill_profile.resolve(),
                    )

                    skill_profile.unlink()
                    default_profile.parent.mkdir(parents=True, exist_ok=True)
                    default_profile.write_text("{}", encoding="utf-8")
                    self.assertEqual(
                        module.default_repo_profile_path(repo_root),
                        default_profile.resolve(),
                    )

                    default_profile.unlink()
                    self.assertEqual(
                        module.default_repo_profile_path(repo_root),
                        module.retained_default_repo_profile_path(),
                    )

    def test_resolve_profile_path_prefers_repo_root_then_skill_root(self) -> None:
        for module in MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as tmpdir:
                    repo_root = Path(tmpdir)
                    skill_profile_relative = (
                        Path(".codex")
                        / "project"
                        / "profiles"
                        / module.skill_root().name
                        / "profile.json"
                    )
                    default_profile_relative = (
                        Path(".codex") / "project" / "profiles" / "default" / "profile.json"
                    )
                    skill_profile = repo_root / skill_profile_relative
                    default_profile = repo_root / default_profile_relative
                    skill_profile.parent.mkdir(parents=True, exist_ok=True)
                    default_profile.parent.mkdir(parents=True, exist_ok=True)
                    skill_profile.write_text("{}", encoding="utf-8")
                    default_profile.write_text("{}", encoding="utf-8")

                    self.assertEqual(
                        module.resolve_profile_path(skill_profile_relative.as_posix(), repo_root),
                        skill_profile.resolve(),
                    )
                    self.assertEqual(
                        module.resolve_profile_path(default_profile_relative.as_posix(), repo_root),
                        default_profile.resolve(),
                    )
                    self.assertEqual(
                        module.resolve_profile_path("profiles/default/profile.json", repo_root),
                        module.retained_default_repo_profile_path(),
                    )


if __name__ == "__main__":
    unittest.main()
