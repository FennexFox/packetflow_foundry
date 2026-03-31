from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from reword_test_support import commit_file, load_json, make_repo, run_git

import reword_recent_commits  # type: ignore  # noqa: E402


class RewordWorkflowSmokeTests(unittest.TestCase):
    def seed_repo(self) -> tuple[object, Path]:
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
        return temp_dir, repo

    def run_driver(self, *args: str) -> tuple[int, dict]:
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["reword_recent_commits.py", *args]), contextlib.redirect_stdout(stdout):
            exit_code = reword_recent_commits.main()
        return exit_code, json.loads(stdout.getvalue())

    def test_end_to_end_driver_prepare_apply_and_eval(self) -> None:
        _temp_dir, repo = self.seed_repo()

        exit_code, prepare_summary = self.run_driver("--repo", str(repo), "--count", "2", "--prepare-only")

        self.assertEqual(exit_code, 0)
        self.assertEqual(prepare_summary["status"], "prepared")
        artifact_root = Path(prepare_summary["artifact_root"])
        template_path = Path(prepare_summary["message_template_path"])
        template = load_json(template_path)
        template["commits"][0]["new_message"] = "fix(core): rewrite seed"
        template["commits"][1]["new_message"] = "fix(parser): rewrite follow-up"
        template_path.write_text(json.dumps(template, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

        exit_code, apply_summary = self.run_driver("--repo", str(repo), "--messages-file", str(template_path), "--apply")

        self.assertEqual(exit_code, 0)
        self.assertEqual(apply_summary["status"], "ok")
        subjects = run_git(repo, "log", "-n", "2", "--reverse", "--format=%s").splitlines()
        self.assertEqual(subjects, ["fix(core): rewrite seed", "fix(parser): rewrite follow-up"])
        build_result = load_json(artifact_root / "build-result.json")
        final_log = load_json(Path(apply_summary["evaluation_log_path"]))
        apply_result = load_json(artifact_root / "apply-result.json")
        self.assertTrue(final_log["safety"]["apply_succeeded"])
        self.assertEqual(final_log["skill_specific"]["data"]["new_head"], apply_result["new_head"])
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
