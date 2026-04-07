---
name: draft-release-copy
description: Draft and validate reusable release-copy updates by collecting release evidence, preparing publish configuration and README updates, and normalizing release-issue create or edit actions. Use when Codex must turn tracked repo state plus release evidence into guarded release-copy edits without encoding project-specific release policy in the retained kernel.
---

# Draft Release Copy

Use this skill to prepare reusable release-copy updates with packet-heavy local synthesis and validator-normalized apply actions.

## Use When

- the user wants release notes, README release text, publish metadata, or release-issue copy updated from tracked evidence
- common-path drafting should stay local on `global_packet.json` plus `synthesis_packet.json`
- mini workers are used only for narrow packet analysis and never as the final mutation authority

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/draft-release-copy/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/draft-release-copy/<run-id>.json`

## Entry

1. Collect, lint, and build with `<python-bin> -B <skill-dir>/scripts/collect_release_copy_context.py`, `lint_release_copy.py`, and `build_release_copy_packets.py --result-output <build-result-json>`.
2. Initialize the evaluation log, merge the build result, then read `orchestrator.json`, `global_packet.json`, `synthesis_packet.json`, and only the focused packet needed for the current drafting decision.
3. Draft the local release-copy plan, validate it with `validate_release_copy.py`, and run `apply_release_copy.py` only from validator-normalized output.
4. Finalize the evaluation log after validation and apply results are recorded.

## Continue Only If

- `packet_worker_map` remains the routing authority for delegated packet analysis
- review-mode baselines, adjustments, override signals, worker recommendations, and token metrics stay in build/eval artifacts instead of widening runtime packets
- packet insufficiency is treated as a contract failure instead of compensating with broad raw rereads
- apply consumes validator-normalized output only and never raw plan JSON directly
- repo-specific bindings stay data-only in the active profile

## Stop When

- confidence is low, context is stale, or ownership or packet matching is ambiguous
- the synthesis packet is insufficient for the common path
- required evidence, release gates, project scope, or issue snapshot freshness blocks the run
- a concrete Python interpreter cannot be resolved for the helper scripts

## Final Response

- say which packets drove the decision and whether mini workers were used
- say which repo profile was active when repo-specific bindings mattered
- say whether the run stopped at planning, validation, or apply
- if blocked, name the blocker precisely

## References

- `references/release-copy-contract.md`
- `references/architecture-note.md`
- `references/delegation-playbook.md`
- `references/release-copy-evaluation-contract.md`
- `references/core-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_prepare_release_copy.py --repo-root <repo-root>`
