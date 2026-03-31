from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_public_docs_sync_context as collector  # noqa: E402


class CollectPublicDocsSyncContextHelperTests(unittest.TestCase):
    def test_default_state_file_uses_skill_state_path(self) -> None:
        path = collector.default_state_file("abc123")
        self.assertTrue(str(path).endswith(str(Path(".codex/state/public-docs-sync/abc123.json"))))

    def test_build_context_fingerprint_changes_when_inventory_changes(self) -> None:
        left = collector.build_context_fingerprint(
            "head",
            {"mode": "saved", "base_commit": "base"},
            {"kind": "merge-base", "base_commit": "base", "head_commit": "head", "primary_pr_number": None},
            ["README.md"],
            {"README.md": {"sha256": "aaa"}},
            "digest-1",
        )
        right = collector.build_context_fingerprint(
            "head",
            {"mode": "saved", "base_commit": "base"},
            {"kind": "merge-base", "base_commit": "base", "head_commit": "head", "primary_pr_number": None},
            ["README.md"],
            {"README.md": {"sha256": "bbb"}},
            "digest-1",
        )
        self.assertNotEqual(left, right)


if __name__ == "__main__":
    unittest.main()
