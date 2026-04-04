# Weekly Update Contract

This file defines the packet, candidate, worker, and apply contract for the `weekly-update` skill.

## Builder Metadata

- `workflow_family`: `repo-audit`
- `archetype`: `plan-validate-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `true`
- `worker_return_contract`: `classification-oriented`
- `worker_output_shape`: `hierarchical`
- trigger phrases:
  - weekly update
  - summarize this week's PRs
  - synthesize this week's rollouts incidents and reviews
  - build a weekly status update

## Final Output Shape

The final update must:
- state the exact reporting window
- use these sections in order:
  - `PRs`
  - `Rollouts`
  - `Incidents`
  - `Reviews`
  - `Blockers / Risks`
  - `Evidence reviewed`
- include only verified items from the reporting window
- say so briefly when a section has no verified evidence

## Required Runtime Packet Outputs

- `orchestrator.json`
- `global_packet.json`
- `mapping_packet.json`
- `changes_packet.json`
- `incidents_packet.json`
- `risks_packet.json`

## Eval-Side Build Outputs

- `packet_metrics.json`
- build result JSON emitted via `build_weekly_update_packets.py --result-output`

Token-efficiency counters belong only in these evaluation-side artifacts, not in `orchestrator.json`.

## Repo Profile Boundary

- default retained profile: `profiles/default/profile.json`
- preferred project-local override: `.codex/project/profiles/weekly-update/profile.json`
- explicit `--profile <profile-json>` remains available for manual override, smoke, and fixture-refresh entrypoints
- keep repo-specific conventions in `repo_profile.extra.weekly_update`
- collected context, `orchestrator.json`, `global_packet.json`, and build-result artifacts should surface active profile metadata

## Authority Order

Use evidence in this order:
- published GitHub releases and linked release issues
- merged PR diffs and git history
- directly related review, issue, and workflow-run evidence
- structured workflow packets
- local last-success state as baseline only

The last-success marker is never a facts source for the weekly narrative. It is only a baseline source for the reporting window.

## Analysis Ref Semantics

- Resolve `analysis_ref` before any local git or file evidence is collected or reread.
- Repo-wide GitHub evidence remains repo-wide:
  - releases
  - PR summaries and details
  - issues
  - review comments
  - workflow runs
- Local git and file evidence is selected-ref-local and must follow `analysis_ref.selected_ref` and `analysis_ref.selected_sha`.
- Default retained behavior is `analysis_ref.policy=freshest_local_branch`.
- `freshest_local_branch` selects the tip under `refs/heads/*` with the newest commit timestamp.
- `current_head` preserves the old attached or detached `HEAD` behavior.
- `preferred_branch_order` selects the first configured local branch, then falls back to `freshest_local_branch`, then to `current_head` when no local branches exist.
- When the selected ref differs from the current workspace `HEAD`, use `git show <analysis_ref.selected_sha>:<repo-relative-path>` or an equivalent selected-ref materialization for local rereads instead of the worktree filesystem.
- State-marker identity is keyed by the logical repo's shared git common-dir plus the analysis-ref policy so ephemeral worktree paths do not fragment weekly history.

## Review Mode Guidance

- `local-only`
  - use no workers
  - reserve for quiet windows with a small candidate set and no meaningful rollout or incident activity
- `targeted-delegation`
  - default mode
  - use 1-2 workers on narrow focused packets
- `broad-delegation`
  - use 3-4 workers when releases, incidents, reviews, and nested PR lineage materially expand the evidence graph

## Worker Routing Metadata

Preferred worker families:
- `context_findings`
  - `repo_mapper`
  - `docs_verifier`
- `candidate_producers`
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `verifiers`
  - `docs_verifier`

Concrete routing uses `packet_worker_map`:
- `mapping_packet -> repo_mapper`
- `changes_packet -> large_diff_auditor`
- `incidents_packet -> log_triager`
- `risks_packet -> evidence_summarizer`

Rules:
- `packet_worker_map` is the routing authority
- `worker_selection_guidance` is explanatory only
- routed worker budgets still follow `local-only`, `targeted-delegation`, and `broad-delegation`

## Candidate Proposal Model

Workers and collectors produce proposal-grade candidates. The main agent performs the final adjudication.

- `proposed_classification` is worker proposal only; the main agent may override it.
- `final_classification` is local synthesis state, not a worker-output field.
- `summary` is the candidate-level fact summary.
- `classification_rationale` explains why the candidate was proposed for that classification.
- `artifact_only` candidates are reference-only evidence. They do not appear as standalone final section items, but may support another candidate or appear in `Evidence reviewed`.

### Candidate Schema

Every candidate record uses this schema:
- `candidate_id`
- `source_type`
- `source_id`
- `title`
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

### Classification Values

`proposed_classification` allows only:
- `actual_incident`
- `blocker_or_risk`
- `artifact_only`
- `ignore`

### Confidence Rules

`confidence` is a candidate-level enum:
- `high`
  - failure and materiality evidence are both direct
  - no meaningful conflicting signal remains
- `medium`
  - core evidence exists
  - some ambiguity remains, but the proposal is still usable
- `low`
  - a proposal is possible
  - raw reread is likely required before final adjudication

### Canonical Citations

`source_refs` is the canonical citation list across packets and worker output.

Each entry must include:
- `kind`
- `ref`

It may also include:
- `url`

Example refs:
- `issue/#110`
- `pr/#97`
- `release/v0.2.3`
- `run/23635553980`
- `review/pr107-comment2992368622`
- `file/.github/scripts/perf_telemetry_automation.py`

Do not use a separate `evidence_files_or_links` field.

### Excerpt Bundle

`excerpt_bundle` uses named slots:
- `failure_excerpt`
- `materiality_excerpt`
- `ambiguity_excerpt`

Each slot is nullable. When present it contains:
- `text`
- `source_ref`
- `source_type`
- `why_selected`

Selection rules:
- `failure_excerpt`
  - choose the excerpt that most directly shows failure, regression, invalid output, or broken behavior
- `materiality_excerpt`
  - choose the excerpt that most directly shows weekly relevance such as creation, resolution, significant update, or linked PR/workflow impact during the reporting window
- `ambiguity_excerpt`
  - choose the excerpt that most directly shows unresolved scope, incomplete evidence, or remaining ambiguity

Do not place full issue bodies, long PR diffs, or workflow-log transcripts inside the excerpt bundle.

### Raw Reread Control

`raw_reread_reason` is a nullable enum:
- `null`
- `conflicting_signals`
- `missing_failure_evidence`
- `missing_materiality_evidence`
- `schema_mismatch`
- `insufficient_excerpt_quality`

Treat `raw_reread_reason != null` as an exception path. The main agent should reread raw evidence only for those candidates when local adjudication requires it.

### Packet Membership

`packet_membership` is the canonical list of packet names that contain the candidate.

Use it to:
- track intended duplication across packets
- verify packet completeness
- explain why a review-related candidate may appear in both `Reviews` and `Blockers / Risks`

## Packet Semantics

### `orchestrator.json`

Keep runtime routing and local-adjudication metadata here:
- `orchestrator_profile`
- `review_mode`
- `decision_ready_packets`
- `worker_return_contract`
- `worker_output_shape`
- `packet_worker_map`
- `preferred_worker_families`
- `recommended_workers`
- `optional_workers`
- `shared_packet`
- `selected_packets`
- `common_path_contract`
- `local_responsibilities`
- `review_mode_overrides`

Do not place token/size counters or build-only packet inventory metadata in `orchestrator.json`.

### `global_packet.json`

Keep shared workflow facts here:
- reporting window
- primary goal
- authority order
- stop conditions
- `analysis_ref`
- review mode
- worker budget
- section rules
- source-gap summary
- `decision_ready_packets`
- `worker_return_contract`
- `worker_output_shape`
- `candidate_field_bundles`
- `worker_footer_fields`
- `reread_reason_values`
- `domain_overlay`
- `preferred_worker_families`
- `packet_worker_map`
- `worker_selection_guidance`

### `common_path_contract`

Lock the normal local-adjudication path to:
- `global_packet.json`
- `mapping_packet.json`
- one focused packet needed for the current decision

Raw reread stays exception-only and must remain candidate-scoped through `raw_reread_reason`.

### `mapping_packet.json`

Keep the evidence map here:
- reporting window
- default branch
- `analysis_ref`
- release-to-issue linkage
- top-level versus nested PR lineage
- candidate inventory index
- each candidate's `packet_membership`
- candidates whose `raw_reread_reason != null`

### `changes_packet.json`

Keep top-level shipped change candidates here:
- top-level merged PR candidates only
- `shipped_change_bullets`
- `review_followups`
- linked issue and review candidate references

`review_followups` must stay separate from `shipped_change_bullets`.

### `incidents_packet.json`

Keep incident-focused candidates here:
- candidates proposed as `actual_incident`
- incident-adjacent candidates that still require adjudication
- workflow failures only when they materially affected release, validation, or schedule

### `risks_packet.json`

Keep blocker and risk material here:
- candidates proposed as `blocker_or_risk`
- `artifact_only` reference candidates
- unresolved review findings
- release-gate gaps
- pending follow-ups

## Reviews And Blockers Rules

- `Incidents` is narrow.
  - include only actual events that materially affected operations, validation, release, or schedule during the reporting window
- pending investigations, gate tracking, reusable evidence artifacts, and forecasted risks belong in `Blockers / Risks`, not `Incidents`
- resolved review findings appear in `Reviews` only
- unresolved review findings with release or merge-gate impact may appear in both `Reviews` and `Blockers / Risks`
- generic notices, bot noise, and empty self-reviews are always excluded

## Worker Output Contract

Each worker response has two layers:
- top-level `candidates[]`
- top-level `footer`

### Candidate-Level Fields

Each entry in `candidates[]` contains candidate-level data. The worker-level summary does not replace or absorb these fields.

Required candidate fields:
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

### Worker Footer Fields

Every worker response also includes `footer` with:
- `packet_ids`
- `candidate_ids`
- `primary_outcome`
- `overall_confidence`
- `coverage_gaps`
- `overall_risk`

Definitions:
- `footer.primary_outcome`
  - worker-level batch summary only
- `footer.overall_confidence`
  - worker-level confidence for the whole batch
  - summarize candidate confidences and unresolved ambiguity as `high`, `medium`, or `low`
- `footer.candidate_ids`
  - follow `candidates[]` stable discovery order exactly
- `footer.coverage_gaps`
  - scope the worker could not read or could not verify sufficiently
- `footer.overall_risk`
  - remaining batch-level operational or adjudication risk

Candidate-level `risk` is limited to that candidate. It is not a substitute for worker-level `footer.overall_risk`.

## Plan And Apply Contract

Use `weekly-update-plan.json` as the local synthesis artifact.

It should include at least:
- `context_id`
- `context_fingerprint`
- `reporting_window`
- `selected_packets`
- `overall_confidence`
- `stop_reasons`
- `allow_marker_update`
- `sections`

`scripts/apply_weekly_update.py` must read only the synthesized plan fields:
- `overall_confidence`
- `stop_reasons`
- `allow_marker_update`

`scripts/validate_weekly_update_plan.py` validates the full plan schema before apply, including:
- required plan fields
- section-key coverage and ordering
- `artifact_only` direct-section exclusion
- unresolved reread and low-confidence marker-update blocks

The apply step must not read worker footers directly.

Marker updates are blocked when:
- unresolved `raw_reread_reason` exceptions remain after adjudication
- `overall_confidence` is `low`
- `allow_marker_update` is `false`

Default state-marker lookup and write paths are derived from the logical repo identity plus the resolved analysis-ref policy, not from an ephemeral worktree root path. The collector may read a legacy path once during migration, but successful apply writes the stable marker path.

## Notes

- Flat contracts remain the default in this environment. Read `references/architecture-note.md` for why `weekly-update` keeps a hierarchical contract as an explicit exception.
- Use only repository evidence and directly related GitHub evidence available during the run.
- When evidence is missing or conflicting, keep the claim out of the final weekly update.
- Keep packet contents adjudication-ready so the main agent does not need broad raw rereads in the normal path.
- `scripts/refresh_weekly_update_live_fixture.py` is maintainer-only. It may refresh fixture snapshots from live evidence, but it must stay out of the default unit-test path because it depends on networked GitHub state.
- Automation or meta-skill prompts should stay thin: invoke `$weekly-update`, specify the final section order and reporting-window requirement, and let this skill own packet internals, worker routing, and apply-gate details.
