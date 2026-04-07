from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_worktree_context as worktree_context  # type: ignore  # noqa: E402


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class CollectWorktreeContextTests(unittest.TestCase):
    def test_tracked_test_for_script_maps_retained_skill_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_text(
                repo
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "gh-address-review-threads"
                / "tests"
                / "test_build_review_packets.py",
                "import unittest\n",
            )

            mapped = worktree_context.tracked_test_for_script(
                repo,
                "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/build_review_packets.py",
            )

            self.assertEqual(
                mapped,
                "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_build_review_packets.py",
            )

    def test_targeted_validation_candidates_include_retained_skill_test_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            test_path = (
                repo
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "gh-address-review-threads"
                / "tests"
                / "test_build_review_packets.py"
            )
            write_text(test_path, "import unittest\n")

            candidates = worktree_context.targeted_validation_candidates(
                repo,
                [
                    "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/build_review_packets.py",
                    "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_build_review_packets.py",
                ],
            )

            self.assertEqual(
                candidates,
                [
                    {
                        "command": (
                            'python -m unittest discover -s '
                            'builders/packet-workflow/retained-skills/gh-address-review-threads/tests '
                            '-p "test_build_review_packets.py"'
                        ),
                        "reason": (
                            "Changed test file "
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/"
                            "test_build_review_packets.py."
                        ),
                        "paths": [
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_build_review_packets.py"
                        ],
                    }
                ],
            )

    def test_tracked_test_for_nested_script_maps_to_sibling_tests_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_text(
                repo
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "gh-address-review-threads"
                / "tests"
                / "test_packet_builder.py",
                "import unittest\n",
            )

            mapped = worktree_context.tracked_test_for_script(
                repo,
                "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/subdir/packet_builder.py",
            )

            self.assertEqual(
                mapped,
                "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_packet_builder.py",
            )

    def test_targeted_validation_candidates_include_nested_github_script_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_text(repo / ".github" / "scripts" / "tests" / "test_existing.py", "import unittest\n")

            candidates = worktree_context.targeted_validation_candidates(
                repo,
                [
                    ".github/scripts/subdir/task.py",
                ],
            )

            self.assertEqual(
                candidates,
                [
                    {
                        "command": 'python -m unittest discover -s .github/scripts/tests -p "test_*.py"',
                        "reason": "Changed Python code without a complete one-to-one test mapping in the sibling tests directory.",
                        "paths": [
                            ".github/scripts/subdir/task.py",
                        ],
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
