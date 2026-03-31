from __future__ import annotations

import sys
import tempfile
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

    def test_infer_repo_slug_accepts_dotted_repo_names(self) -> None:
        self.assertEqual(
            collector.infer_repo_slug("git@github.com:owner/my.repo.git"),
            "owner/my.repo",
        )

    def test_main_passes_repo_profile_into_github_evidence_collection(self) -> None:
        profile = {
            "name": "default",
            "summary": "test profile",
            "bindings": {
                "primary_readme_path": "README.md",
                "publish_config_path": None,
                "settings_source_path": None,
            },
        }
        identity = {
            "repo_name": "packetflow_foundry",
            "repo_id": "repo-id",
            "repo_hash": "repo-hash",
            "remote_url": "https://github.com/FennexFox/packetflow_foundry",
            "repo_slug": "FennexFox/packetflow_foundry",
        }
        relevant_ref = {
            "kind": "current-branch-pr",
            "base_commit": None,
            "head_commit": "head-sha",
            "primary_pr_number": 1,
        }
        observed: dict[str, object] = {}

        def fake_collect_github_evidence(
            repo_root: Path,
            actual_identity: dict[str, str],
            actual_relevant_ref: dict[str, object],
            public_doc_paths: list[str],
            actual_repo_profile: dict[str, object],
        ) -> dict[str, object]:
            observed["repo_root"] = repo_root
            observed["identity"] = actual_identity
            observed["relevant_ref"] = actual_relevant_ref
            observed["public_doc_paths"] = public_doc_paths
            observed["repo_profile"] = actual_repo_profile
            return {"required": False, "enabled": False, "digest": None}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "context.json"
            state_path = Path(temp_dir) / "state.json"
            args = mock.Mock(
                repo_root="C:/repo",
                output=str(output_path),
                profile="profile.json",
                full=True,
                since_ref=None,
                state_file=None,
            )
            with (
                mock.patch.object(collector, "parse_args", return_value=args),
                mock.patch.object(collector, "resolve_repo_root", return_value=Path("C:/repo")),
                mock.patch.object(collector, "resolve_profile_path", return_value=Path("C:/repo/profile.json")),
                mock.patch.object(collector, "load_repo_profile", return_value=profile),
                mock.patch.object(collector, "repo_identity", return_value=identity),
                mock.patch.object(collector, "default_state_file", return_value=state_path),
                mock.patch.object(collector, "git_head_commit", return_value="head-sha"),
                mock.patch.object(collector, "git_branch", return_value="develop"),
                mock.patch.object(collector, "collect_public_doc_paths", return_value=[]),
                mock.patch.object(collector, "build_baseline", return_value={"mode": "saved", "base_commit": None}),
                mock.patch.object(collector, "select_relevant_ref", return_value=(relevant_ref, [])),
                mock.patch.object(collector, "collect_status_paths", return_value=[]),
                mock.patch.object(collector, "collect_github_evidence", side_effect=fake_collect_github_evidence),
                mock.patch.object(collector, "build_evidence_summary", return_value={"artifact_count": 0, "comment_count": 0}),
                mock.patch.object(
                    collector,
                    "build_packet_candidates",
                    return_value={"forms_batch_packet": {"active": False, "direct_source_changes": []}},
                ),
                mock.patch.object(collector, "build_builder_compatibility", return_value={"status": "current"}),
                mock.patch.object(collector, "write_json"),
            ):
                self.assertEqual(collector.main(), 0)

        self.assertEqual(observed["repo_root"], Path("C:/repo"))
        self.assertIs(observed["identity"], identity)
        self.assertIs(observed["relevant_ref"], relevant_ref)
        self.assertEqual(observed["public_doc_paths"], [])
        self.assertIs(observed["repo_profile"], profile)

    def test_collect_github_evidence_fails_closed_when_required_slug_is_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc_info:
            collector.collect_github_evidence(
                Path("C:/repo"),
                {"repo_slug": ""},
                {"requires_github_evidence": True, "primary_pr_number": 1},
                [],
                {},
            )

        self.assertIn("repository slug could not be inferred", str(exc_info.exception))

    def test_collect_github_evidence_allows_missing_slug_when_not_required(self) -> None:
        evidence = collector.collect_github_evidence(
            Path("C:/repo"),
            {"repo_slug": ""},
            {"requires_github_evidence": False, "primary_pr_number": None},
            [],
            {},
        )

        self.assertFalse(evidence["required"])
        self.assertFalse(evidence["enabled"])
        self.assertIsNone(evidence["repo_slug"])


if __name__ == "__main__":
    unittest.main()
