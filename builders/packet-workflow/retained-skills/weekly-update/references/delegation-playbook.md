# Delegation Playbook

Read this file only when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`
  - no workers
- `targeted-delegation`
  - default mode
  - 1-2 workers
- `broad-delegation`
  - 3-4 workers
- Optional QA worker
  - only when worker findings conflict or a raw reread exception remains unresolved

## Worker Families

- `context_findings`
  - `repo_mapper`
  - `docs_verifier`
- `candidate_producers`
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `verifiers`
  - `docs_verifier`

Surfaced optional-worker list after subtracting explicitly routed workers:
- `targeted-delegation`
  - `docs_verifier`
  - `evidence_summarizer`
  - `log_triager`
- `broad-delegation`
  - `docs_verifier`
- `local-only`
  - no delegation; optional workers are informational only and should not be spawned

Rules:
- `packet_worker_map` is the routing authority
- `worker_selection_guidance` is explanatory only
- do not infer routing from packet names alone when explicit routing metadata exists

## Shared Packet Discipline

Every worker reads `global_packet.json` first.

Then give the worker only:
- one focused packet or one narrow slice from a focused packet
- any explicitly referenced file slice only when the packet cannot carry the required evidence

Do not ask workers to:
- rediscover the whole repo state from scratch
- reread long raw diffs or workflow logs without an explicit exception reason
- draft the final user-facing weekly update

## Explicit Packet Routing

Use this `packet_worker_map`:
- `mapping_packet -> repo_mapper`
- `changes_packet -> large_diff_auditor`
- `incidents_packet -> log_triager`
- `risks_packet -> evidence_summarizer`

Use these `worker_selection_guidance` notes only as supporting context:
- `repo_mapper`
  - reporting-window grounding, release linkage, PR lineage, candidate inventory, and packet membership
- `docs_verifier`
  - tracked docs or runbooks needed to resolve conflicting packet evidence
- `large_diff_auditor`
  - shipped change bullets, behavior or config changes, and review-driven follow-ups
- `log_triager`
  - failure signals, workflow impact, and incident-versus-risk evidence
- `evidence_summarizer`
  - narrative-heavy issue, release, review, or workflow discussion compressed into adjudication-ready excerpts and rationales

## Candidate Proposal Rules

Workers return proposal-grade candidates only.

- `proposed_classification` is worker proposal only; the main agent may override it
- `summary` is the candidate-level fact summary
- `classification_rationale` explains why that proposal was made
- `source_refs` is the canonical citation list
- `artifact_only` candidates remain reference-only evidence

If a worker cannot support a proposal cleanly from the packet, it should lower confidence or set `raw_reread_reason` rather than broadening scope on its own.

## Worker Output Contract

Each worker response has:
- `candidates[]`
- `footer`

### `candidates[]`

Each candidate entry should include:
- `candidate_id`
- `summary`
- `proposed_classification`
- `classification_rationale`
- `materiality_evidence`
- `concrete_failure_evidence`
- `open_ambiguity`
- `confidence`
- `source_refs`
- `excerpt_bundle`
- `raw_reread_reason`
- `packet_membership`
- `risk`
- `recommended_next_step`
- `tests_or_checks`

`confidence` meanings:
- `high`
  - direct failure and materiality evidence with no meaningful conflict
- `medium`
  - core evidence exists but some ambiguity remains
- `low`
  - raw reread is likely required before final adjudication

### Worker Footer Fields

Return `footer` with these fields exactly:
- `packet_ids`
- `candidate_ids`
- `primary_outcome`
- `overall_confidence`
- `coverage_gaps`
- `overall_risk`

Field meanings:
- `packet_ids`
  - the packets or packet slices the worker actually used
- `candidate_ids`
  - follow `candidates[]` stable discovery order exactly
- `primary_outcome`
  - worker-level batch summary only
- `overall_confidence`
  - worker-level confidence for the full batch
- `coverage_gaps`
  - unread or insufficiently verified scope
- `overall_risk`
  - remaining batch-level operational or adjudication risk

Candidate-level `risk` is specific to one candidate. Worker-level `overall_risk` summarizes the batch.

## Excerpt And Reread Rules

Each candidate uses named excerpt slots:
- `failure_excerpt`
- `materiality_excerpt`
- `ambiguity_excerpt`

Selection rules:
- choose one excerpt that most directly shows failure or broken behavior
- choose one excerpt that most directly shows weekly materiality
- choose one excerpt that most directly shows ambiguity or unresolved scope

If the packet cannot support a usable excerpt bundle, set `raw_reread_reason` to one of:
- `conflicting_signals`
- `missing_failure_evidence`
- `missing_materiality_evidence`
- `schema_mismatch`
- `insufficient_excerpt_quality`

`raw_reread_reason != null` means the main agent may approve a narrow raw reread for that candidate only.

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use $weekly-update to analyze packet-driven workflow inputs.

Read only:
- <global-packet>
- <focused-packet-or-focused-slice>

Read `global_packet.json` first.
Treat `packet_worker_map` as routing authority.
Treat proposed_classification as worker proposal only.
Use source_refs as the canonical citation list.
Return:
- candidates[]
- footer.packet_ids
- footer.candidate_ids
- footer.primary_outcome
- footer.overall_confidence
- footer.coverage_gaps
- footer.overall_risk
```

Keep each worker narrow. Keep the final section wording, final classification, and marker-update decision local.
