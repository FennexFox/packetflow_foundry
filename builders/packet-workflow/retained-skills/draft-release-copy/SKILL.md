---
name: draft-release-copy
description: Draft and validate reusable release-copy updates by collecting release evidence, preparing publish configuration and README updates, and normalizing release-issue create or edit actions. Use when Codex must turn tracked repo state plus release evidence into guarded release-copy edits without encoding project-specific release policy in the retained kernel.
---

# Draft Release Copy

Use this skill to prepare reusable release-copy updates with packet-heavy local synthesis and validator-normalized apply actions.

This is a packet-driven repo workflow skill:
- keep orchestration, final synthesis, and mutation local
- use deterministic scripts to collect context before reading raw artifacts broadly
- use `gpt-5.4-mini` workers only for narrow packet analysis
- stop on low confidence, stale snapshots, or ambiguous ownership instead of guessing
- keep generic packet rules in `references/core-contract.md` and repo-specific layout assumptions in `profiles/default/profile.json`
- keep repo profiles data-only: paths, globs, doc lists, booleans, and notes only; executable logic stays in scripts and contracts
- prefer a project-local override at `.codex/project/profiles/draft-release-copy/profile.json` when the repo carries release-copy-specific bindings or review docs
- Orchestrator profile: `packet-heavy-orchestrator`.
- Keep runtime contract metadata lean. Put packet sizing, byte proxies, and delegation-efficiency counters in `packet_metrics.json` and evaluation logs instead of `orchestrator.json`.
- Read `synthesis_packet.json` as the shared local drafting packet before reopening raw artifacts.
- Retained neutral profile scaffold: `profiles/default/profile.json`.
- Preferred project-local override path: `.codex/project/profiles/draft-release-copy/profile.json`.
- Keep repo-specific paths, packet review docs, and deterministic lint toggles in the repo profile instead of hardcoding them into the generic core templates.
- Keep the repo profile data-only: paths, globs, doc lists, booleans, and notes only. Do not add executable hooks, prompt text, or worker-routing logic there.

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } | Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox, reuse that exact path inside the sandbox instead of calling `py` or bare `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter path.
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/draft-release-copy/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `<repo-root>/.codex/tmp/evaluation_logs/draft-release-copy/<run-id>.json` by default and keep `.codex/tmp/` gitignored.

## Workflow

1. Collect structured context.
- Review `references/core-contract.md` before changing shared packet semantics.
- Review the active repo profile before trusting repo-specific path bindings, review-doc lists, or deterministic lint toggles.
- Run `<python-bin> -B <skill-dir>/scripts/collect_release_copy_context.py --repo-root <repo-root> --output <context-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/lint_release_copy.py --context <context-json> --output <lint-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_release_copy_packets.py --context <context-json> --lint <lint-json> --output-dir <packet-dir> [--result-output <build-result-json>]`.
- - Recommended: add `--result-output <build-result-json>` so the machine-readable build summary can merge build-phase packet metrics into evaluation logging without expanding runtime contract metadata.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading any focused packet.
- Packet-heavy common path contract:
  - read `global_packet.json` first
  - keep `synthesis_packet.json` open for local drafting
  - reopen at most one focused packet in the common path
  - treat packet insufficiency as a build/contract failure instead of compensating with broad raw rereads

2. Follow the review mode.
- `local-only`: keep the work local unless the final `review_mode` was promoted by `review_mode_adjustments=["delegation_savings_floor"]`.
- `targeted-delegation`: use 1-2 `gpt-5.4-mini` workers on narrow packets.
- `broad-delegation`: use 3-4 `gpt-5.4-mini` workers and add QA only when findings conflict.
- Escalate to the next larger mode when churn is high, core runtime/config/process files span groups, or generated files are not the majority.

3. Keep packet analysis narrow.
- Treat `references/core-contract.md` as the generic workflow contract and the active repo profile as the repo-specific overlay.
- Read `references/release-copy-contract.md` before drafting domain outputs.
- Read `references/delegation-playbook.md` only when the final `review_mode` is not `local-only`.
- Worker return contract for this skill: `generic`.
- Worker output shape for this skill: `flat`.
- Decision-ready packets enabled: `false`.
- XHigh reread policy: Do not reopen raw evidence by default after packet generation. Only reopen raw evidence when reread control points to an allowed reason such as conflicting signals, missing required evidence, schema mismatch, or insufficient excerpt quality.
- Keep final adjudication local.
- Keep worker outputs narrow and use them as inputs to local synthesis, not as final decisions.
- Recompute final plan confidence locally during synthesis from packet evidence, worker outputs, unresolved reread exceptions, and authority conflicts.
- Use the named context/findings worker family when delegation is needed and keep candidate-producing workers optional unless the workflow becomes adjudication-heavy.
- Preferred worker families for this skill:
- `context_findings`: mapping, packet-scoped code analysis, touched-surface, and packet-membership findings
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
- `verifiers`: narrow claim or version-sensitive verification
  - `docs_verifier`
- Use `worker_selection_guidance` as explanatory family guidance only. When configured, `packet_worker_map` owns concrete packet routing.
- Focus packet set for this skill:
- `publish_packet.json`
- `readme_packet.json`
- `changes_packet.json`
- `checklist_packet.json`
- `evidence_packet.json`
- Additional runtime packet:
  - `synthesis_packet.json` for common-path local drafting and synthesis.
- This scaffold defaults to singleton focused packets only.

4. Respect authority and stop conditions.
- Authority order for this skill:
- tracked repo materials
- structured workflow packets
- optional local helper
- No optional local helper is configured for this scaffold.
- Packet-first adjudication guidance:
- Start from packetized evidence first and only widen to raw artifact rereads when the reread policy is triggered.
- Stop and report instead of mutating when:
- low confidence
- stale snapshot or stale context
- ambiguous packet or ownership match

5. Validate before mutating.
- Run `<python-bin> -B <skill-dir>/scripts/validate_release_copy.py --context <context-json> --plan <plan-json> --output <validation-json>`.
- Stop if validation reports errors, stale context, low-confidence findings, or an apply-gate failure.

6. Apply only after local verification.
- Run `<python-bin> -B <skill-dir>/scripts/apply_release_copy.py --validation <validation-json>` after the validation output is locally reviewed.
- Apply must consume validator-normalized output only; do not wire raw plan JSON directly into the mutation step.
- If the user asked for `dry-run`, keep the same validation path and stop before any external mutation.

## Evaluation

- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <context-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>` after packet generation.
- Evaluation-only sidecar:
  - `packet_metrics.json` for packet sizing, byte proxies, and regression-oriented token-efficiency estimates.
- Use `phase` updates for deterministic lint, validate, and apply results when those outputs exist.
- Use `finalize` after the run to merge token usage, actual worker mix, final usability, outputs, and notes.
- Keep the evaluation log under the repo-local `.codex/tmp/evaluation_logs/` tree.
- Keep any repo-local temporary, helper, scratch, or ad hoc input file under the fixed gitignored `.codex/tmp/` tree; packet artifacts stay under `.codex/tmp/packet-workflow/`.
- Read `references/evaluation-log-contract.md` for the shared envelope and `references/release_copy-evaluation-contract.md` for workflow-specific fields.

## Scripts

- `scripts/collect_release_copy_context.py`
  - Collect the structured inputs and repo artifacts for this workflow, including the active repo profile.
- `scripts/lint_release_copy.py`
  - Run deterministic checks and emit warnings, errors, and override signals.
- `scripts/build_release_copy_packets.py`
  - Build `orchestrator.json`, `global_packet.json`, and focused packets for local synthesis and optional mini-worker analysis.
- `scripts/write_evaluation_log.py`
  - Emit and update the shared evaluation log for efficiency, quality, and safety tracking.
- `scripts/validate_release_copy.py`
  - Validate the planned actions against the collected context, normalize the plan, and emit apply-gate status before apply.
- `scripts/apply_release_copy.py`
  - Dry-run or apply only from validator-normalized output after local verification.

## Output

- Tell the user which packets drove the decision.
- Tell the user whether the run stayed local or used mini workers.
- Tell the user which repo profile was active when repo-specific bindings mattered.
- Tell the user whether final plan confidence was recomputed locally or a reread exception blocked that conclusion.
- Tell the user whether the run stopped at planning, validation, or apply.
