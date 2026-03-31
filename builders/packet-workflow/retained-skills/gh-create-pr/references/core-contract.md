# Gh Create Pr Core Contract

This file captures the reusable packet-workflow core boundaries for `gh-create-pr`.

Keep repo-specific guidance sources, review-doc lists, and lint toggles in [profiles/default/profile.json](../profiles/default/profile.json). Keep validator/apply semantics, stop-taxonomy meaning, and packet-routing authority in code and workflow contracts, not in the profile.

## Core Metadata

- `workflow_family`: `github-review`
- `archetype`: `plan-validate-apply`
- `orchestrator_profile`: `packet-heavy-orchestrator`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

## Runtime Outputs

Required runtime outputs:
- `orchestrator.json`
- `global_packet.json`
- `rules_packet.json`
- `testing_packet.json`
- `synthesis_packet.json`

Conditionally emitted runtime packets:
- `runtime_packet.json` when runtime files changed
- `process_packet.json` when automation/docs/config files changed

Evaluation-only output:
- `packet_metrics.json`

Rules:
- keep `packet_metrics.json` out of runtime routing
- keep final title/body synthesis local
- keep `rules_packet.json` authoritative for template, title, and claim gates
- keep validator/apply mutation gates local

## Common Path Contract

Common-path local drafting must close with:
- `rules_packet.json`
- `synthesis_packet.json`
- at most one focused packet

Rules:
- packet insufficiency is a failure, not a reason to widen scope casually
- raw reread is exceptional and should be reserved for stale or disputed evidence
- validator/apply must not rely on collector duplicate hints as authoritative GitHub state

## Worker Routing

`packet_worker_map` is the routing authority when configured:
- `runtime_packet.json -> packet_explorer`
- `process_packet.json -> packet_explorer`
- `testing_packet.json -> evidence_summarizer`

Optional local cross-check workers:
- `rules_packet.json -> docs_verifier`
- `runtime_packet.json -> large_diff_auditor`

Rules:
- `worker_selection_guidance` is explanatory only
- `rules_packet.json` remains local-first even when a rules verifier is available
- final PR draft synthesis never delegates away from the orchestrator

## Runtime vs Evaluation Split

Keep in runtime packets and `orchestrator.json`:
- routing metadata
- authority order
- common-path contract
- local responsibilities
- packet file lists

Keep in `packet_metrics.json` or evaluation logs only:
- packet sizing
- byte proxies
- token-efficiency estimates
- regression-oriented delegation metrics

## Repo Profile Boundary

The default generated profile remains a reusable data-only overlay:
- review-doc locations
- source globs
- repo matching hints
- repo-specific notes

Never move into the profile:
- executable hooks
- prompt fragments
- packet routing authority
- validator/apply behavior
- duplicate-check policy
- stop-taxonomy meaning
