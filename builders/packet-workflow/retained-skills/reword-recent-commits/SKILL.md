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

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } | Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox, reuse that exact path inside the sandbox instead of calling `py` or bare `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter path.

## Workflow

1. Use the single driver for the normal path.
- Run `<python-bin> -B <skill-dir>/scripts/reword_recent_commits.py --repo <repo-root> --count <n> --prepare-only`.
- Edit the emitted `message-template.json` by filling `commits[*].new_message`.
- Run `<python-bin> -B <skill-dir>/scripts/reword_recent_commits.py --repo <repo-root> --count <n> --messages-file <message-template-json>`.
- Add `--apply` only after confirmation. Without `--apply`, the driver validates and runs `apply_reword_plan.py --dry-run`.
- Use `--temp-root <path>` when `git worktree add` needs a known-writable parent path. Resolution order is `--temp-root`, then `REWORD_RECENT_COMMITS_TEMP_ROOT`, then `~/.codex/tmp/packet-workflow/reword-recent-commits/temp/<repo-name>`.
- Artifacts default to `<repo-root>/.codex/tmp/packet-workflow/reword-recent-commits/<run-id>`, and the workflow excludes the managed `.codex/tmp/` prefix from dirty-worktree checks.
- Read `<artifact-root>/packets/orchestrator.json` first.
- Keep `<artifact-root>/packets/global_packet.json` in view before reading any focused packet.
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
- Run `reword_recent_commits.py --messages-file ... --apply` only after confirmation.
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

- `scripts/reword_recent_commits.py`
  - Normal entrypoint for prepare, validate, dry-run apply, real apply, and evaluation-log finalization.
- `scripts/reword_runtime_paths.py`
  - Resolve the fixed repo-local `.codex/tmp/packet-workflow/reword-recent-commits/` artifact root and replay temp-root parent path.
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
  - Run the temp-repo smoke path through the single driver and print a compact JSON summary.

## Debugging And Manual Recovery

- If the driver flow blocks, fall back to the low-level scripts in order: `collect_commit_rules.py`, `collect_recent_commits.py`, `build_reword_packets.py`, `validate_reword_plan.py`, `apply_reword_plan.py`, and `write_evaluation_log.py`.
- Keep `message-template.json` shape fixed:
  - root keys: `context_fingerprint`, `branch`, `head_commit`, `commits`
  - commit keys: `index`, `hash`, `current_subject`, `new_message`
- Ignore any extra keys when using `--messages-file`; only `new_message` is consumed from the user-edited commit entries.

## Evaluation

- The driver initializes the evaluation log after packet generation, merges build/validation/apply phase results, and finalizes the run.
- Use `--final-observations <json>` to merge extra finalize payload fields when needed.
- Low-level debugging still uses `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init|phase|finalize ...`.
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
