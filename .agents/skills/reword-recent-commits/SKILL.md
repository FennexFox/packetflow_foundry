---
name: reword-recent-commits
description: Rewrite or reword the latest n Git commit messages to the active repository's commit-message rules. Use when Codex needs to inspect repo-specific commit guidance, draft replacement commit messages for recent local commits, and optionally apply the rewrite safely without hand-driving an interactive rebase. Keep orchestration, final message synthesis, confirmation, and ref updates local while offloading narrow read-only packet analysis to gpt-5.4-mini workers when the rewrite spans multiple commits or areas.
---

# Reword Recent Commits

Use this skill as the packet-driven orchestration layer for rewriting recent commit messages against the repository's own rules.

This workflow follows the packet-workflow standard:
- collect rules and commit history deterministically before drafting replacements
- build flat packets and keep final message synthesis local
- treat worker output as proposal-grade only
- use `gpt-5.4-mini` only for narrow packet analysis when review mode says to delegate
- keep ref updates local and stop on low confidence or rewrite safety blockers

Boundary:
- Keep reusable packet-workflow semantics in `references/core-contract.md`.
- Keep default repo bindings and review-doc ownership in `profiles/default/profile.json`.
- Keep vendored repo overrides data-only in `.codex/project/profiles/`.

Read `references/architecture-note.md` before changing the packet/result model or the flat/generic contract.

## Workflow

1. Collect artifacts before drafting messages.
- Run `<python-bin> -B <skill-dir>/scripts/collect_commit_rules.py --repo <repo-root> --output <rules-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/collect_recent_commits.py --count <n> --repo <repo-root> --rules <rules-json> --output <plan-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_reword_packets.py --rules <rules-json> --plan <plan-json> --output-dir <packet-dir> --result-output <build-result-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <plan-json> --orchestrator <packet-dir>/orchestrator.json --output <packet-dir>/eval-log.json`.
- Merge the build result with `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --phase build --result <build-result-json> --log <eval-log-json>`.
- Draft a raw plan by filling `commits[*].new_message` in a copy of `<plan-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/validate_reword_plan.py --rules <rules-json> --context <plan-json> --plan <raw-plan-json> --output <validated-json>`.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading any focused packet.
- Read `rules_packet.json` locally before drafting, then keep `rules_packet.json + one commit packet at a time` as the common path.
- Re-check `rules_packet.json` immediately before confirming the final replacement messages.

2. Follow the review mode from `orchestrator.json`.
- `local-only`: keep the rewrite fully local.
- `targeted-delegation`: use the routed mini workers for `rules_packet.json` and the commit packets.
- `broad-delegation`: use the routed mini workers and add QA only when findings conflict or the rewrite spans many areas.
- Treat `packet_worker_map` as the routing authority and `preferred_worker_families` as explanatory metadata.
- This pass is a metadata/doc refresh. Keep the current `task_packet_names` and `task_packet_ids` shapes; naming migration is intentionally out of scope.
- If `spawn_agent` is unavailable or fails, stay local on the same packet workflow.

3. Respect the flat packet contract.
- `decision_ready_packets=false`
- `worker_return_contract=generic`
- `worker_output_shape=flat`
- Workers return proposal-grade summaries only.
- `commit-XX.json` packets summarize one commit at a time.
- Raw rereads stay exception-only after packet generation.
- `raw_reread_reasons` must use the enum from `scripts/reword_plan_contract.py`.

4. Keep the critical path local.
- Draft the replacement messages yourself, in oldest-to-newest order.
- Show the proposed messages to the user and confirm immediately before rewriting history.
- Run `apply_reword_plan.py` only after confirmation and only with the validated envelope.
- Validate the result with `git log -n <n> --format=fuller` and `git status --short --branch`.
- Stop before applying if the branch tip moved, a merge commit appears in scope, `base_commit` is null, the worktree is dirty, or another git operation is already in progress.

## Delegation Rules

- Pass `global_packet.json` plus one focused packet per worker.
- Keep workers narrow and read-only.
- Prefer these roles:
  - `docs_verifier` for `rules_packet.json`
  - `repo_mapper` for rewrite-scope and blocker checks when helpful
  - `evidence_summarizer` for `commit-XX.json`
  - `large_diff_auditor` for any QA pass
- Require flat proposal output from each worker:
  - `commit indexes`
  - `primary intent`
  - `suggested type/scope`
  - `body needed`
  - `evidence files`
  - `ambiguity`
  - `confidence`
  - `reread_control`
- Read `references/delegation-playbook.md` when `review_mode` is not `local-only`.
- Read `references/architecture-note.md` before changing the packet/result model.

## Scripts

- `scripts/collect_commit_rules.py`
  - Collect canonical commit-message rules, repo defaults, recent scope vocabulary, and source paths.
- `scripts/collect_recent_commits.py`
  - Collect the recent target commits into a rewrite plan file in oldest-to-newest order and attach the canonical `context_fingerprint`.
- `scripts/build_reword_packets.py`
  - Build `global_packet.json`, `rules_packet.json`, the commit packets, `packet_metrics.json`, orchestrator metadata, and an optional build-result artifact.
- `scripts/validate_reword_plan.py`
  - Validate drafted `new_message` values, normalize the rewrite order, and emit the canonical apply envelope.
- `scripts/apply_reword_plan.py`
  - Replay the selected commits in a temporary worktree and move the branch ref only if the validated envelope still matches the current context.
- `scripts/write_evaluation_log.py`
  - Record the shared evaluation log for efficiency, quality, and safety tracking.
- `scripts/reword_plan_contract.py`
  - Shared source of truth for fingerprints, builder metadata, reread reasons, packet metrics, validation codes, stop categories, and normalized rewrite ordering.
- `scripts/smoke_reword_recent_commits.py`
  - Run the temp-repo smoke path for collect -> build -> eval build -> validate -> apply `--dry-run` -> eval apply and print a compact JSON summary.

## Evaluation

- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <plan-json> --orchestrator <packet-dir>/orchestrator.json --output <packet-dir>/eval-log.json` after packet generation.
- Merge deterministic build, validation, and apply results with `phase`.
- Finalize the evaluation log after the run with worker usage, packet usage, confidence, branch-update status, and any stop reasons.
- Read `references/evaluation-log-contract.md` for the shared envelope, `references/reword-recent-commits-contract.md` for the rewrite-plan contract, and `references/reword-recent-commits-evaluation-contract.md` for rewrite-specific fields.

## Maintenance Notes

- Prefer `<python-bin> -B ...` when running bundled scripts so local verification does not leave fresh bytecode artifacts in the distributable skill folder.
- Keep distributable bundles free of `__pycache__/` directories and `.pyc` files.
- Re-read `references/architecture-note.md` before changing the flat/generic contract or expanding this skill into a naming-migration pass.

## Safety

- Stop if a target commit is a merge commit.
- Stop if another git operation is already in progress.
- Stop if `base_commit` is null. Root-commit rewrites remain out of scope for this skill.
- Stop if the worktree is dirty.
- Do not apply the rewrite without explicit confirmation.
- Do not hand-drive interactive rebase when the plan/apply scripts are sufficient.
- Read `references/rule-discovery.md` when the repo rules are unclear.
- Read `references/history-rewrite-safety.md` when the branch is shared, upstream divergence matters, or the replay script refuses to proceed.
