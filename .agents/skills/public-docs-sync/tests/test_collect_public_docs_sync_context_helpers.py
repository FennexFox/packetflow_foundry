from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_public_docs_sync_context as collector  # noqa: E402


class CollectPublicDocsSyncContextHelperTests(unittest.TestCase):
    def test_default_state_file_uses_skill_state_path(self) -> None:
        path = collector.default_state_file("abc123")
        self.assertTrue(str(path).endswith(str(Path(".codex/state/public-docs-sync/abc123.json"))))

    def test_builder_compatibility_reports_current(self) -> None:
        profile = collector.load_repo_profile(collector.default_repo_profile_path())
        compatibility = collector.build_builder_compatibility(profile)
        self.assertEqual(compatibility["status"], "current")

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

    def test_require_gh_auth_stops_cleanly_when_gh_is_missing(self) -> None:
        with mock.patch.object(collector.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(SystemExit) as exc_info:
                collector.require_gh_auth(Path("C:/repo"))
        self.assertIn("gh auth is invalid", str(exc_info.exception))

    def test_build_artifact_entry_uses_repo_profile_for_path_packet_hints(self) -> None:
        profile = collector.load_repo_profile(collector.default_repo_profile_path())
        artifact = collector.build_artifact_entry(
            artifact_type="pull_request",
            identifier="PR #1",
            title="docs: update workflow docs",
            body=None,
            url="https://example.invalid/pr/1",
            comment_digests=[],
            changed_paths=["CONTRIBUTING.md"],
            public_doc_paths=["CONTRIBUTING.md"],
            repo_profile=profile,
        )
        self.assertIn("workflow_packet", artifact["packet_hints"])


if __name__ == "__main__":
    unittest.main()
