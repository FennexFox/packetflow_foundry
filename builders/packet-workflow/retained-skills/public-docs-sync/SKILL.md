---
name: public-docs-sync
description: Audit and synchronize public repository docs against tracked runtime metadata, selected GitHub evidence, and validator-normalized deterministic edits. Use when Codex must detect public-doc drift, propose scoped fixes, and update marker state without embedding repo-specific governance policy in the retained kernel.
---

# Public Docs Sync

Use this skill to audit public docs with scoped packet analysis and validator-normalized deterministic sync actions.

## Use When

- the user wants public docs checked or synchronized against tracked runtime metadata and selected GitHub evidence
- deterministic doc fixes and marker updates must stay local and validator-gated
- mini workers are used only for narrow packet analysis, not for final doc or marker decisions

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/public-docs-sync/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/public-docs-sync/<run-id>.json`

## Entry

1. Collect, lint, and build with `<python-bin> -B <skill-dir>/scripts/collect_public_docs_sync_context.py`, `lint_public_docs_sync.py`, and `build_public_docs_sync_packets.py --result-output <build-result-json>`.
2. Initialize the evaluation log, merge the build result, then read `orchestrator.json`, `global_packet.json`, and only the active focused packets or batch packet needed for the current review.
3. Draft the local sync plan, validate it with `validate_public_docs_sync.py`, and run `apply_public_docs_sync.py` only from validator-normalized output.
4. Finalize the evaluation log after validation and apply results are recorded.

## Continue Only If

- `packet_worker_map` remains the routing authority for delegated packet analysis
- review-mode baselines, adjustments, override signals, worker recommendations, and packet metrics stay in build/eval artifacts instead of widening runtime packets
- deterministic edits stay within validator-approved scope and marker updates stay blocked while manual narrative review remains
- GitHub evidence follows the configured fail-closed policy before remote claims are trusted
- repo-specific bindings stay data-only in the active profile

## Stop When

- confidence is low, context is stale, or packet ownership is ambiguous
- required evidence is missing, deterministic scope is exceeded, or the marker context is stale
- manual review residuals or validator failures block deterministic sync
- a concrete Python interpreter cannot be resolved for the helper scripts

## Final Response

- say which packets drove the decision and whether mini workers were used
- say which repo profile was active when repo-specific bindings mattered
- say whether the run stopped at planning, validation, or apply
- if blocked, name the blocker precisely

## References

- `references/public-docs-sync-contract.md`
- `references/delegation-playbook.md`
- `references/public-docs-sync-evaluation-contract.md`
- `references/core-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_public_docs_sync.py --repo-root <repo-root>`
