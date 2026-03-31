from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
REWORD_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "reword-recent-commits"
    / "scripts"
)
GIT_SPLIT_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "git-split-and-commit"
    / "scripts"
)
for candidate in (SCRIPT_DIR, REWORD_SCRIPT_DIR, GIT_SPLIT_SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import collect_recent_commits as reword_collect
import collect_worktree_context as worktree_collect
import init_consumer_codex as bootstrap


def run_python(
    script: Path,
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def create_consumer_repo(
    root: Path,
    *,
    include_readme: bool = True,
    root_agents_text: str | None = None,
    codex_agents_text: str | None = None,
    existing_profile: bool = False,
    existing_skill_gitkeep: bool = False,
    existing_agent_gitkeep: bool = False,
    include_vendor: bool = True,
) -> Path:
    repo = root / "consumer"
    repo.mkdir()
    (repo / ".git").mkdir()
    if include_readme:
        (repo / "README.md").write_text("# Consumer Repo\n", encoding="utf-8")
    if include_vendor:
        (repo / ".codex" / "vendor" / "packetflow_foundry").mkdir(parents=True)
    if root_agents_text is not None:
        (repo / "AGENTS.md").write_text(root_agents_text, encoding="utf-8")
    if codex_agents_text is not None:
        codex_agents_path = repo / ".codex" / "AGENTS.md"
        codex_agents_path.parent.mkdir(parents=True, exist_ok=True)
        codex_agents_path.write_text(codex_agents_text, encoding="utf-8")
    if existing_profile:
        profile_path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text("{}", encoding="utf-8")
    if existing_skill_gitkeep:
        gitkeep_path = repo / bootstrap.PROJECT_SKILLS_GITKEEP_RELATIVE
        gitkeep_path.parent.mkdir(parents=True, exist_ok=True)
        gitkeep_path.write_text("\n", encoding="utf-8")
    if existing_agent_gitkeep:
        gitkeep_path = repo / bootstrap.PROJECT_AGENTS_GITKEEP_RELATIVE
        gitkeep_path.parent.mkdir(parents=True, exist_ok=True)
        gitkeep_path.write_text("\n", encoding="utf-8")
    return repo


class ConsumerBootstrapTests(unittest.TestCase):
    def test_script_compiles(self) -> None:
        py_compile.compile(
            str(SCRIPT_DIR / "init_consumer_codex.py"),
            doraise=True,
        )

    def test_init_creates_codex_scaffold_without_root_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp))

            result = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                cwd=repo,
            )

            self.assertIn("root AGENTS.md: not present", result.stdout)
            self.assertIn(".codex/AGENTS.md: created", result.stdout)
            self.assertFalse((repo / "AGENTS.md").exists())

            codex_agents = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(bootstrap.BOOTSTRAP_MARKER_START, codex_agents)
            self.assertIn(".codex/vendor/packetflow_foundry", codex_agents)
            self.assertIn(
                ".codex/project/profiles/default/profile.json",
                codex_agents,
            )

            profile = json.loads(
                (repo / bootstrap.PROJECT_PROFILE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertEqual(
                profile["kind"],
                bootstrap.PROJECT_LOCAL_PROFILE_KIND,
            )
            self.assertEqual(
                profile["profile_path"],
                bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
            )
            self.assertEqual(
                profile["repo_match"]["root_markers"],
                [".git", "README.md"],
            )
            self.assertIn("project-local scaffold", profile["summary"].lower())
            self.assertTrue(
                any(
                    "not a reusable foundry overlay" in note
                    for note in profile["notes"]
                )
            )

    def test_root_markers_skip_readme_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), include_readme=False)

            run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            )

            profile = json.loads(
                (repo / bootstrap.PROJECT_PROFILE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertEqual(profile["repo_match"]["root_markers"], [".git"])

    def test_existing_agents_files_append_once_then_stay_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text="# Root AGENTS\n",
                codex_agents_text="# Local Codex AGENTS\n",
            )

            first = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            )
            (repo / bootstrap.PROJECT_PROFILE_RELATIVE).unlink()
            (repo / bootstrap.PROJECT_SKILLS_GITKEEP_RELATIVE).unlink()
            (repo / bootstrap.PROJECT_AGENTS_GITKEEP_RELATIVE).unlink()
            second = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            )

            self.assertIn("root AGENTS.md: appended foundry block", first.stdout)
            self.assertIn(".codex/AGENTS.md: appended foundry block", first.stdout)
            self.assertIn("root AGENTS.md: unchanged", second.stdout)
            self.assertIn(".codex/AGENTS.md: unchanged", second.stdout)

            root_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            codex_agents = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(root_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)
            self.assertEqual(codex_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)

    def test_existing_agents_with_foundry_keywords_stay_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text=(
                    "# Root AGENTS\n\nVendor path: .codex/vendor/packetflow_foundry\n"
                ),
                codex_agents_text="# Local Codex AGENTS\n\npacketflow_foundry note\n",
            )

            root_before = (repo / "AGENTS.md").read_text(encoding="utf-8")
            codex_before = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")

            result = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            )

            self.assertIn("root AGENTS.md: unchanged", result.stdout)
            self.assertIn(".codex/AGENTS.md: unchanged", result.stdout)
            self.assertEqual(
                (repo / "AGENTS.md").read_text(encoding="utf-8"),
                root_before,
            )
            self.assertEqual(
                (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8"),
                codex_before,
            )

    def test_generated_profile_is_reader_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp))
            run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
            )

            profile_path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
            worktree_profile = worktree_collect.load_repo_profile(profile_path)
            reword_profile = reword_collect.load_repo_profile_document(profile_path)

            self.assertEqual(
                worktree_profile["kind"],
                bootstrap.PROJECT_LOCAL_PROFILE_KIND,
            )
            self.assertEqual(
                reword_profile["profile_path"],
                bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
            )

    def test_conflicting_generated_output_aborts_without_touching_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text="# Root AGENTS\n",
                codex_agents_text="# Local Codex AGENTS\n",
                existing_profile=True,
            )

            result = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "Refusing to overwrite existing bootstrap outputs",
                result.stderr,
            )
            self.assertNotIn(
                bootstrap.BOOTSTRAP_MARKER_START,
                (repo / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                bootstrap.BOOTSTRAP_MARKER_START,
                (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((repo / bootstrap.PROJECT_SKILLS_GITKEEP_RELATIVE).exists())
            self.assertFalse((repo / bootstrap.PROJECT_AGENTS_GITKEEP_RELATIVE).exists())

    def test_missing_vendor_subtree_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), include_vendor=False)

            result = run_python(
                SCRIPT_DIR / "init_consumer_codex.py",
                "--repo-root",
                str(repo),
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Missing PacketFlow Foundry vendor subtree", result.stderr)
            self.assertFalse((repo / ".codex" / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
