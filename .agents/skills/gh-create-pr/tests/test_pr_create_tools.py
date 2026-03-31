from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_create_tools as tools  # noqa: E402


def run_git(repo_root: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_repo(repo_root: Path, origin_root: Path) -> None:
    origin_root.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "init", "--bare", str(origin_root)],
        cwd=str(origin_root.parent),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git init --bare failed")
    run_git(repo_root, ["init", "-b", "main"])
    run_git(repo_root, ["config", "user.name", "Tests"])
    run_git(repo_root, ["config", "user.email", "tests@example.invalid"])
    run_git(repo_root, ["remote", "add", "origin", str(origin_root)])

    write_text(
        repo_root / ".github" / "pull_request_template.md",
        "## Why\n\n## What changed\n\n## How\n\n## Risk / Rollback\n\n## Testing\n",
    )
    write_text(
        repo_root / ".github" / "instructions" / "pull-request.instructions.md",
        "# Rules\n\n## PR Title\nUse Conventional Commit style.\n",
    )
    write_text(
        repo_root / ".github" / "instructions" / "commit-message.instructions.md",
        "# Commit Rules\n\n## Types\n- feat\n- fix\n",
    )
    write_text(repo_root / "README.md", "# Repo\n")
    write_text(repo_root / "src" / "feature.py", "VALUE = 1\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "Initial commit"])
    run_git(repo_root, ["push", "-u", "origin", "main"])

    run_git(repo_root, ["checkout", "-b", "release"])
    run_git(repo_root, ["push", "-u", "origin", "release"])

    run_git(repo_root, ["checkout", "main"])
    run_git(repo_root, ["checkout", "-b", "feature/pr-create"])
    run_git(repo_root, ["config", "branch.feature/pr-create.gh-merge-base", "main"])
    write_text(repo_root / "src" / "feature.py", "VALUE = 2\n")
    run_git(repo_root, ["add", "."])
    run_git(repo_root, ["commit", "-m", "feat(pr-create): add guarded creator #42"])
    run_git(repo_root, ["push", "-u", "origin", "feature/pr-create"])


class PrCreateToolsTests(unittest.TestCase):
    def test_infer_repo_slug_accepts_dotted_repo_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            run_git(repo_root, ["init", "-b", "main"])
            run_git(repo_root, ["remote", "add", "origin", "git@github.com:owner/my.repo.git"])

            self.assertEqual(tools.infer_repo_slug(repo_root), "owner/my.repo")

    def test_build_context_resolves_defaults_from_branch_and_profiled_repo_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            origin_root = root / "origin.git"
            repo_root.mkdir()
            init_repo(repo_root, origin_root)

            context = tools.build_context(repo_root=repo_root, repo_slug="owner/repo")

            self.assertEqual(context["resolved_head"], "feature/pr-create")
            self.assertEqual(context["resolved_base"], "main")
            self.assertEqual(context["repo_slug"], "owner/repo")
            self.assertEqual(context["template_selection"]["status"], "selected")
            self.assertTrue(context["changed_files"])
            self.assertEqual(context["duplicate_check_hint"]["status"], "unavailable")

    def test_build_context_respects_explicit_base_and_head_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            origin_root = root / "origin.git"
            repo_root.mkdir()
            init_repo(repo_root, origin_root)

            context = tools.build_context(
                repo_root=repo_root,
                repo_slug="owner/repo",
                base_ref="release",
                head_ref="feature/pr-create",
            )

            self.assertEqual(context["resolved_base"], "release")
            self.assertEqual(context["resolved_head"], "feature/pr-create")

    def test_select_pr_template_fails_closed_when_multiple_candidates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_text(repo_root / ".github" / "pull_request_template.md", "## Why\n")
            write_text(repo_root / ".github" / "PULL_REQUEST_TEMPLATE" / "alt.md", "## Why\n")

            selection = tools.select_pr_template(repo_root)

            self.assertEqual(selection["status"], "ambiguous")
            self.assertGreaterEqual(len(selection["all_candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
