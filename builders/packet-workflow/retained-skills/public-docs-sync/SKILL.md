---
name: public-docs-sync
description: Audit and synchronize public repository docs against tracked runtime metadata, selected GitHub evidence, and validator-normalized deterministic edits. Use when Codex must detect public-doc drift, propose scoped fixes, and update marker state without embedding repo-specific governance policy in the retained kernel.
---

# Public Docs Sync

Use this skill to audit public docs with scoped packet analysis and validator-normalized deterministic sync actions.

This is a packet-driven repo workflow skill:
- keep orchestration, final synthesis, and mutation local
- use deterministic scripts to collect context before reading raw artifacts broadly
- use `gpt-5.4-mini` workers only for narrow packet analysis
- stop on low confidence, stale snapshots, or ambiguous ownership instead of guessing
- keep generic packet rules in `references/core-contract.md` and repo-specific layout assumptions in `profiles/default/profile.json`
- keep repo profiles data-only: paths, globs, doc lists, booleans, and notes only; executable logic stays in scripts and contracts
- Orchestrator profile: `standard`.
- Keep runtime metadata focused on routing, authority, stop conditions, and adjudication support only.
- Default repo profile scaffold: `profiles/default/profile.json`.
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
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/public-docs-sync/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `~/.codex/tmp/evaluation_logs/public-docs-sync/<run-id>.json` by default. If the sandbox blocks that path, use `<repo-root>/.codex/tmp/evaluation_logs/public-docs-sync/<run-id>.json` as an explicit override and keep `.codex/tmp/` gitignored.

## Workflow

1. Collect structured context.
- Review `references/core-contract.md` before changing shared packet semantics.
- Review `profiles/default/profile.json` before trusting repo-specific path bindings, review-doc lists, or deterministic lint toggles.
- Run `<python-bin> -B <skill-dir>/scripts/collect_public_docs_sync_context.py --repo-root <repo-root> --output <context-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/lint_public_docs_sync.py --context <context-json> --output <lint-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_public_docs_sync_packets.py --context <context-json> --lint <lint-json> --output-dir <packet-dir>`.
- - Optional: add `--result-output <build-result-json>` when you want a machine-readable build summary for smoke runs or evaluation logging.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading any focused packet.
- This scaffold does not add an orchestrator-profile-level common-path drafting packet.

2. Follow the review mode.
- `local-only`: keep the work local.
- `targeted-delegation`: use 1-2 `gpt-5.4-mini` workers on narrow packets.
- `broad-delegation`: use 3-4 `gpt-5.4-mini` workers and add QA only when findings conflict.
- Escalate to the next larger mode when churn is high, core runtime/config/process files span groups, or generated files are not the majority.

3. Keep packet analysis narrow.
- Treat `references/core-contract.md` as the generic workflow contract and `profiles/default/profile.json` as the repo-specific overlay.
- Read `references/public-docs-sync-contract.md` before drafting domain outputs.
- Read `references/delegation-playbook.md` only when `review_mode` is not `local-only`.
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
- `claims_packet.json`
- `reporting_packet.json`
- `workflow_packet.json`
- `forms_batch_packet.json`
- No additional orchestrator-profile-specific runtime packet is required.
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
- Run `<python-bin> -B <skill-dir>/scripts/validate_public_docs_sync.py --context <context-json> --plan <plan-json> --output <validation-json>`.
- Stop if validation reports errors, stale context, low-confidence findings, or an apply-gate failure.

6. Apply only after local verification.
- Run `<python-bin> -B <skill-dir>/scripts/apply_public_docs_sync.py --validation <validation-json>` after the validation output is locally reviewed.
- Apply must consume validator-normalized output only; do not wire raw plan JSON directly into the mutation step.
- If the user asked for `dry-run`, keep the same validation path and stop before any external mutation.

## Evaluation

- Use `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <context-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>` after packet generation.
- No orchestrator-profile-specific evaluation sidecar is required.
- Use `phase` updates for deterministic lint, validate, and apply results when those outputs exist.
- Use `finalize` after the run to merge token usage, actual worker mix, final usability, outputs, and notes.
- Keep the evaluation log at the contract-default outside-repo path unless you intentionally need the gitignored `.codex/tmp/` fallback.
- Keep packet artifacts and other helper temp files under the fixed gitignored `.codex/tmp/packet-workflow/` root.
- Read `references/evaluation-log-contract.md` for the shared envelope and `references/public_docs_sync-evaluation-contract.md` for workflow-specific fields.

## Scripts

- `scripts/collect_public_docs_sync_context.py`
  - Collect the structured inputs and repo artifacts for this workflow, including the active repo profile.
- `scripts/lint_public_docs_sync.py`
  - Run deterministic checks and emit warnings, errors, and override signals.
- `scripts/build_public_docs_sync_packets.py`
  - Build `orchestrator.json`, `global_packet.json`, and focused packets for local synthesis and optional mini-worker analysis.
- `scripts/write_evaluation_log.py`
  - Emit and update the shared evaluation log for efficiency, quality, and safety tracking.
- `scripts/validate_public_docs_sync.py`
  - Validate the planned actions against the collected context, normalize the plan, and emit apply-gate status before apply.
- `scripts/apply_public_docs_sync.py`
  - Dry-run or apply only from validator-normalized output after local verification.

## Output

- Tell the user which packets drove the decision.
- Tell the user whether the run stayed local or used mini workers.
- Tell the user which repo profile was active when repo-specific bindings mattered.
- Tell the user whether final plan confidence was recomputed locally or a reread exception blocked that conclusion.
- Tell the user whether the run stopped at planning, validation, or apply.
