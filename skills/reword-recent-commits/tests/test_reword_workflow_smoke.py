from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reword_test_support import commit_file, load_json, make_repo, run_git, write_json

import apply_reword_plan  # type: ignore  # noqa: E402
import build_reword_packets  # type: ignore  # noqa: E402
import collect_commit_rules  # type: ignore  # noqa: E402
import collect_recent_commits  # type: ignore  # noqa: E402
import validate_reword_plan  # type: ignore  # noqa: E402
import write_evaluation_log as eval_log  # type: ignore  # noqa: E402
from reword_plan_contract import build_context_fingerprint  # noqa: E402


class RewordWorkflowSmokeTests(unittest.TestCase):
    def test_end_to_end_collect_build_validate_apply_and_eval(self) -> None:
        temp_dir, repo = make_repo()
        self.addCleanup(temp_dir.cleanup)
        commit_file(
            repo,
            ".github/instructions/commit-message.instructions.md",
            "\n".join(
                [
                    "## Format",
                    "`<type>(<scope>): <subject>`",
                    "## Types",
                    "- `fix`",
                    "- `docs`",
                    "## Scopes",
                    "scope is required",
                    "## Subject Rules",
                    "72 characters or fewer",
                ]
            ),
            "docs(repo): add commit rules",
        )
        commit_file(repo, "src/a.py", "one\n", "fix(core): seed")
        commit_file(repo, "src/b.py", "two\n", "fix(parser): follow-up")

        rules = collect_commit_rules.build_rules(repo)
        context = collect_recent_commits.build_plan(repo, 2, rules)
        self.assertEqual(context["context_fingerprint"], build_context_fingerprint(context, rules))

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        rules_path = tmp_path / "rules.json"
        context_path = tmp_path / "context.json"
        raw_plan_path = tmp_path / "raw-plan.json"
        packet_dir = tmp_path / "packets"
        build_result_path = tmp_path / "build-result.json"
        validated_path = tmp_path / "validated.json"
        dry_run_path = tmp_path / "dry-run.json"
        apply_path = tmp_path / "apply.json"
        eval_log_path = tmp_path / "eval-log.json"
        final_path = tmp_path / "final.json"
        write_json(rules_path, rules)
        write_json(context_path, context)

        build_stdout = io.StringIO()
        build_argv = [
            "build_reword_packets.py",
            "--rules",
            str(rules_path),
            "--plan",
            str(context_path),
            "--output-dir",
            str(packet_dir),
            "--result-output",
            str(build_result_path),
        ]
        with mock.patch.object(sys, "argv", build_argv), contextlib.redirect_stdout(build_stdout):
            self.assertEqual(build_reword_packets.main(), 0)
        orchestrator = load_json(packet_dir / "orchestrator.json")
        build_result = load_json(build_result_path)
        self.assertEqual(orchestrator["context_fingerprint"], context["context_fingerprint"])
        self.assertTrue(build_result["common_path_sufficient"])
        self.assertEqual(build_result["raw_reread_reasons"], [])

        raw_plan = copy.deepcopy(context)
        raw_plan["commits"][0]["new_message"] = "fix(core): rewrite seed"
        raw_plan["commits"][1]["new_message"] = "fix(parser): rewrite follow-up"
        write_json(raw_plan_path, raw_plan)

        validate_stdout = io.StringIO()
        validate_argv = [
            "validate_reword_plan.py",
            "--rules",
            str(rules_path),
            "--context",
            str(context_path),
            "--plan",
            str(raw_plan_path),
            "--output",
            str(validated_path),
        ]
        with mock.patch.object(sys, "argv", validate_argv), contextlib.redirect_stdout(validate_stdout):
            self.assertEqual(validate_reword_plan.main(), 0)
        validated = load_json(validated_path)
        self.assertTrue(validated["valid"])

        init_argv = [
            "write_evaluation_log.py",
            "init",
            "--context",
            str(context_path),
            "--orchestrator",
            str(packet_dir / "orchestrator.json"),
            "--output",
            str(eval_log_path),
        ]
        with mock.patch.object(sys, "argv", init_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eval_log.main(), 0)

        phase_build_argv = [
            "write_evaluation_log.py",
            "phase",
            "--log",
            str(eval_log_path),
            "--phase",
            "build",
            "--result",
            str(build_result_path),
        ]
        with mock.patch.object(sys, "argv", phase_build_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eval_log.main(), 0)

        dry_run_argv = [
            "apply_reword_plan.py",
            "--context",
            str(context_path),
            "--plan",
            str(validated_path),
            "--dry-run",
            "--result-output",
            str(dry_run_path),
        ]
        with mock.patch.object(sys, "argv", dry_run_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(apply_reword_plan.main(), 0)

        apply_argv = [
            "apply_reword_plan.py",
            "--context",
            str(context_path),
            "--plan",
            str(validated_path),
            "--result-output",
            str(apply_path),
        ]
        with mock.patch.object(sys, "argv", apply_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(apply_reword_plan.main(), 0)

        phase_validate_argv = [
            "write_evaluation_log.py",
            "phase",
            "--log",
            str(eval_log_path),
            "--phase",
            "validate",
            "--result",
            str(validated_path),
        ]
        with mock.patch.object(sys, "argv", phase_validate_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eval_log.main(), 0)

        phase_apply_argv = [
            "write_evaluation_log.py",
            "phase",
            "--log",
            str(eval_log_path),
            "--phase",
            "apply",
            "--result",
            str(apply_path),
        ]
        with mock.patch.object(sys, "argv", phase_apply_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eval_log.main(), 0)

        write_json(
            final_path,
            {
                "quality": {
                    "first_pass_usable": True,
                    "human_post_edit_required": False,
                    "human_post_edit_severity": "none",
                }
            },
        )
        finalize_argv = [
            "write_evaluation_log.py",
            "finalize",
            "--log",
            str(eval_log_path),
            "--final",
            str(final_path),
        ]
        with mock.patch.object(sys, "argv", finalize_argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(eval_log.main(), 0)

        subjects = run_git(repo, "log", "-n", "2", "--reverse", "--format=%s").splitlines()
        self.assertEqual(subjects, ["fix(core): rewrite seed", "fix(parser): rewrite follow-up"])
        final_log = load_json(eval_log_path)
        self.assertTrue(final_log["safety"]["apply_succeeded"])
        self.assertEqual(final_log["skill_specific"]["data"]["new_head"], load_json(apply_path)["new_head"])
        self.assertEqual(final_log["skill_specific"]["data"]["packet_count"], build_result["packet_metrics"]["packet_count"])
        self.assertEqual(final_log["baseline"]["estimated_local_only_tokens"], build_result["packet_metrics"]["estimated_local_only_tokens"])
        self.assertTrue(final_log["skill_specific"]["data"]["common_path_sufficient"])

    def test_standalone_smoke_helper_prints_stable_summary_shape(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_reword_recent_commits.py"
        result = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            set(payload.keys()),
            {"status", "packet_metrics", "common_path_sufficient", "evaluation_log_path"},
        )
        self.assertEqual(payload["status"], "ok")
        self.assertIsInstance(payload["packet_metrics"], dict)
        self.assertIsInstance(payload["common_path_sufficient"], bool)
        self.assertTrue(Path(payload["evaluation_log_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
