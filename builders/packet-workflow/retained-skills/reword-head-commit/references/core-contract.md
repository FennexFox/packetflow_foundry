# Reword Head Commit Core Contract

`reword-head-commit` is an express retained skill for exactly one `HEAD`
commit.

Core rules:
- no packet build
- no subagents
- no temp-worktree replay
- no push side effects
- direct amend only after local validation succeeds
- repo-local temporary, helper, scratch, and ad hoc operator-input files stay under `.codex/tmp/`

Shared authority:
- commit-rule discovery stays aligned with
  `reword-recent-commits/scripts/collect_commit_rules.py`
- subject/type/scope/body validation stays aligned with
  `reword-recent-commits/scripts/reword_plan_contract.py`

Boundary:
- if the repo rules are only derived or fallback, stop and hand off to
  `reword-recent-commits`
- if more than one commit or any non-`HEAD` target is needed, use
  `reword-recent-commits`
- this skill is intentionally narrower than the full replay-based workflow
