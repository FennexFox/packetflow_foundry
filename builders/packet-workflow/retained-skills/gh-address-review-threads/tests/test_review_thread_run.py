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
from review_thread_test_support import context_with_threads, review_thread, write_json  # noqa: E402
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
                    "default_validation_commands": ["py -3 -m unittest tests/test_docs.py"],
                    "accepted_threads": [
                        {
                            "thread_id": "t-1",
                            "validation_commands": ["py -3 -m unittest tests/test_docs.py"],
                        }
                    ],
                },
            )

    def test_copy_validated_ack_plan_records_accepted_threads(self) -> None:
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
                        {"thread_id": "t-2", "decision": "defer", "ack_mode": "skip"},
                        {"thread_id": "t-1", "decision": "accept", "ack_mode": "add", "ack_body": "Will fix this."},
                    ],
                },
            )

            run_support.copy_validated_plan_into_manifest(
                manifest,
                phase="ack",
                source_path=validated_plan_path,
            )

            self.assertEqual(manifest["state"]["accepted_threads"], ["t-1"])
            self.assertTrue(Path(manifest["paths"]["ack"]["validated_plan"]).is_file())

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
            manifest["state"]["last_completed_phase"] = "ack-validated"
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
            manifest["state"]["last_completed_phase"] = "ack-validated"
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
