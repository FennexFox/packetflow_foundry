---
name: reword-head-commit
description: Rewrite only the current HEAD commit message to the active repository's commit-message rules. Use when Codex needs a fast amend-based path for one clean HEAD commit with explicit repo guidance and no packet or replay audit requirements.
---

# Reword Head Commit

Use this skill as the narrow express path for rewriting the current `HEAD`
commit message without packet generation, subagents, or temp-worktree replay.

This workflow is intentionally narrow:
- reuse the same commit-rule discovery and validation contract as
  `reword-recent-commits`
- stop when the repo only has derived or fallback commit guidance
- validate locally, then amend `HEAD` directly with `git commit --amend`
- report when a later `git push --force-with-lease` is likely required
- keep push decisions outside this skill

Boundary:
- Keep reusable foundry semantics in `references/core-contract.md`.
- Keep this skill limited to one clean `HEAD` commit with explicit repo rules.
- Use `reword-recent-commits` for commit ranges, packet/audit needs, or
  replay-style safety.

## Decision Guide

- Use `reword-head-commit` when the target is exactly `HEAD`, the worktree is
  clean, repo guidance is explicit, and no packet/audit trail is needed.
- Use `reword-recent-commits` when `count > 1`, the target is not exactly
  `HEAD`, the repo rules are only derived or fallback, or replay-style safety
  is preferred over a direct amend.

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any
  helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python
  -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } |
  Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\
  python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then
  reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox,
  reuse that exact path inside the sandbox instead of calling `py` or bare
  `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter
  path.

## Workflow

1. Prepare the full replacement commit message.
- Keep the first line as the final subject.
- Add a blank line before any body or footer content.
- You may pass the message directly with `--message`.
- If you prefer `--message-file`, keep that file outside the tracked worktree
  or under `<repo-root>/.codex/tmp/packet-workflow/reword-head-commit/` so the
  repo stays clean.
- Any repo-local temporary, helper, or ad hoc input file for this workflow
  belongs under `<repo-root>/.codex/tmp/`.

2. Run the express driver.
- Run `<python-bin> -B <skill-dir>/scripts/reword_head_commit.py --repo <repo-root> --message <full-message>`.
- Or run `<python-bin> -B <skill-dir>/scripts/reword_head_commit.py --repo <repo-root> --message-file <repo-root>/.codex/tmp/packet-workflow/reword-head-commit/message.txt`.
- Add `--apply` only after confirmation. Without `--apply`, the driver stops
  after validation and writes a dry-run apply summary.
- Artifacts default to `<repo-root>/.codex/tmp/packet-workflow/reword-head-commit/<run-id>/`.

3. Validate before mutation.
- The driver reuses the same canonical rule discovery as
  `reword-recent-commits`.
- The driver reuses the same subject/type/scope/body validation contract as
  `reword-recent-commits`.
- The driver stops if repo rules are not explicit, the worktree is dirty,
  another git operation is active, `HEAD` is detached, `HEAD` is a merge
  commit, or `HEAD` is the root commit.

4. Apply only after confirmation.
- When `--apply` is present, the driver amends `HEAD` directly with
  `git commit --amend -F <message-file>`.
- The driver does not push. If the branch has an upstream, it reports that a
  later `git push --force-with-lease` is likely required.
- Validate the result with `git log -1 --format=fuller` and
  `git status --short --branch`.

## Scripts

- `scripts/reword_head_commit.py`
  - Driver for rule collection, HEAD context collection, validation, dry-run
    apply summaries, real amend, and evaluation-log writing.
- `scripts/smoke_reword_head_commit.py`
  - Run the temp-repo smoke path through the express driver and print a compact
    JSON summary.

## References

- Read `references/reword-head-commit-contract.md` for the express validation
  and apply envelope.
- Read `references/amend-safety.md` before changing the amend preconditions or
  branch-tip safety checks.
- Read `references/reword-head-commit-evaluation-contract.md` for the
  evaluation-log fields.

## Maintenance Notes

- Keep this skill intentionally narrower than `reword-recent-commits`.
- Reuse the full skill's rule collector and validator instead of forking new
  rule-discovery semantics here.
- Prefer `<python-bin> -B ...` so local verification does not leave fresh
  bytecode artifacts in the distributable skill folder.
- Keep distributable bundles free of `__pycache__/` directories and `.pyc`
  files.

## Safety

- Stop if repo commit-message rules are not explicit.
- Stop if the worktree is dirty.
- Stop if another git operation is already in progress.
- Stop if `HEAD` is detached, a merge commit, or the root commit.
- Do not apply the amend without explicit confirmation.
- Do not push automatically from this skill.
