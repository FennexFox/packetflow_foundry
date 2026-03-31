from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def run_command(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class GitSplitAndCommitIntegrationTests(unittest.TestCase):
    def init_repo(self, root: Path) -> None:
        run_command(["git", "init"], cwd=root)
        run_command(["git", "config", "user.name", "Codex Test"], cwd=root)
        run_command(["git", "config", "user.email", "codex@example.com"], cwd=root)

    def commit_all(self, root: Path, message: str) -> None:
        run_command(["git", "add", "--all"], cwd=root)
        run_command(["git", "commit", "-m", message], cwd=root)

    def script_path(self, name: str) -> str:
        return str(SCRIPTS_DIR / name)

    def test_smoke_collect_build_validate_and_apply_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            artifacts = tmp / "artifacts"
            repo.mkdir()
            artifacts.mkdir()
            self.init_repo(repo)

            write_text(
                repo / ".github" / "instructions" / "commit-message.instructions.md",
                "\n".join(
                    [
                        "## Format",
                        "- Use `<type>(<scope>): <subject>`.",
                        "",
                        "## Types",
                        "- `fix`",
                        "- `docs`",
                        "",
                        "## Scopes",
                        "- `core`",
                    ]
                )
                + "\n",
            )
            write_text(repo / "src" / "app.py", "print('before')\n")
            self.commit_all(repo, "fix(core): seed repo")

            write_text(repo / "src" / "app.py", "print('after')\n")

            rules_path = artifacts / "rules.json"
            worktree_path = artifacts / "worktree.json"
            packet_dir = artifacts / "packets"
            build_result_path = artifacts / "build-result.json"
            plan_path = artifacts / "commit-plan.json"
            validation_path = artifacts / "validation.json"
            apply_path = artifacts / "apply.json"

            run_command(
                [sys.executable, self.script_path("collect_commit_rules.py"), "--repo", str(repo), "--output", str(rules_path)],
                cwd=SKILL_ROOT,
            )
            run_command(
                [sys.executable, self.script_path("collect_worktree_context.py"), "--repo", str(repo), "--output", str(worktree_path)],
                cwd=SKILL_ROOT,
            )
            run_command(
                [
                    sys.executable,
                    self.script_path("build_commit_packets.py"),
                    "--rules",
                    str(rules_path),
                    "--worktree",
                    str(worktree_path),
                    "--output-dir",
                    str(packet_dir),
                    "--result-output",
                    str(build_result_path),
                ],
                cwd=SKILL_ROOT,
            )

            worktree = json.loads(worktree_path.read_text(encoding="utf-8"))
            plan = {
                "repo_root": worktree["repo_root"],
                "base_head": worktree["head_commit"],
                "worktree_fingerprint": worktree["worktree_fingerprint"],
                "input_scope": worktree["input_scope"],
                "overall_confidence": "high",
                "validation_commands": [],
                "omitted_paths": [],
                "stop_reasons": [],
                "commits": [
                    {
                        "commit_index": 1,
                        "intent_summary": "Update app output.",
                        "type": "fix",
                        "scope": "core",
                        "subject": "update app output",
                        "body": ["- update the tracked runtime file"],
                        "whole_file_paths": ["src/app.py"],
                        "untracked_paths": [],
                        "split_paths": [],
                        "selected_hunk_ids": [],
                        "supporting_paths": [],
                        "targeted_checks": [],
                        "confidence": "high",
                    }
                ],
            }
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

            validate_result = run_command(
                [
                    sys.executable,
                    self.script_path("validate_commit_plan.py"),
                    "--worktree",
                    str(worktree_path),
                    "--plan",
                    str(plan_path),
                    "--output",
                    str(validation_path),
                ],
                cwd=SKILL_ROOT,
            )
            self.assertEqual(validate_result.returncode, 0)

            apply_result = run_command(
                [
                    sys.executable,
                    self.script_path("apply_commit_plan.py"),
                    "--worktree",
                    str(worktree_path),
                    "--validation",
                    str(validation_path),
                    "--dry-run",
                    "--result-output",
                    str(apply_path),
                ],
                cwd=SKILL_ROOT,
            )
            payload = json.loads(apply_path.read_text(encoding="utf-8"))
            build_result = json.loads(build_result_path.read_text(encoding="utf-8"))
            self.assertEqual(apply_result.returncode, 0)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["apply_status"]["status"], "dry_run")
            self.assertEqual(payload["commits"][0]["subject"], "fix(core): update app output")
            self.assertEqual(payload["created_hashes"], [])
            self.assertTrue((packet_dir / "orchestrator.json").is_file())
            self.assertTrue((packet_dir / "packet_metrics.json").is_file())
            self.assertTrue(build_result["common_path_sufficient"])
            self.assertEqual(build_result["raw_reread_count"], 0)

    def test_apply_rolls_back_created_commits_and_preserves_worktree_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = tmp / "repo"
            artifacts = tmp / "artifacts"
            repo.mkdir()
            artifacts.mkdir()
            self.init_repo(repo)

            write_text(repo / "src" / "one.txt", "one\n")
            write_text(repo / "src" / "two.txt", "two\n")
            self.commit_all(repo, "fix(core): seed repo")
            original_head = run_command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

            write_text(repo / "src" / "one.txt", "one updated\n")
            write_text(repo / "src" / "two.txt", "two updated\n")

            hook_path = repo / ".git" / "hooks" / "pre-commit"
            write_text(
                hook_path,
                "\n".join(
                    [
                        "#!/bin/sh",
                        "for path in $(git diff --cached --name-only); do",
                        '  if [ \"$path\" = \"src/two.txt\" ]; then',
                        '    echo \"block second commit\" >&2',
                        "    exit 1",
                        "  fi",
                        "done",
                        "exit 0",
                    ]
                )
                + "\n",
            )
            try:
                os.chmod(hook_path, 0o755)
            except PermissionError:
                pass

            worktree_path = artifacts / "worktree.json"
            plan_path = artifacts / "commit-plan.json"
            validation_path = artifacts / "validation.json"
            apply_path = artifacts / "apply.json"

            run_command(
                [sys.executable, self.script_path("collect_worktree_context.py"), "--repo", str(repo), "--output", str(worktree_path)],
                cwd=SKILL_ROOT,
            )

            worktree = json.loads(worktree_path.read_text(encoding="utf-8"))
            plan = {
                "repo_root": worktree["repo_root"],
                "base_head": worktree["head_commit"],
                "worktree_fingerprint": worktree["worktree_fingerprint"],
                "input_scope": worktree["input_scope"],
                "overall_confidence": "high",
                "validation_commands": [],
                "omitted_paths": [],
                "stop_reasons": [],
                "commits": [
                    {
                        "commit_index": 1,
                        "intent_summary": "Update first file.",
                        "type": "fix",
                        "scope": "core",
                        "subject": "update first file",
                        "body": ["- update src/one.txt"],
                        "whole_file_paths": ["src/one.txt"],
                        "untracked_paths": [],
                        "split_paths": [],
                        "selected_hunk_ids": [],
                        "supporting_paths": [],
                        "targeted_checks": [],
                        "confidence": "high",
                    },
                    {
                        "commit_index": 2,
                        "intent_summary": "Update second file.",
                        "type": "fix",
                        "scope": "core",
                        "subject": "update second file",
                        "body": ["- update src/two.txt"],
                        "whole_file_paths": ["src/two.txt"],
                        "untracked_paths": [],
                        "split_paths": [],
                        "selected_hunk_ids": [],
                        "supporting_paths": [],
                        "targeted_checks": [],
                        "confidence": "high",
                    },
                ],
            }
            plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

            run_command(
                [
                    sys.executable,
                    self.script_path("validate_commit_plan.py"),
                    "--worktree",
                    str(worktree_path),
                    "--plan",
                    str(plan_path),
                    "--output",
                    str(validation_path),
                ],
                cwd=SKILL_ROOT,
            )

            apply_result = run_command(
                [
                    sys.executable,
                    self.script_path("apply_commit_plan.py"),
                    "--worktree",
                    str(worktree_path),
                    "--validation",
                    str(validation_path),
                    "--result-output",
                    str(apply_path),
                ],
                cwd=SKILL_ROOT,
                check=False,
            )
            payload = json.loads(apply_path.read_text(encoding="utf-8"))

            self.assertEqual(apply_result.returncode, 1)
            self.assertEqual(payload["apply_status"]["status"], "hard_stop")
            self.assertEqual(payload["apply_status"]["stop_category"], "commit_creation_failed")
            self.assertTrue(payload["apply_status"]["rollback_performed"])
            self.assertEqual(payload["apply_status"]["rollback_status"], "success")
            self.assertEqual(len(payload["created_hashes"]), 1)

            current_head = run_command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            unstaged = {
                line.strip()
                for line in run_command(["git", "diff", "--name-only"], cwd=repo).stdout.splitlines()
                if line.strip()
            }
            staged = {
                line.strip()
                for line in run_command(["git", "diff", "--cached", "--name-only"], cwd=repo).stdout.splitlines()
                if line.strip()
            }

            self.assertEqual(current_head, original_head)
            self.assertEqual(unstaged, {"src/one.txt", "src/two.txt"})
            self.assertEqual(staged, set())


if __name__ == "__main__":
    unittest.main()
