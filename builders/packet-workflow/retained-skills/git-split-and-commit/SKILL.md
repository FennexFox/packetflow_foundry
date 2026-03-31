---
name: git-split-and-commit
description: Review the active repository's current working tree, split local changes into logical commits, draft repo-compliant commit messages, and commit automatically when confidence is high. Use when Codex needs to inspect staged, unstaged, and untracked non-ignored changes, decide whether they belong in one or more commits, and apply the commits safely with packetized evidence and targeted validation.
---

# Git Split And Commit

Use this skill as the packet-driven orchestration layer for turning one working tree into logical commits.

This workflow follows the packet-workflow standard:
- collect context deterministically before reading raw diffs broadly
- build decision-ready packets and keep the final plan local
- treat worker output as proposal-grade only
- use `gpt-5.4-mini` only for narrow packet analysis when review mode says to delegate
- keep git mutation local and stop on low confidence or stale worktree state

Boundary:
- Keep reusable packet-workflow semantics in `references/core-contract.md`.
- Keep default repo bindings and review-doc ownership in `profiles/default/profile.json`.
- Keep vendored repo overrides data-only in `.codex/project/profiles/`.

Read `references/architecture-rationale.md` before changing packet metadata, delegation shape, or the default whole-file bias.

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } | Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox, reuse that exact path inside the sandbox instead of calling `py` or bare `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter path.
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/git-split-and-commit/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `~/.codex/tmp/evaluation_logs/git-split-and-commit/<run-id>.json` by default. If the sandbox blocks that path, use `<repo-root>/.codex/tmp/evaluation_logs/git-split-and-commit/<run-id>.json` as an explicit override and keep `.codex/tmp/` gitignored.

## Workflow

1. Collect rules and worktree context before planning commits.
- Write helper artifacts outside the repo root, preferably in a system temp directory.
- Run `<python-bin> -B <skill-dir>/scripts/collect_commit_rules.py --repo <repo-root> --output <rules-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/collect_worktree_context.py --repo <repo-root> --output <worktree-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_commit_packets.py --rules <rules-json> --worktree <worktree-json> --output-dir <packet-dir> --result-output <build-result-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <worktree-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>`.
- Merge the build result with `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --phase build --result <build-result-json> --log <eval-log-json>`.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading any focused packet.
- Read `rules_packet.json` and `worktree_packet.json` locally before drafting `commit-plan.json`.
- Treat `rules_packet.json + worktree_packet.json + one focused packet at a time` as the common path. Raw diff rereads are exception-only after packet generation.

2. Follow the review mode from `orchestrator.json`.
- `local-only`: keep commit planning local.
- `targeted-delegation`: use the routed mini workers for `rules_packet.json`, `worktree_packet.json`, `candidate-batch-XX.json`, or `split-file-XX.json`.
- `broad-delegation`: use the routed mini workers and add QA only when batches, split candidates, or findings conflict.
- Treat `packet_worker_map` as the routing authority and `preferred_worker_families` as explanatory metadata.
- Treat `task_packet_names` as basename-only packet metadata and `packet_order` as the file-oriented packet list.
- If `spawn_agent` is unavailable or fails, stay local on the same packet workflow.

3. Respect the decision-ready packet contract.
- `decision_ready_packets=true`
- `worker_return_contract=classification-oriented`
- `worker_output_shape=hierarchical`
- Workers return hierarchical `candidates[]` plus `footer`; their output is proposal-grade only.
- `candidate-batch-XX.json` packets describe logical commit buckets.
- `split-file-XX.json` packets describe files that may need a split decision.
- `candidate-batch-XX.json` and `split-file-XX.json` should be sufficient for common-path local adjudication; raw rereads stay exception-only after packet generation.

4. Keep the critical path local.
- Draft `commit-plan.json` locally using `references/commit-plan-contract.md`.
- Re-check the rules and worktree packets locally before finalizing the plan.
- Prefer whole-file commits unless a split-file packet clearly justifies a split.
- Stop and ask when hunk confidence is low, the worktree fingerprint changed, a split packet stays ambiguous, or targeted checks cannot run locally.
- If packet evidence is insufficient, record an explicit reread reason instead of silently falling back to the raw diff.
- Validate `commit-plan.json` before running `apply_commit_plan.py`.
- Treat `validate_commit_plan.py` as the only source of `normalized_plan` for apply and `--dry-run`.
- Run `apply_commit_plan.py --validation <validation-json>` only after the validator emits a current, apply-safe normalized plan.

## Delegation Rules

- Pass `global_packet.json` plus one focused packet per worker.
- Keep workers narrow and read-only.
- Prefer these roles:
  - `docs_verifier` for `rules_packet.json`
  - `repo_mapper` for `worktree_packet.json`
  - `evidence_summarizer` for `candidate-batch-XX.json`
  - `large_diff_auditor` for `split-file-XX.json` and any QA pass
- Require hierarchical proposal output from each worker:
  - `candidates[]`
  - `footer`
  - `fact_summary`
  - `proposal_classification`
- `classification_rationale`
- `supporting_references`
- `ambiguity`
- `confidence`
- `reread_control`
- Current domain aliases assume file/path-oriented evidence first, so `supporting_paths` should stay path-shaped unless the contract is deliberately expanded.
- Read `references/delegation-playbook.md` when `review_mode` is not `local-only`.

## Scripts

- `scripts/collect_commit_rules.py`
  - Collect canonical commit-message rules, repo defaults, and recent scope vocabulary.
- `scripts/collect_worktree_context.py`
  - Collect the current working-tree surface, fingerprint, hunk candidates, and validation commands.
- `scripts/build_commit_packets.py`
  - Build `global_packet.json`, `rules_packet.json`, `worktree_packet.json`, the candidate batches, the split-file packets, `packet_metrics.json`, and orchestrator metadata plus an optional build-result artifact.
- `scripts/validate_commit_plan.py`
  - Validate coverage, active git operations, hunk uniqueness, split safety, targeted-check feasibility, unknown-field handling, and worktree fingerprint consistency, then emit the normalized plan and stop categories that apply consumes.
- `scripts/apply_commit_plan.py`
  - Consume validator output only, re-stage each planned commit, run targeted checks, create commits, emit structured hard-stop payloads, and roll created commits back to the original HEAD with worktree edits preserved when a later apply step fails.
- `scripts/write_evaluation_log.py`
  - Record the shared evaluation log for efficiency, quality, and safety tracking, including build-phase packet metrics and common-path sufficiency.

- `scripts/smoke_git_split_and_commit.py`
  - Run the temp-repo smoke path for collect -> build -> validate -> apply `--dry-run` -> evaluation logging.

## Evaluation

- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <worktree-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>` after packet generation.
- Merge deterministic phase results with `phase` after validation or apply.
- Finalize the evaluation log after the run with worker usage, packet usage, confidence, validation status, and any stop reasons.
- Keep the evaluation log at the contract-default outside-repo path unless you intentionally need the gitignored `.codex/tmp/` fallback.
- Read `references/evaluation-log-contract.md` for the shared envelope and `references/git-split-and-commit-evaluation-contract.md` for commit-planning-specific fields.

## Maintenance Notes

- Prefer `<python-bin> -B ...` when running bundled scripts so local verification does not leave fresh bytecode artifacts in the distributable skill folder.
- Keep distributable bundles free of `__pycache__/` directories and `.pyc` files.
- Re-read `references/architecture-rationale.md` before changing the orchestrator profile, worker families, or whole-file/split defaults.

## Output

- Tell the user how many commit buckets the current plan uses and why.
- Tell the user whether the skill applied commits or stopped at validation.
- If the skill stopped, name the blocker precisely with the hard-stop category when available.
- Local hard-stop categories include `active_git_operation`, `ambiguous_split_rematch`, `partial_split_unsupported`, `targeted_check_unavailable`, `targeted_check_failed`, `commit_creation_failed`, and `rollback_failed`.
