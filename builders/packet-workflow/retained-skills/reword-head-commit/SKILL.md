---
name: reword-head-commit
description: Rewrite only the current HEAD commit message to the active repository's commit-message rules. Use when Codex needs a fast amend-based path for one clean HEAD commit with explicit repo guidance and no packet or replay audit requirements.
---

# Reword Head Commit

Use this skill for the narrow express path that validates one replacement message and amends `HEAD` directly.

## Use When

- the target is exactly `HEAD`
- the worktree is clean and repo commit-message rules are explicit
- packet generation or replay-style history rewriting would be unnecessary overhead

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python and reuse the same resolved interpreter path for the whole run
- `<artifact-root>`: `<repo-root>/.codex/tmp/packet-workflow/reword-head-commit/<run-id>/`

## Entry

1. Prepare the full replacement message.
- Pass it directly with `--message`, or store it under `<repo-root>/.codex/tmp/packet-workflow/reword-head-commit/` and use `--message-file`.
2. Run the express driver.
- Run `<python-bin> -B <skill-dir>/scripts/reword_head_commit.py --repo <repo-root> --message <full-message>`.
- Or run `<python-bin> -B <skill-dir>/scripts/reword_head_commit.py --repo <repo-root> --message-file <message-path>`.
- Add `--apply` only after confirmation. Without `--apply`, the driver stops after validation and writes a dry-run apply summary.
3. Use the emitted validation/apply artifacts to report the outcome; keep any later push decision outside this skill.

## Continue Only If

- repo commit-message rules are explicit enough for the express path
- the worktree is clean, `HEAD` is attached, no git operation is active, and `HEAD` is neither a merge commit nor the root commit
- the amend stays local and no push is attempted from this workflow
- the express path keeps using the shared reword validation contract instead of inventing a separate rule parser

## Stop When

- repo rules are derived or fallback-only
- the worktree is dirty or another git operation is active
- `HEAD` is detached, a merge commit, or the root commit
- the replacement message fails validation

## Final Response

- say whether validation blocked the run or the amend succeeded
- include the new head when the amend ran
- name the blocker precisely when the run stops
- mention whether a later force-push is likely

## References

- `references/reword-head-commit-contract.md`
- `references/amend-safety.md`
- `references/core-contract.md`
- `references/reword-head-commit-evaluation-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_reword_head_commit.py`
