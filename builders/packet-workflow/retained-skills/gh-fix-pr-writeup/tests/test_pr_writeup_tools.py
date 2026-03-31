from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_writeup_tools as tools  # noqa: E402


class PrWriteupToolsTests(unittest.TestCase):
    def test_infer_repo_slug_accepts_dotted_repo_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_root), check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "remote", "add", "origin", "git@github.com:owner/my.repo.git"],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(tools.infer_repo_slug(repo_root), "owner/my.repo")

    def test_run_command_wraps_missing_executable(self) -> None:
        with mock.patch.object(tools.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(RuntimeError) as exc_info:
                tools.run_command(["gh", "auth", "status"], cwd=Path("C:/repo"))
        self.assertEqual(str(exc_info.exception), "gh executable not found")

    def test_classify_changed_files_and_summary_cover_expected_groups(self) -> None:
        groups = tools.classify_changed_files(
            [
                "ExampleProduct/Mod.cs",
                ".github/workflows/check.yml",
                "docs/guide.md",
                "tests/writeup_test.py",
                "Directory.Build.props",
                "assets/icon.png",
            ]
        )
        summary = tools.summarize_groups(groups)

        self.assertEqual(summary["runtime"]["count"], 1)
        self.assertEqual(summary["automation"]["count"], 1)
        self.assertEqual(summary["docs"]["count"], 1)
        self.assertEqual(summary["tests"]["count"], 1)
        self.assertEqual(summary["config"]["count"], 1)
        self.assertEqual(summary["other"]["count"], 1)
        self.assertEqual(summary["runtime"]["sample_files"], ["ExampleProduct/Mod.cs"])
        self.assertEqual(summary["tests"]["sample_files"], ["tests/writeup_test.py"])
        self.assertEqual(summary["config"]["sample_strategy"], "directory_round_robin")

    def test_select_representative_files_round_robins_then_preserves_original_order(self) -> None:
        selected = tools.select_representative_files(
            [
                "src/a/one.cs",
                "src/a/two.cs",
                "src/b/one.cs",
                "src/b/two.cs",
                "docs/alpha.md",
                "docs/beta.md",
            ],
            limit=4,
        )

        self.assertEqual(
            selected,
            [
                "src/a/one.cs",
                "src/a/two.cs",
                "src/b/one.cs",
                "docs/alpha.md",
            ],
        )

    def test_first_heading_block_returns_requested_heading_only(self) -> None:
        markdown = "\n".join(
            [
                "# Title",
                "## PR Title",
                "- Use a conventional title.",
                "",
                "## Body",
                "- Keep the template order.",
            ]
        )

        self.assertEqual(
            tools.first_heading_block(markdown, "## PR Title"),
            "## PR Title\n- Use a conventional title.",
        )

    def test_load_pr_changed_files_falls_back_to_api_when_diff_is_too_large(self) -> None:
        with mock.patch.object(
            tools,
            "run_command",
            side_effect=[
                subprocess.CalledProcessError(
                    1,
                    ["gh", "pr", "diff", "7", "--name-only", "--repo", "owner/repo"],
                    stderr=(
                        "could not find pull request diff: HTTP 406: Sorry, the diff exceeded "
                        "the maximum number of lines (20000)\nPullRequest.diff too_large"
                    ),
                ),
                "src/foo.py\nsrc/bar.py\n",
            ],
        ) as run_command:
            result = tools.load_pr_changed_files(7, Path("C:/repo"), "owner/repo")

        self.assertEqual(result, ["src/foo.py", "src/bar.py"])
        self.assertEqual(run_command.call_count, 2)
        self.assertEqual(
            run_command.call_args_list[1].args[0],
            [
                "gh",
                "api",
                "repos/owner/repo/pulls/7/files",
                "--paginate",
                "--jq",
                ".[].filename",
            ],
        )


if __name__ == "__main__":
    unittest.main()
