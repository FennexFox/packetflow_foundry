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

            argv = worktree_context.unittest_discover_argv(
                "builders/packet-workflow/retained-skills/gh-address-review-threads/tests",
                "test_build_review_packets.py",
            )
            self.assertEqual(
                candidates,
                [
                    {
                        "command": worktree_context.unittest_discover_command(
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests",
                            "test_build_review_packets.py",
                        ),
                        "argv": argv,
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

            argv = worktree_context.unittest_discover_argv(
                ".github/scripts/tests",
                "test_*.py",
            )
            self.assertEqual(
                candidates,
                [
                    {
                        "command": worktree_context.unittest_discover_command(
                            ".github/scripts/tests",
                            "test_*.py",
                        ),
                        "argv": argv,
                        "reason": "Changed Python code without a complete one-to-one test mapping in the sibling tests directory.",
                        "paths": [
                            ".github/scripts/subdir/task.py",
                        ],
                    }
                ],
            )

    def test_targeted_validation_candidates_keep_script_candidates_when_tests_also_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_text(repo / ".github" / "scripts" / "tests" / "test_existing.py", "import unittest\n")
            write_text(repo / "tests" / "test_unrelated.py", "import unittest\n")

            candidates = worktree_context.targeted_validation_candidates(
                repo,
                [
                    ".github/scripts/subdir/task.py",
                    "tests/test_unrelated.py",
                ],
            )

            script_argv = worktree_context.unittest_discover_argv(
                ".github/scripts/tests",
                "test_*.py",
            )
            test_argv = worktree_context.unittest_discover_argv("tests", "test_unrelated.py")
            self.assertEqual(
                candidates,
                [
                    {
                        "command": worktree_context.unittest_discover_command("tests", "test_unrelated.py"),
                        "argv": test_argv,
                        "reason": "Changed test file tests/test_unrelated.py.",
                        "paths": ["tests/test_unrelated.py"],
                    },
                    {
                        "command": worktree_context.unittest_discover_command(
                            ".github/scripts/tests",
                            "test_*.py",
                        ),
                        "argv": script_argv,
                        "reason": "Changed Python code without a complete one-to-one test mapping in the sibling tests directory.",
                        "paths": [".github/scripts/subdir/task.py"],
                    },
                ],
            )

    def test_targeted_validation_candidates_include_workflow_fallback_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            write_text(repo / ".github" / "scripts" / "tests" / "test_workflows.py", "import unittest\n")

            candidates = worktree_context.targeted_validation_candidates(
                repo,
                [
                    ".github/workflows/ci.yml",
                ],
            )

            argv = worktree_context.unittest_discover_argv(
                ".github/scripts/tests",
                "test_*.py",
            )
            self.assertEqual(
                candidates,
                [
                    {
                        "command": worktree_context.unittest_discover_command(
                            ".github/scripts/tests",
                            "test_*.py",
                        ),
                        "argv": argv,
                        "reason": "Changed GitHub workflow files that orchestrate automation tests.",
                        "paths": [".github/workflows/ci.yml"],
                    }
                ],
            )

    def test_targeted_validation_candidates_dedupe_duplicate_mapped_test_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            test_path = (
                repo
                / "builders"
                / "packet-workflow"
                / "retained-skills"
                / "gh-address-review-threads"
                / "tests"
                / "test_shared_builder.py"
            )
            write_text(test_path, "import unittest\n")

            candidates = worktree_context.targeted_validation_candidates(
                repo,
                [
                    "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/subdir-a/shared_builder.py",
                    "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/subdir-b/shared_builder.py",
                ],
            )

            argv = worktree_context.unittest_discover_argv(
                "builders/packet-workflow/retained-skills/gh-address-review-threads/tests",
                "test_shared_builder.py",
            )
            self.assertEqual(
                candidates,
                [
                    {
                        "command": worktree_context.unittest_discover_command(
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests",
                            "test_shared_builder.py",
                        ),
                        "argv": argv,
                        "reason": (
                            "Changed script "
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/subdir-a/shared_builder.py "
                            "with matching test "
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_shared_builder.py."
                        ),
                        "paths": [
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/scripts/subdir-a/shared_builder.py",
                            "builders/packet-workflow/retained-skills/gh-address-review-threads/tests/test_shared_builder.py",
                        ],
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
