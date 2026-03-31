from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pr_writeup_tools as tools  # noqa: E402


class PrWriteupToolsTests(unittest.TestCase):
    def test_classify_changed_files_and_summary_cover_expected_groups(self) -> None:
        groups = tools.classify_changed_files(
            [
                "NoOfficeDemandFix/Mod.cs",
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
        self.assertEqual(summary["runtime"]["sample_files"], ["NoOfficeDemandFix/Mod.cs"])
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


if __name__ == "__main__":
    unittest.main()
