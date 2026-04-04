# Prepare Release Copy Architecture Note

This note explains why `draft-release-copy` keeps a `packet-heavy-orchestrator` shape instead of collapsing into either a flat-contract mutation skill or a fully hierarchical candidate workflow.

## Why This Profile Exists

Flat-contract skills are the default and usually simpler. `draft-release-copy` is an exception because the local agent must synthesize all of these together before mutation:

- release-gate applicability
- publish metadata drift
- README current-state drift
- shipped-change evidence
- existing release-issue delta
- helper handoff policy

That combination is too broad for a single worker-facing packet and too coupled to leave final wording outside a local decision packet. The result is:

- compact focused packets for narrow worker analysis
- one local-only `synthesis_packet.json` for final drafting
- validator/apply remaining deterministic and narrow

## Why Not A Flat Mutation Profile

A flat mutation profile would force the local agent to reread raw release sources too often. That works operationally, but it weakens the packet workflow by making raw reread compensatory instead of exceptional.

## Why Not A Fully Hierarchical Candidate Profile

This skill still does not want worker-authored candidate inventories. Final release wording, final issue wording, and mutation authority remain local. A hierarchical candidate/result contract would add structure that the apply boundary does not need.

## Common-Path Rule

`synthesis_packet.json must be sufficient for local final drafting in the common path; raw reread should be exceptional, not compensatory.`

Common path means:

- read `global_packet.json`
- read `synthesis_packet.json`
- open at most one focused packet
- finish local final drafting without reopening raw release sources

If this path fails because the packet set is not sufficient, treat that as packet insufficiency and stop. Do not silently compensate with broad rereads.

## Runtime Vs Eval Split

- runtime contract:
  - `orchestrator.json`
  - runtime packets
  - validator/apply inputs and outputs
- eval contract:
  - `packet_metrics.json`
  - optional build result JSON from `build_release_copy_packets.py --result-output`
  - `eval-log.json`
  - smoke summaries

Token-efficiency data belongs to the eval side. It is for regression visibility, not routing authority.

## Field Role Rule

- authority:
  - `authority_order`
  - `packet_worker_map`
  - `common_path_contract`
- metadata:
  - `preferred_worker_families`
- derived convenience:
  - `recommended_workers`
  - `optional_workers`
- explanatory:
  - `worker_selection_guidance`

If these drift, the authority fields win.

## Out Of Scope

This skill intentionally does not do:

- unsupported XML layout rewrites
- broad README structure rewrites
- narrative-only prose mutation outside deterministic apply
- helper execution
- worker-authored final release wording

## Maintenance Note

If you change packet names, authority order, smoke schema, or runtime/eval boundaries, update all of these in the same patch:

- `release_copy_plan_contract.py`
- `build_release_copy_packets.py`
- `release-copy-contract.md`
- `SKILL.md`
- smoke output expectations
- packet/build/eval tests
