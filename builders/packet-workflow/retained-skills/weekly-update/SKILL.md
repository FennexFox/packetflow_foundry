---
name: weekly-update
description: Top-level orchestration skill for reusable weekly updates. Synthesize recent PRs, rollouts, incidents, reviews, and blockers using packet-driven evidence collection and narrow read-only delegation, keep worker outputs proposal-grade, keep final classification and wording local, and update only a last-success marker after a reviewed plan clears apply gates.
---

# Weekly Update

Use this skill as the top-level orchestration layer for packet-driven weekly updates.

The retained fallback profile lives at `profiles/default/profile.json`.
When this skill is vendored, prefer a project-local override at `.codex/project/profiles/weekly-update/profile.json`.
Use `--profile` only when you need to override the default discovery order explicitly.
Read `references/core-contract.md` for the reusable packet-workflow boundary.

This is a packet-driven workflow:
- keep evidence collection and packet building deterministic
- keep final classification, section inclusion, final wording, and marker updates local
- use `gpt-5.4-mini` workers only for narrow read-only packet analysis
- treat worker classifications as proposals, not final decisions

## Packet Contract

- `orchestrator_profile=standard`
- `decision_ready_packets=true`
- `worker_return_contract=classification-oriented`
- `worker_output_shape=hierarchical`
- `packet_worker_map` is the routing authority for delegated packets
- `worker_selection_guidance` is explanatory only and must not override explicit packet routing
- workers read `global_packet.json` first, then exactly one focused packet or one narrow packet slice
- workers return hierarchical proposal-grade output as `candidates[]` plus `footer`
- token-efficiency counters live in `packet_metrics.json` and the evaluation log, not in runtime packets
- read `references/architecture-note.md` for why this skill keeps hierarchy even though flat-contract skills remain the default elsewhere

## Automation Prompt Shape

When another automation or meta-skill invokes this skill, keep the prompt thin and contract-aware.

Include:
- `Use [$weekly-update](<skill-dir>/SKILL.md).`
- the expected final section order
- the requirement to state the exact reporting window
- the instruction to report the concrete blocker and stop at the appropriate gate when collection, validation, or apply cannot proceed

Do not restate:
- packet internals
- worker field lists
- packet-to-worker routing details
- apply-gate implementation details already locked in this skill

Prefer a prompt shaped like:

```text
Use [$weekly-update](<skill-dir>/SKILL.md).

Produce this workspace repo's weekly update.
Return sections `PRs`, `Rollouts`, `Incidents`, `Reviews`, `Blockers / Risks`, and `Evidence reviewed`.
State the exact reporting window.
If the run cannot proceed, report the blocker clearly and stop at the appropriate gate.
```

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } | Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox, reuse that exact path inside the sandbox instead of calling `py` or bare `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter path.
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/weekly-update/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `<repo-root>/.codex/tmp/evaluation_logs/weekly-update/<run-id>.json` by default and keep `.codex/tmp/` gitignored.

## Workflow

1. Verify GitHub access first.
- Run `gh auth status`.
- If authentication fails, stop and tell the user to run `gh auth login`.
- Do not substitute weaker local-only guesses when remote GitHub evidence is required for the reporting window.

2. Collect structured context before broad reading.
- Prefer `<python-bin> -B` for verification and smoke commands and reuse the resolved concrete interpreter path for every helper script.
- Run `<python-bin> -B <skill-dir>/scripts/collect_weekly_update_context.py --repo-root <repo-root> --output <context-json> [--profile <profile-json>]`.
- Run `<python-bin> -B <skill-dir>/scripts/lint_weekly_update.py --context <context-json> --output <lint-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_weekly_update_packets.py --context <context-json> --lint <lint-json> --output-dir <packet-dir> --result-output <build-result-json>`.
- `collect_weekly_update_context.py` resolves `repo_profile.extra.weekly_update.analysis_ref` before any local git or file evidence is interpreted.
- Default retained behavior is `analysis_ref.policy=freshest_local_branch`: select the newest commit timestamp under `refs/heads/*`.
- `analysis_ref.policy=current_head` preserves the old attached or detached `HEAD` behavior.
- `analysis_ref.policy=preferred_branch_order` chooses the first configured local branch, then falls back to `freshest_local_branch`, then to `current_head` if no local branches exist.
- Treat releases, PRs, issues, reviews, and workflow runs as repo-wide GitHub evidence. Treat any local git or file reread as selected-ref-local. When the selected ref differs from the workspace `HEAD`, use `analysis_ref.selected_sha` with `git show <sha>:<path>` or an equivalent selected-ref materialization instead of reading the detached worktree filesystem directly.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading focused packets.
- Treat `packet_metrics.json` and `<build-result-json>` as evaluation/regression artifacts, not runtime routing inputs.
- State the exact reporting window in the final update.

3. Follow the weekly-update candidate model.
- Final sections are `PRs`, `Rollouts`, `Incidents`, `Reviews`, `Blockers / Risks`, and `Evidence reviewed`.
- Workers return candidate proposals. `proposed_classification` is worker proposal only; the main agent may override it during final adjudication.
- `summary` is the candidate-level fact summary.
- `classification_rationale` explains why that proposal was made.
- `source_refs` is the canonical citation list across packets and worker output.
- `artifact_only` candidates are reference-only evidence and do not surface as standalone section items.
- Worker outputs remain proposal-grade only; they never decide final classification or final weekly wording.

4. Respect review mode and keep delegation narrow.
- `local-only`: use no workers on the final path. Quiet windows still start here, but the final mode may promote to `targeted-delegation` when `review_mode_adjustments` includes `delegation_savings_floor`.
- `targeted-delegation`: default mode. Use 1-2 `gpt-5.4-mini` workers on one focused packet each.
- `broad-delegation`: use 3-4 `gpt-5.4-mini` workers only when releases, incidents, reviews, and nested PR lineage all expand the evidence surface.
- Read `references/delegation-playbook.md` when `review_mode` is not `local-only`.
- Use `review_mode_baseline` and `review_mode_adjustments` to explain why a quiet-window baseline still delegated.
- Use `packet_worker_map` as the only concrete routing source for delegated packets.
- Treat `worker_selection_guidance` and worker families as explanatory metadata only.
- Do not ask workers to rediscover the whole repo, reread long raw diffs, or draft the final weekly update.
- Workers are read-only packet analysts, not final adjudicators.

5. Respect authority and weekly output rules.
- Authority order:
  - published GitHub releases and linked release issues
  - merged PR diffs and git history
  - directly related review, issue, and workflow-run evidence
  - structured workflow packets
  - local last-success state as baseline only
- Repo-wide GitHub evidence stays repo-wide even when the analysis ref is redirected. Only local git and file evidence follows the selected analysis ref.
- `Incidents` is narrow. Include only actual events that materially affected operations, validation, release, or schedule during the reporting window.
- Put release gates, pending investigations, reusable evidence artifacts, and unresolved risks in `Blockers / Risks` instead.
- In `Reviews`, include resolved findings once. Unresolved gate-impact findings may also appear in `Blockers / Risks`.
- Exclude generic notices, bot noise, and empty self-reviews.

6. Apply only after local synthesis.
- Build and locally review `weekly-update-plan.json`.
- Prefer `<python-bin> -B <skill-dir>/scripts/validate_weekly_update_plan.py --context <context-json> --plan <weekly-update-plan.json> --output <validation-json>` before apply when the plan was synthesized or edited locally.
- Run `<python-bin> -B <skill-dir>/scripts/apply_weekly_update.py --context <context-json> --plan <weekly-update-plan.json> [--dry-run]`.
- `apply_weekly_update.py` reads only the synthesized plan fields `overall_confidence`, `stop_reasons`, and `allow_marker_update`.
- Do not let the apply step read worker footers directly.
- Stop before marker updates when unresolved `raw_reread_reason` candidates remain or the final plan confidence is `low`.
- Default state-marker identity is keyed by the logical repo's shared git common-dir plus the analysis-ref policy so temporary worktree paths reuse the same weekly baseline.

## Required Packets

- `orchestrator.json`
- `global_packet.json`
- `mapping_packet.json`
- `changes_packet.json`
- `incidents_packet.json`
- `risks_packet.json`

## Eval-Side Build Artifacts

- `packet_metrics.json`
- build result JSON from `--result-output`

## Scripts

- `<skill-dir>/scripts/collect_weekly_update_context.py`
  - Collect the reporting window, repo metadata, releases, PRs, issues, review evidence, workflow runs, and candidate inventory.
- `<skill-dir>/scripts/lint_weekly_update.py`
  - Check deterministic boundary conditions such as missing evidence, stale context, and packet-shape blockers.
- `<skill-dir>/scripts/build_weekly_update_packets.py`
  - Build the orchestrator, global packet, the four focused packets, `packet_metrics.json`, and an optional build result JSON for evaluation-log phase merge.
- `<skill-dir>/scripts/validate_weekly_update_plan.py`
  - Validate `weekly-update-plan.json` against the collected context before apply, including marker-update gating, section shape, and artifact-only exclusion rules.
- `<skill-dir>/scripts/write_evaluation_log.py`
  - Record the shared evaluation log for efficiency, quality, and safety tracking.
- `<skill-dir>/scripts/apply_weekly_update.py`
  - Update only the last-success marker after the local plan passes the apply gate.
- `<skill-dir>/scripts/smoke_weekly_update.py`
  - Run an opt-in end-to-end smoke of collect -> lint -> build -> eval init/build -> validate -> eval validate -> apply `--dry-run` -> eval apply, verify runtime packets stay lean, and confirm `--dry-run` apply does not write a marker.
- `<skill-dir>/scripts/refresh_weekly_update_live_fixture.py`
  - Maintainer-only helper that refreshes the live sample fixture and paired plan fixtures from current repo and GitHub evidence. Keep it out of the default test path and prefer `--dry-run` before overwriting fixture files.

## Evaluation

- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <context-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>` after packet generation.
- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase build --result <build-result-json>` after packet build.
- Use phase updates for deterministic validate and apply results when those outputs exist.
- Keep token-efficiency counters in `packet_metrics.json` and the evaluation log only; do not treat them as runtime routing metadata.
- Finalize the evaluation log after the run with worker usage, packet usage, confidence, marker-update status, and any stop reasons.
- Keep the evaluation log under the repo-local `.codex/tmp/evaluation_logs/` tree.
- Read `references/evaluation-log-contract.md` for the shared envelope and `references/weekly-update-evaluation-contract.md` for workflow-specific fields.

## Output

- Tell the user which packets and evidence categories drove the result.
- Tell the user whether the run stayed local or used mini workers.
- Tell the user whether the run stopped at planning or advanced to apply.
- When blocked, name the blocker precisely: invalid `gh` auth, stale context, low-confidence plan, or unresolved raw reread exceptions.
