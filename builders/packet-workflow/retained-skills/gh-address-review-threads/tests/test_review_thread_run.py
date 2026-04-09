from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent / "scripts"
for candidate in (str(TEST_DIR), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import review_thread_run as run_support  # type: ignore  # noqa: E402
import manage_review_thread_run as manage_run  # type: ignore  # noqa: E402
from review_thread_test_support import ack_reply_body, context_with_threads, review_thread, write_json  # noqa: E402
from thread_action_contract import build_context_fingerprint  # type: ignore  # noqa: E402


def init_repo(repo_root: Path) -> None:
    commands = [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "Codex"],
        ["git", "config", "user.email", "codex@example.com"],
        ["git", "add", "."],
        ["git", "commit", "--no-gpg-sign", "-m", "test: seed repo"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=str(repo_root),
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git command failed")


class ReviewThreadRunTests(unittest.TestCase):
    def test_create_run_writes_manifest_pre_context_and_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            source_context_path = tmp / "input-context.json"
            write_json(source_context_path, context)

            manifest = run_support.create_run(
                repo_root,
                source_context_path,
                run_id="test-run-a",
                evaluation_log_path=tmp / "eval-log.json",
            )

            manifest_path = Path(manifest["paths"]["manifest"])
            pre_context_path = Path(manifest["paths"]["pre"]["context"])
            latest_path = run_support.latest_pointer_path(repo_root)

            self.assertTrue(manifest_path.is_file())
            self.assertTrue(pre_context_path.is_file())
            self.assertTrue(latest_path.is_file())
            self.assertEqual(json.loads(pre_context_path.read_text(encoding="utf-8"))["context_fingerprint"], context["context_fingerprint"])
            self.assertEqual(manifest["state"]["pre_ack_worktree"]["entries"], [])
            self.assertTrue(str(manifest["state"]["pre_ack_worktree"].get("content_fingerprint") or "").startswith("sha256:"))
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(latest["run_id"], "test-run-a")
            self.assertEqual(latest["manifest_path"], manifest["paths"]["manifest"])

            second_manifest = run_support.create_run(
                repo_root,
                source_context_path,
                run_id="test-run-b",
                evaluation_log_path=tmp / "eval-log-2.json",
            )
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(latest["run_id"], "test-run-b")
            self.assertTrue(Path(second_manifest["paths"]["manifest"]).is_file())
            self.assertTrue(pre_context_path.is_file())

    def test_post_push_staging_keeps_pre_context_and_builds_reconciliation_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            pre_context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            post_context = json.loads(json.dumps(pre_context))
            post_context["threads"][0]["is_outdated"] = True
            pre_context["context_fingerprint"] = build_context_fingerprint(pre_context)
            post_context["context_fingerprint"] = build_context_fingerprint(post_context)
            repo_root = Path(pre_context["repo_root"])
            init_repo(repo_root)

            pre_source_path = tmp / "pre-context.json"
            post_source_path = tmp / "post-context.json"
            write_json(pre_source_path, pre_context)
            write_json(post_source_path, post_context)

            manifest = run_support.create_run(
                repo_root,
                pre_source_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            run_support.set_accepted_threads(manifest, ["t-1"])
            run_support.set_validation_commands(manifest, ["py -3 -m unittest tests/test_docs.py"])
            run_support.copy_context_into_manifest(
                manifest,
                phase="post",
                source_path=post_source_path,
            )
            reconciliation = run_support.write_reconciliation_input(manifest)

            pre_staged = json.loads(Path(manifest["paths"]["pre"]["context"]).read_text(encoding="utf-8"))
            post_staged = json.loads(Path(manifest["paths"]["post"]["context"]).read_text(encoding="utf-8"))

            self.assertEqual(pre_staged["context_fingerprint"], pre_context["context_fingerprint"])
            self.assertEqual(post_staged["context_fingerprint"], post_context["context_fingerprint"])
            self.assertEqual(
                reconciliation,
                {
                    "pre_push_head_sha": manifest["git"]["pre_push_head_sha"],
                    "post_push_head_sha": manifest["git"]["post_push_head_sha"],
                    "default_validation_commands": ["py -3 -m unittest tests/test_docs.py"],
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["py -3 -m unittest tests/test_docs.py"],
                        }
                    ],
                },
            )

    def test_copy_validated_ack_plan_keeps_pre_ack_decisions_out_of_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    ),
                    review_thread(
                        thread_id="t-2",
                        path="src/helper.py",
                        line=20,
                        reviewer_login="reviewer-b",
                        reviewer_body="Please add a test.",
                    ),
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            source_context_path = tmp / "context.json"
            write_json(source_context_path, context)
            manifest = run_support.create_run(
                repo_root,
                source_context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            validated_plan_path = tmp / "ack-plan.json"
            write_json(
                validated_plan_path,
                {
                    "phase": "ack",
                    "valid": True,
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-2",
                            "decision": "defer",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(
                                decision="defer",
                                detail="Deferring until packet-local evidence is re-grounded.",
                            ),
                        },
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        },
                    ],
                },
            )

            run_support.copy_validated_plan_into_manifest(
                manifest,
                phase="ack",
                source_path=validated_plan_path,
            )

            self.assertEqual(manifest["state"]["accepted_threads"], [])
            self.assertEqual(manifest["state"]["last_completed_phase"], "ack-validated")
            self.assertTrue(Path(manifest["paths"]["ack"]["validated_plan"]).is_file())

    def test_record_ack_plan_rejects_pre_ack_worktree_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            validated_plan_path = tmp / "ack-plan.json"
            write_json(context_path, context)
            write_json(
                validated_plan_path,
                {
                    "phase": "ack",
                    "valid": True,
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            (repo_root / "src" / "app.py").write_text("one\ntwo\nthree\nfour\nfive\nsix\n", encoding="utf-8")

            argv = [
                "manage_review_thread_run.py",
                "record-plan",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--validated-plan",
                str(validated_plan_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-plan --phase ack blocked because the git worktree changed after run start and before ack-applied",
                ):
                    manage_run.main()

    def test_record_ack_plan_rejects_content_drift_when_status_entry_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            tracked_path = repo_root / "src" / "app.py"
            tracked_path.parent.mkdir(parents=True, exist_ok=True)
            tracked_path.write_text("baseline\n", encoding="utf-8")
            init_repo(repo_root)
            tracked_path.write_text("dirty-before-run\n", encoding="utf-8")

            context_path = tmp / "context.json"
            validated_plan_path = tmp / "ack-plan.json"
            write_json(context_path, context)
            write_json(
                validated_plan_path,
                {
                    "phase": "ack",
                    "valid": True,
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            tracked_path.write_text("dirty-after-run\n", encoding="utf-8")

            argv = [
                "manage_review_thread_run.py",
                "record-plan",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--validated-plan",
                str(validated_plan_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "content-sensitive comparison detected additional edits to already-dirty paths",
                ):
                    manage_run.main()

    def test_record_ack_plan_requires_pre_ack_manifest_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            validated_plan_path = tmp / "ack-plan.json"
            write_json(context_path, context)
            write_json(
                validated_plan_path,
                {
                    "phase": "ack",
                    "valid": True,
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-applied"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-plan",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--validated-plan",
                str(validated_plan_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-plan --phase ack requires manifest state",
                ):
                    manage_run.main()

    def test_record_apply_cli_records_phase_result_and_advances_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            result_path = tmp / "ack-result.json"
            write_json(context_path, context)
            write_json(
                result_path,
                {
                    "phase": "ack",
                    "dry_run": False,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "context_fingerprint": "updated-fingerprint",
                    "mutation_type": "add_reply",
                    "mutations": [{"kind": "add_reply", "thread_id": "t-1", "phase": "ack"}],
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )

            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-apply",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--result",
                str(result_path),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(manage_run.main(), 0)

            updated = run_support.load_manifest(manifest_path)
            self.assertEqual(updated["state"]["last_completed_phase"], "ack-applied")
            self.assertEqual(updated["state"]["latest_context_fingerprint"], "updated-fingerprint")
            self.assertEqual(updated["state"]["accepted_threads"], ["t-1"])
            self.assertEqual(
                updated["state"]["phase_apply_results"]["ack"],
                {
                    "dry_run": False,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "mutation_type": "add_reply",
                    "mutation_count": 1,
                    "result_path": updated["paths"]["ack"]["result"],
                },
            )

    def test_record_ack_apply_rejects_pre_ack_worktree_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            result_path = tmp / "ack-result.json"
            write_json(context_path, context)
            write_json(
                result_path,
                {
                    "phase": "ack",
                    "dry_run": False,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "context_fingerprint": "updated-fingerprint",
                    "mutation_type": "add_reply",
                    "mutations": [{"kind": "add_reply", "thread_id": "t-1", "phase": "ack"}],
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )

            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)
            (repo_root / "src" / "app.py").write_text("one\ntwo\nthree\nfour\nfive\nsix\n", encoding="utf-8")

            argv = [
                "manage_review_thread_run.py",
                "record-apply",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--result",
                str(result_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-apply --phase ack blocked because the git worktree changed after run start and before ack-applied",
                ):
                    manage_run.main()

    def test_record_ack_apply_rejects_content_drift_when_status_entry_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            tracked_path = repo_root / "src" / "app.py"
            tracked_path.parent.mkdir(parents=True, exist_ok=True)
            tracked_path.write_text("baseline\n", encoding="utf-8")
            init_repo(repo_root)
            tracked_path.write_text("dirty-before-run\n", encoding="utf-8")

            context_path = tmp / "context.json"
            result_path = tmp / "ack-result.json"
            write_json(context_path, context)
            write_json(
                result_path,
                {
                    "phase": "ack",
                    "dry_run": False,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "context_fingerprint": "updated-fingerprint",
                    "mutation_type": "add_reply",
                    "mutations": [{"kind": "add_reply", "thread_id": "t-1", "phase": "ack"}],
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "ack_mode": "add",
                            "ack_body": ack_reply_body(decision="accept", detail="Will fix this."),
                        }
                    ],
                },
            )

            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)
            tracked_path.write_text("dirty-after-run\n", encoding="utf-8")

            argv = [
                "manage_review_thread_run.py",
                "record-apply",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--result",
                str(result_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "content-sensitive comparison detected additional edits to already-dirty paths",
                ):
                    manage_run.main()

    def test_record_apply_rejects_dry_run_live_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            result_path = tmp / "ack-result.json"
            write_json(context_path, context)
            write_json(
                result_path,
                {
                    "phase": "ack",
                    "dry_run": True,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "mutations": [],
                },
            )

            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-apply",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--result",
                str(result_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "ack apply result must be non-dry-run",
                ):
                    manage_run.main()

    def test_record_apply_allows_dry_run_when_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            result_path = tmp / "ack-result.json"
            write_json(context_path, context)
            write_json(
                result_path,
                {
                    "phase": "ack",
                    "dry_run": True,
                    "apply_succeeded": True,
                    "fingerprint_match": True,
                    "context_fingerprint": "updated-fingerprint",
                    "mutation_type": "add_reply",
                    "mutations": [],
                },
            )

            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-apply",
                "--manifest",
                str(manifest_path),
                "--phase",
                "ack",
                "--result",
                str(result_path),
                "--allow-dry-run",
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(manage_run.main(), 0)

            updated = run_support.load_manifest(manifest_path)
            self.assertEqual(updated["state"]["last_completed_phase"], "ack-applied")
            self.assertTrue(updated["state"]["phase_apply_results"]["ack"]["dry_run"])

    def test_post_push_requires_recorded_validation_commands_when_threads_were_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            pre_context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            post_context = json.loads(json.dumps(pre_context))
            pre_context["context_fingerprint"] = build_context_fingerprint(pre_context)
            post_context["context_fingerprint"] = build_context_fingerprint(post_context)
            repo_root = Path(pre_context["repo_root"])
            init_repo(repo_root)

            pre_source_path = tmp / "pre-context.json"
            post_source_path = tmp / "post-context.json"
            write_json(pre_source_path, pre_context)
            write_json(post_source_path, post_context)

            manifest = run_support.create_run(
                repo_root,
                pre_source_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["accepted_threads"] = ["t-1"]
            manifest["state"]["last_completed_phase"] = "ack-applied"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "post-push",
                "--manifest",
                str(manifest_path),
                "--context",
                str(post_source_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "post-push requires recorded validation commands",
                ):
                    manage_run.main()

    def test_record_validation_cli_keeps_subcommand_and_commands_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            write_json(context_path, context)
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-applied"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-validation",
                "--manifest",
                str(manifest_path),
                "--validation-command",
                "py -3 -m unittest tests/test_docs.py",
                "--command",
                "py -3 -m unittest tests/test_more.py",
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(manage_run.main(), 0)

            updated = run_support.load_manifest(manifest_path)
            self.assertEqual(updated["state"]["validation_commands"], [
                "py -3 -m unittest tests/test_docs.py",
                "py -3 -m unittest tests/test_more.py",
            ])

    def test_record_accepts_requires_ack_applied_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            write_json(context_path, context)
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-accepts",
                "--manifest",
                str(manifest_path),
                "--thread-id",
                "t-1",
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-accepts requires manifest state in \\{ack-applied\\}",
                ):
                    manage_run.main()

    def test_record_validation_requires_ack_applied_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            write_json(context_path, context)
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-validation",
                "--manifest",
                str(manifest_path),
                "--validation-command",
                "py -3 -m unittest tests/test_docs.py",
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-validation requires manifest state in \\{ack-applied\\}",
                ):
                    manage_run.main()

    def test_record_complete_plan_requires_post_prepared_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            context = context_with_threads(
                tmp,
                [
                    review_thread(
                        thread_id="t-1",
                        path="src/app.py",
                        line=10,
                        reviewer_login="reviewer-a",
                        reviewer_body="Please rename this.",
                    )
                ],
            )
            context["context_fingerprint"] = build_context_fingerprint(context)
            repo_root = Path(context["repo_root"])
            init_repo(repo_root)

            context_path = tmp / "context.json"
            validated_plan_path = tmp / "complete-plan.json"
            write_json(context_path, context)
            write_json(
                validated_plan_path,
                {
                    "phase": "complete",
                    "valid": True,
                    "normalized_thread_actions": [
                        {
                            "thread_id": "t-1",
                            "decision": "accept",
                            "complete_mode": "add",
                            "complete_body": "Done.",
                            "resolve_after_complete": True,
                        }
                    ],
                },
            )
            manifest = run_support.create_run(
                repo_root,
                context_path,
                run_id="test-run",
                evaluation_log_path=tmp / "eval-log.json",
            )
            manifest_path = Path(manifest["paths"]["manifest"])
            manifest["state"]["last_completed_phase"] = "ack-validated"
            run_support.write_manifest(manifest_path, manifest)

            argv = [
                "manage_review_thread_run.py",
                "record-plan",
                "--manifest",
                str(manifest_path),
                "--phase",
                "complete",
                "--validated-plan",
                str(validated_plan_path),
            ]
            with patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "record-plan --phase complete requires manifest state",
                ):
                    manage_run.main()


if __name__ == "__main__":
    unittest.main()
