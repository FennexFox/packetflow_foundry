# Pattern Catalog

Read this file when a new workflow needs to be mapped onto the packet-driven repo pattern.
This file is a shared core reference, not a project-local profile surface.

## Core Shape

The repeated family in this environment follows:

1. deterministic context collection
2. optional deterministic lint or normalization
3. packet building
4. local synthesis from `orchestrator.json` and `global_packet.json`
5. optional validate or apply
6. local evaluation-log updates for efficiency, quality, and safety tracking

Keep the generated skill lean. Put the workflow in `SKILL.md`, detailed contracts in `references/`, and deterministic logic in `scripts/`.

## Common Reference-Grade Baseline

Promote these as the common default for new reference-grade scaffolds:
- authoritative contract source in code and references
- validator/apply separation for mutating workflows
- apply consumes validator-normalized output only
- stale-context recheck and dry-run parity
- explicit stop taxonomy and fixed warning/error codes
- smoke or end-to-end dry-run validation
- runtime contract metadata separated from evaluation/regression metadata

## Archetypes

### `audit-only`

Use for read-only tasks that compare rules, docs, repo state, or GitHub state and report a decision.

### `audit-and-apply`

Use for tasks that audit first and then apply a small, direct mutation path after local synthesis.

### `plan-validate-apply`

Use when the skill must create a structured action plan and refuse mutation until that plan is validated.

## Packet Defaults

Every generated skill should keep these contracts:
- `orchestrator.json`
  - review mode
  - worker budget
  - shared packet name
  - local responsibilities
  - recommended workers
- `global_packet.json`
  - authoritative context shared by all workers
  - stop conditions
  - review mode overrides
  - non-authoritative helper notes when relevant

Focused packets should be named for the workflow, for example:
- `rules_packet.json`
- `changes_packet.json`
- `thread-01.json`
- `commit-01.json`

Use batch packets only when a grouped unit saves worker count or preserves context better than singleton packets.

## Packet-Heavy Orchestrator Profile

Use `orchestrator_profile=packet-heavy-orchestrator` only when the workflow is both packet-heavy and local-synthesis-heavy.

Profile-specific additions:
- `synthesis_packet.json`
  - shared local drafting packet for the common path
- `common_path_contract`
  - runtime rule that common-path drafting should finish from `global_packet.json`, `synthesis_packet.json`, and at most one focused packet reread
- `packet_metrics.json`
  - evaluation/regression sidecar for packet sizing and byte/token proxies

Do not make this the blanket default.
- Narrow mutation skills usually need the common baseline only.
- Packet-efficiency counters usually belong in evaluation artifacts, not runtime packets.

## Hierarchical Adjudication Workflow

Use this pattern when the local orchestrator must make the final decision from packetized evidence rather than from broad raw rereads.

Shared generic structure:
- `decision_ready_packets=true`
- `worker_return_contract=classification-oriented`
- `worker_output_shape=hierarchical`
- worker outputs use:
  - `candidates[]`
  - `footer`
- candidate-level factual summaries stay inside `candidates[]`
- worker batch summary stays in `footer.primary_outcome` only
- worker classifications remain proposal-only
- final adjudication stays local
- final plan confidence is recomputed locally
- raw rereads remain exception-only

Generic candidate semantics:
- `fact_summary`
- `proposal_classification`
- `classification_rationale`
- `supporting_references`
- `ambiguity`
- `confidence`
- `reread_control`

Generic footer semantics:
- `packet_ids`
- `candidate_ids`
- `primary_outcome`
- `overall_confidence`
- `coverage_gaps`
- `overall_risk`

Shared reread discipline:
- do not reopen raw evidence by default after packet generation
- reread only when reread control points to an allowed reason such as:
  - `conflicting_signals`
  - `missing_required_evidence`
  - `schema_mismatch`
  - `insufficient_excerpt_quality`

Required retained-shape guards:
- do not combine `classification-oriented` with `decision_ready_packets=false`
- do not declare explicit `candidate_field_bundles` for `generic` worker return
  contracts
- do not declare explicit `worker_footer_fields` outside decision-ready
  hierarchical flows

## Worker Family Pattern

Use named worker families when the workflow benefits from reusable specialists without collapsing every workflow into one downstream-specific contract.

Context/findings workers:
- `repo_mapper`
  - execution path
  - touched surfaces
  - packet membership hints
  - assumptions and unknowns
- `packet_explorer`
  - one focused packet or batch packet
  - explicitly referenced file slices only when needed
  - packet-scoped code, behavior, or workflow findings
- `docs_verifier`
  - verified vs inferred vs unknown claims
  - exact refs
  - narrow verifier-only checks

Candidate-producing workers:
- `evidence_summarizer`
  - long narrative evidence -> decision-ready candidate records
- `large_diff_auditor`
  - risk hotspots -> candidate-ready change findings
- `log_triager`
  - failure signals -> candidate-ready root-cause or incident findings

Routing rules:
- `worker_selection_guidance` explains when each family is useful
- `packet_worker_map` is the only concrete routing authority
- the builder should not infer packet-to-agent routing from packet names alone

Optional worker surface:
- family membership may overlap
- surfaced `optional_workers` is still a deduped list
- when explicit packet routing exists, delegation docs should surface the delegated-mode optional list after removing mapped recommended worker types
- the same worker type may still appear on multiple packet assignments in `recommended_workers`

## Domain Overlay Pattern

Use a `domain_overlay` when the workflow needs domain semantics without changing the shared structure.

Typical overlay responsibilities:
- define proposal enum values
- map generic candidate semantics to domain field names
- mark some proposal values as reference-only
- declare output inclusion and exclusion rules
- adjust candidate bundles for the domain

The overlay should never rename shared structural keys like `candidates` or `footer`.

Precedence model:
1. shared structure stays fixed
2. generic candidate bundles establish semantic slots
3. overlay bundle overrides adjust those bundles
4. overlay aliases rename the resolved semantic slots

## Weekly-Update As One Example

`weekly-update` is a strong example overlay, not the universal template.

It specializes the shared structure by:
- defining proposal enum values such as incident, blocker/risk, reference-only artifact, and ignore
- mapping generic candidate semantics to names like `summary`, `proposed_classification`, `source_refs`, `open_ambiguity`, and `raw_reread_reason`
- mapping packets to reusable worker types such as:
  - `mapping_packet -> repo_mapper`
  - `changes_packet -> large_diff_auditor`
  - `incidents_packet -> log_triager`
  - `risks_packet -> evidence_summarizer`
- marking one proposal value as reference-only
- defining final section inclusion rules for its reporting output
- keeping repo-specific review markers, release-title patterns, and similar
  conventions in `repo_profile.extra.weekly_update` rather than in a separate
  builder family

That same structure can support other adjudication-heavy workflows such as:
- release gating
- incident-vs-risk adjudication
- review triage
- operational summaries

## Delegation Defaults

- `local-only`
  - no workers
- `targeted-delegation`
  - 1-2 narrow packet workers
- `broad-delegation`
  - 3-4 narrow packet workers
  - add QA only when findings conflict or mutation risk is broad

Workers should read:
1. `global_packet.json`
2. one narrow packet or one batch packet
3. one file slice only when necessary

Worker return modes:
- `generic`
  - flat outcome-oriented response
- `classification-oriented`
  - proposal-grade candidate records for local adjudication
  - prefer hierarchical `candidates[] + footer`

## Safety Defaults

Generated skills should inherit these assumptions unless the target workflow clearly needs something else:
- keep final synthesis local
- keep final adjudication local
- keep mutation local
- stop on `low confidence`
- stop on stale snapshots or stale structured context
- refresh smoke expectations from a fresh snapshot instead of hardcoding them
- use deterministic markers or fingerprints for reruns
- treat optional local helpers as local-only and non-authoritative
- emit local evaluation logs outside the repo by default

## Non-Goals

Do not generate:
- shared runtime Python libraries used by multiple skills
- long generic READMEs
- exhaustive domain semantics without repo evidence
- migration helpers for older generic skills unless the user explicitly asks for a separate migration tool
