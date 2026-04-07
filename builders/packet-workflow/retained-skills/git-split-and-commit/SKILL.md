---
name: git-split-and-commit
description: Review the active repository's current working tree, split local changes into logical commits, draft repo-compliant commit messages, and commit automatically when confidence is high. Use when Codex needs to inspect staged, unstaged, and untracked non-ignored changes, decide whether they belong in one or more commits, and apply the commits safely with packetized evidence and targeted validation.
---

# Git Split And Commit

Use this skill to turn one working tree into logical commits with a guarded `collect -> build -> validate -> apply` flow.

## Use When

- the user wants the current local changes split into one or more clean commits
- packet evidence should guide the grouping, but final commit planning and git mutation must stay local
- hunk rematch, targeted checks, and rollback behavior need deterministic script enforcement

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python and reuse the same resolved interpreter for every helper script
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/git-split-and-commit/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/git-split-and-commit/<run-id>.json`

## Entry

1. Collect rules and worktree context, then build packets.
- Run `<python-bin> -B <skill-dir>/scripts/collect_commit_rules.py --repo <repo-root> --output <rules-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/collect_worktree_context.py --repo <repo-root> --output <worktree-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_commit_packets.py --rules <rules-json> --worktree <worktree-json> --output-dir <packet-dir> --result-output <build-result-json>`.
2. Initialize evaluation logging and read the runtime packets in order.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <worktree-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --phase build --result <build-result-json> --log <eval-log-json>`.
- Read `orchestrator.json` first, then `global_packet.json`, then `rules_packet.json` and `worktree_packet.json`, then at most one focused packet at a time on the common path.
3. Draft and validate the local commit plan.
- Draft `commit-plan.json` against `references/commit-plan-contract.md`.
- Run `<python-bin> -B <skill-dir>/scripts/validate_commit_plan.py --worktree <worktree-json> --plan <commit-plan-json> --output <validation-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/apply_commit_plan.py --worktree <worktree-json> --validation <validation-json> [--dry-run] --result-output <apply-result-json>` only after local review of the validator output.
4. If `orchestrator.json` sets a delegated review mode, follow `packet_worker_map` per focused packet and keep `apply_commit_plan.py` local.
5. Record validation/apply phase results and finalize the evaluation log before ending the run.

## Continue Only If

- final planning, staging, targeted checks, and `git commit` stay local
- `packet_worker_map` is the routing authority and worker output remains proposal-grade only
- apply consumes validator-normalized output only; it must not reinterpret stale hunk ownership
- review baselines, adjustments, worker recommendations, and similar observability fields stay build-result or eval-side unless a later runtime phase consumes them
- raw diff rereads happen only for an explicit allowed reason

## Stop When

- the worktree fingerprint or `HEAD` changed after collection
- another git operation is active
- a split stays ambiguous or rematch safety is too weak
- targeted checks are unavailable or fail
- confidence is too low to finalize a safe local plan

## Final Response

- say how many commit buckets the plan used and whether commits were applied or the run stopped
- name the blocker precisely, including the hard-stop category when available
- mention the targeted checks that actually ran

## References

- `references/commit-plan-contract.md`
- `references/delegation-playbook.md`
- `references/core-contract.md`
- `references/git-split-and-commit-evaluation-contract.md`
- `references/architecture-rationale.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_git_split_and_commit.py`
