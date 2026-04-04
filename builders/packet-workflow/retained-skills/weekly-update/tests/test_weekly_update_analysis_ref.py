from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import weekly_update_lib as wl


def run_git(repo_root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env=merged_env,
    )
    return result.stdout.strip()


def write_profile(
    directory: Path,
    *,
    policy: str,
    preferred_branch_order: list[str] | None = None,
) -> Path:
    profile = json.loads(
        json.dumps(
            wl.load_repo_profile(wl.retained_default_repo_profile_path()),
            ensure_ascii=True,
        )
    )
    profile.setdefault("extra", {}).setdefault("weekly_update", {})["analysis_ref"] = {
        "policy": policy,
        "preferred_branch_order": list(preferred_branch_order or []),
    }
    profile_path = directory / f"profile-{policy}.json"
    profile_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return profile_path


class WeeklyUpdateAnalysisRefTests(unittest.TestCase):
    def init_detached_repo(self, repo_root: Path) -> dict[str, str]:
        repo_root.mkdir(parents=True, exist_ok=True)
        run_git(repo_root, "init")
        run_git(repo_root, "config", "user.name", "Codex Tests")
        run_git(repo_root, "config", "user.email", "codex-tests@example.invalid")

        note_path = repo_root / "note.txt"
        note_path.write_text("older worktree text\n", encoding="utf-8")
        run_git(repo_root, "add", "note.txt")
        base_env = {
            "GIT_AUTHOR_DATE": "2026-03-21T08:00:00Z",
            "GIT_COMMITTER_DATE": "2026-03-21T08:00:00Z",
        }
        run_git(repo_root, "commit", "-m", "base", env=base_env)
        base_sha = run_git(repo_root, "rev-parse", "HEAD")

        run_git(repo_root, "branch", "release-candidate", base_sha)
        run_git(repo_root, "checkout", "-b", "newer")
        note_path.write_text("newer branch text\n", encoding="utf-8")
        run_git(repo_root, "add", "note.txt")
        newer_env = {
            "GIT_AUTHOR_DATE": "2026-03-28T09:30:00Z",
            "GIT_COMMITTER_DATE": "2026-03-28T09:30:00Z",
        }
        run_git(repo_root, "commit", "-m", "newer", env=newer_env)
        newer_sha = run_git(repo_root, "rev-parse", "HEAD")

        run_git(repo_root, "checkout", "--detach", base_sha)
        return {"base_sha": base_sha, "newer_sha": newer_sha}

    def collect_context(
        self,
        repo_root: Path,
        *,
        profile_path: Path,
        state_file: Path | None = None,
        load_state_marker_result: tuple[dict[str, object] | None, list[str]] | None = None,
    ) -> dict[str, object]:
        with ExitStack() as stack:
            stack.enter_context(patch.object(wl, "verify_gh_auth", return_value=None))
            stack.enter_context(
                patch.object(
                    wl,
                    "get_repo_metadata",
                    return_value={
                        "repo_slug": "example/repo",
                        "default_branch": "master",
                        "repo_url": "https://example.invalid/repo",
                    },
                )
            )
            stack.enter_context(patch.object(wl, "list_releases", return_value=([], [])))
            stack.enter_context(patch.object(wl, "list_issues", return_value=([], [])))
            stack.enter_context(
                patch.object(wl, "list_merged_pr_summaries", return_value=([], []))
            )
            stack.enter_context(
                patch.object(wl, "list_workflow_runs", return_value=([], []))
            )
            if load_state_marker_result is not None:
                stack.enter_context(
                    patch.object(
                        wl,
                        "load_state_marker",
                        return_value=load_state_marker_result,
                    )
                )
            return wl.collect_context(
                repo_root=str(repo_root),
                profile=str(profile_path),
                state_file=str(state_file) if state_file is not None else None,
                now_utc="2026-03-29T12:00:00Z",
            )

    def test_collect_context_uses_freshest_local_branch_for_selected_ref_and_packets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "repo"
            commits = self.init_detached_repo(repo_root)
            profile_path = write_profile(
                temp_path,
                policy=wl.ANALYSIS_REF_POLICY_FRESHEST_LOCAL_BRANCH,
            )
            context = self.collect_context(
                repo_root,
                profile_path=profile_path,
                state_file=temp_path / "state.json",
            )

            self.assertEqual((repo_root / "note.txt").read_text(encoding="utf-8"), "older worktree text\n")
            self.assertEqual(context["analysis_ref"]["selected_branch"], "newer")
            self.assertEqual(context["analysis_ref"]["selected_ref"], "refs/heads/newer")
            self.assertEqual(context["analysis_ref"]["selected_sha"], commits["newer_sha"])
            self.assertEqual(context["workspace_branch_state"]["current_branch"], "HEAD")
            self.assertEqual(context["head_sha"], commits["newer_sha"])
            self.assertEqual(
                wl.read_text_at_ref(
                    repo_root,
                    str(context["analysis_ref"]["selected_sha"]),
                    "note.txt",
                ),
                "newer branch text\n",
            )
            self.assertTrue(
                any(
                    "Local git/file evidence is pinned" in note
                    for note in context["notes"]
                )
            )

            lint = wl.lint_context(context)
            packets = wl.build_packets(context, lint)
            self.assertEqual(
                packets["global_packet.json"]["analysis_ref"]["selected_branch"],
                "newer",
            )
            self.assertEqual(
                packets["mapping_packet.json"]["analysis_ref"]["selected_sha"],
                commits["newer_sha"],
            )

    def test_current_head_policy_preserves_detached_head_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "repo"
            commits = self.init_detached_repo(repo_root)
            profile_path = write_profile(
                temp_path,
                policy=wl.ANALYSIS_REF_POLICY_CURRENT_HEAD,
            )
            context = self.collect_context(
                repo_root,
                profile_path=profile_path,
                state_file=temp_path / "state.json",
            )

            self.assertEqual(context["analysis_ref"]["selected_ref"], "HEAD")
            self.assertIsNone(context["analysis_ref"]["selected_branch"])
            self.assertEqual(context["current_branch"], "HEAD")
            self.assertEqual(context["head_sha"], commits["base_sha"])
            self.assertEqual(
                context["analysis_ref"]["selected_sha"],
                commits["base_sha"],
            )

    def test_preferred_branch_order_beats_newer_commit_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "repo"
            commits = self.init_detached_repo(repo_root)
            profile_path = write_profile(
                temp_path,
                policy=wl.ANALYSIS_REF_POLICY_PREFERRED_BRANCH_ORDER,
                preferred_branch_order=["release-candidate", "newer"],
            )
            context = self.collect_context(
                repo_root,
                profile_path=profile_path,
                state_file=temp_path / "state.json",
            )

            self.assertEqual(context["analysis_ref"]["selected_branch"], "release-candidate")
            self.assertEqual(context["analysis_ref"]["selected_ref"], "refs/heads/release-candidate")
            self.assertEqual(context["analysis_ref"]["selected_sha"], commits["base_sha"])

    def test_canonical_analysis_ref_settings_treats_string_branch_order_as_single_entry(self) -> None:
        settings = wl.canonical_analysis_ref_settings(
            {
                "policy": wl.ANALYSIS_REF_POLICY_PREFERRED_BRANCH_ORDER,
                "preferred_branch_order": "refs/heads/release-candidate",
            }
        )

        self.assertEqual(settings["policy"], wl.ANALYSIS_REF_POLICY_PREFERRED_BRANCH_ORDER)
        self.assertEqual(settings["preferred_branch_order"], ["release-candidate"])

    def test_state_marker_identity_is_stable_across_worktree_paths_for_same_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "repo"
            commits = self.init_detached_repo(repo_root)
            linked_worktree = temp_path / "linked-worktree"
            run_git(
                repo_root,
                "worktree",
                "add",
                "--detach",
                str(linked_worktree),
                commits["base_sha"],
            )
            profile_current_head = write_profile(
                temp_path,
                policy=wl.ANALYSIS_REF_POLICY_CURRENT_HEAD,
            )
            context_main = self.collect_context(
                repo_root,
                profile_path=profile_current_head,
                load_state_marker_result=(None, []),
            )
            context_linked = self.collect_context(
                linked_worktree,
                profile_path=profile_current_head,
                load_state_marker_result=(None, []),
            )
            self.assertEqual(context_main["repo_hash"], context_linked["repo_hash"])
            self.assertEqual(context_main["state_file"], context_linked["state_file"])

            fresh_hash = wl.compute_repo_hash(
                repo_root,
                analysis_ref_settings={
                    "policy": wl.ANALYSIS_REF_POLICY_FRESHEST_LOCAL_BRANCH,
                    "preferred_branch_order": [],
                },
            )
            self.assertNotEqual(context_main["repo_hash"], fresh_hash)

    def test_state_marker_identity_ignores_preferred_branch_order_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_root = temp_path / "repo"
            self.init_detached_repo(repo_root)

            ordered_hash = wl.compute_repo_hash(
                repo_root,
                analysis_ref_settings={
                    "policy": wl.ANALYSIS_REF_POLICY_PREFERRED_BRANCH_ORDER,
                    "preferred_branch_order": ["release-candidate", "newer"],
                },
            )
            reordered_hash = wl.compute_repo_hash(
                repo_root,
                analysis_ref_settings={
                    "policy": wl.ANALYSIS_REF_POLICY_PREFERRED_BRANCH_ORDER,
                    "preferred_branch_order": ["newer"],
                },
            )

            self.assertEqual(ordered_hash, reordered_hash)

    def test_linked_worktree_reuses_main_worktree_legacy_state_marker_during_migration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            home_dir = temp_path / "home"
            home_dir.mkdir()
            repo_root = temp_path / "repo"
            commits = self.init_detached_repo(repo_root)
            linked_worktree = temp_path / "linked-worktree"
            run_git(
                repo_root,
                "worktree",
                "add",
                "--detach",
                str(linked_worktree),
                commits["base_sha"],
            )
            profile_current_head = write_profile(
                temp_path,
                policy=wl.ANALYSIS_REF_POLICY_CURRENT_HEAD,
            )
            legacy_marker = {"window_end_utc": "2026-03-20T12:00:00Z"}

            with patch.dict(os.environ, {"USERPROFILE": str(home_dir)}):
                main_legacy_path = wl.default_state_file(
                    wl.compute_legacy_repo_hash(repo_root),
                    namespace=wl.DEFAULT_STATE_NAMESPACE,
                )
                main_legacy_path.parent.mkdir(parents=True, exist_ok=True)
                main_legacy_path.write_text(
                    json.dumps(legacy_marker, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )

                context = self.collect_context(
                    linked_worktree,
                    profile_path=profile_current_head,
                )

            self.assertEqual(
                context["state_marker_source_file"],
                main_legacy_path.as_posix(),
            )
            self.assertNotEqual(
                context["state_file"],
                main_legacy_path.as_posix(),
            )
            self.assertEqual(context["reporting_window"]["source"], "state_marker")
            self.assertEqual(
                context["reporting_window"]["start_utc"],
                legacy_marker["window_end_utc"],
            )
            self.assertTrue(
                any(
                    "Reused a legacy weekly-update state marker" in note
                    for note in context["notes"]
                )
            )

if __name__ == "__main__":
    unittest.main()
