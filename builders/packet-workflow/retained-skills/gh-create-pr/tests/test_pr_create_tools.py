from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_create_tools as tools  # noqa: E402
from pr_create_test_support import REPO_TEMPLATE_SECTIONS  # noqa: E402

def run_git(repo_root: Path, args: list[str]) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        stdin=subprocess.DEVNULL,
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
        stdin=subprocess.DEVNULL,
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
        (
            "## What changed\n\n## Why\n\n## How\n\n## Testing\n\n## Compatibility / Adoption\n\n"
            "## Risk / Rollback\n\n## Reviewer Checklist\n\n## PR Classification (optional)\n\nJustification:\n"
        ),
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
    def test_read_utf8_text_accepts_bom_prefixed_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body.md"
            path.write_text("## What changed\nOpen the PR safely.\n", encoding="utf-8-sig")

            text = tools.read_utf8_text(path)

        self.assertEqual(text.splitlines()[0], "## What changed")
        self.assertFalse(text.startswith("\ufeff"))

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
            self.assertEqual(context["expected_template_sections"], REPO_TEMPLATE_SECTIONS)
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

    def test_build_context_merges_explicit_issue_hints_when_branch_and_commits_have_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            origin_root = root / "origin.git"
            repo_root.mkdir()
            init_repo(repo_root, origin_root)

            run_git(repo_root, ["checkout", "main"])
            run_git(repo_root, ["checkout", "-b", "feature/pr-create-operator"])
            run_git(repo_root, ["config", "branch.feature/pr-create-operator.gh-merge-base", "main"])
            write_text(repo_root / "src" / "feature.py", "VALUE = 3\n")
            run_git(repo_root, ["add", "."])
            run_git(repo_root, ["commit", "-m", "feat(pr-create): add guarded creator"])
            run_git(repo_root, ["push", "-u", "origin", "feature/pr-create-operator"])

            context = tools.build_context(
                repo_root=repo_root,
                repo_slug="owner/repo",
                base_ref="main",
                head_ref="feature/pr-create-operator",
                issue_hints=["#15", "15"],
            )

            self.assertEqual(context["issue_reference_hints"]["numbers"], ["15"])
            self.assertEqual(context["issue_reference_hints"]["branch_numbers"], [])
            self.assertEqual(context["issue_reference_hints"]["commit_numbers"], [])
            self.assertEqual(context["issue_reference_hints"]["operator_supplied"], ["15"])

    def test_build_context_rejects_free_form_explicit_issue_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            origin_root = root / "origin.git"
            repo_root.mkdir()
            init_repo(repo_root, origin_root)

            with self.assertRaisesRegex(ValueError, "Explicit issue hints must be exact issue numbers"):
                tools.build_context(
                    repo_root=repo_root,
                    repo_slug="owner/repo",
                    issue_hints=["Refs: #42"],
                )

    def test_select_pr_template_fails_closed_when_multiple_candidates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_text(repo_root / ".github" / "pull_request_template.md", "## What changed\n")
            write_text(repo_root / ".github" / "PULL_REQUEST_TEMPLATE" / "alt.md", "## What changed\n")

            selection = tools.select_pr_template(repo_root)

            self.assertEqual(selection["status"], "ambiguous")
            self.assertGreaterEqual(len(selection["all_candidates"]), 2)

    def test_stubbed_gh_pr_create_reads_bom_prefixed_body_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            body_path = tmp_path / "body.md"
            state_path.write_text(
                json.dumps(
                    {
                        "repo_slug": "owner/repo",
                        "default_branch": "main",
                        "existing_prs": [],
                        "next_pr_number": 101,
                    }
                ),
                encoding="utf-8",
            )
            body_path.write_text("## What changed\nOpen safely.\n", encoding="utf-8-sig")

            with mock.patch.dict(tools.os.environ, {tools.GH_STUB_STATE_ENV: str(state_path)}):
                output = tools.run_command(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--title",
                        "feat(pr-create): open guarded PRs",
                        "--body-file",
                        str(body_path),
                        "--base",
                        "main",
                        "--head",
                        "feature/pr-create",
                    ],
                    cwd=tmp_path,
                )

            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("/pull/101", output)
            self.assertEqual(updated["existing_prs"][0]["body"].splitlines()[0], "## What changed")
            self.assertFalse(updated["existing_prs"][0]["body"].startswith("\ufeff"))


if __name__ == "__main__":
    unittest.main()
