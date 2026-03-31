# Repo Public Docs Sync Contract

This file defines the packet, plan, and apply contract for `public-docs-sync`.

`scripts/public_docs_sync_contract.py` is the authoritative source for packet names, worker routing, reread policy, fixed validation codes, deterministic action aliases, marker stop categories, and packet-metrics helpers. Keep docs and tests aligned to that file instead of restating divergent values.

## Builder Metadata

- `workflow_family`: `repo-audit`
- `archetype`: `audit-and-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`
- trigger phrases:
  - public docs sync
  - audit public docs drift
  - refresh docs after repo changes
  - update the last-success marker

## Packet Set

Required packet outputs:
- `orchestrator.json`
- `global_packet.json`
- `claims_packet.json`
- `reporting_packet.json`
- `workflow_packet.json`
- `forms_batch_packet.json`
- `packet_metrics.json` for evaluation and regression only

Optional grouped packet:
- `batch-packet-01.json` when multiple public issue forms should be reviewed together

## Public Surface

The current repo-facing public surface is:
- release and player-facing copy: `README.md`, `PublishConfiguration.xml`
- diagnostics and telemetry docs: `LOG_REPORTING.md`, `PERF_REPORTING.md`
- contributor and maintainer public workflow docs: `CONTRIBUTING.md`, `MAINTAINING.md`, `.github/pull_request_template.md`, `.github/workflows/release.yml`
- public investigation docs and public issue forms under `.github/`

## Ownership Rules

Packet ownership is:
- `claims_packet`
  - runtime defaults, shipped behavior, README status, publish copy
- `reporting_packet`
  - diagnostics contract, performance telemetry, evidence schema/workflow docs
- `workflow_packet`
  - contributor, maintainer, PR, and release workflow docs
- `forms_batch_packet`
  - public issue templates, especially reporting or release intake forms

When source changes are broad, prefer activating one packet per concern instead of letting one packet absorb unrelated doc review.

Each packet may also carry a `github_evidence_slice` narrowed to its owned surface:
- `claims_packet`
  - shipped behavior, naming, defaults, release copy, and linked PR or issue evidence
- `reporting_packet`
  - diagnostics, telemetry, investigation workflow, and reporting-form evidence
- `workflow_packet`
  - contributor, maintainer, PR, and release workflow evidence
- `forms_batch_packet`
  - public issue-template wording or metadata evidence

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
- `claims_packet -> large_diff_auditor, repo_mapper`
- `reporting_packet -> evidence_summarizer`
- `workflow_packet -> docs_verifier`
- `forms_batch_packet -> docs_verifier`
- `batch-packet-01 -> docs_verifier` when grouped forms review is active

Rules:
- `packet_worker_map` is the routing authority
- `worker_selection_guidance` is explanatory only
- routed worker budgets still follow `local-only`, `targeted-delegation`, and `broad-delegation`
- runtime packets stay lean; token and size counters belong in `packet_metrics.json` or evaluation logs, not in `orchestrator.json`

## Ref Discovery And Remote Evidence

Collector ref discovery precedence is:
- explicit `--since-ref`
- reusable saved marker range
- current HEAD merge commit for `Merge pull request #N ...`
- current branch open PR
- current branch versus upstream/default branch merge-base
- full audit fallback

When the selected relevant ref is PR-backed and the repo has a GitHub remote:
- `gh auth status` must succeed before the run continues
- the collector fails closed on invalid auth instead of running with partial remote evidence
- evidence scope stays narrow:
  - primary PR only
  - linked issues that the PR closes
  - repository discussions directly referenced from the PR or linked issues
  - recent top-level comments and review summaries stored as digests

## Deterministic Findings

The lint step emits only these classifications:
- `hard_drift`
  - deterministic default mismatch, missing expected review doc, or similar direct mismatch
- `review_required`
  - mapped code or workflow surfaces changed without corresponding public-doc changes since the baseline, including docs-relevant GitHub evidence tied to the selected change unit
- `link_error`
  - broken relative links in public docs or public forms
- `stale_baseline`
  - saved marker could not be reused safely; the collector may still auto-discover a narrower relevant ref before falling back to a full audit

Focused packet outputs must make the common path decision-ready:
- `ownership_summary`
- `deterministic_action_candidates`
- `manual_review_residuals`
- `marker_gate_signals`
- `github_evidence_slice`

These fields should be sufficient for common-path local review. Raw reread is allowed only for explicit edge cases, not as compensation for thin packet content.

## Plan Contract

The local plan file passed to `apply_public_docs_sync.py` must contain:
- `context_id`
- `context_fingerprint`
- `overall_confidence`
- `doc_update_status`
  - allowed marker-update values: `completed` or `noop`
- `allow_marker_update`
- `actions`
- `stop_reasons`

Recommended optional fields:
- `marker_reason`
- `selected_packets`
- `remaining_manual_reviews`

Action intent is validator-owned:
- every action is classified as either `deterministic-edit` or `manual-only-review`
- only the deterministic-edit subset can reach apply
- manual-only-review actions and `remaining_manual_reviews` block marker updates but do not automatically block deterministic edits
- action `details` must stay narrowly scoped enough for deterministic execution

## Phase Field Tables

### Draft Plan

Top-level fields:
- required
  - `context_id`
  - `context_fingerprint`
  - `overall_confidence`
  - `doc_update_status`
  - `allow_marker_update`
  - `actions`
  - `stop_reasons`
- allowed
  - `marker_reason`
  - `selected_packets`
  - `remaining_manual_reviews`
- ignored
  - none

Action-entry fields:
- required
  - `type`
  - `summary`
- allowed
  - `path`
  - `details`
- ignored
  - none

### Validator Output

`validate_public_docs_sync.py` must emit:

- `valid`
- `can_apply`
- `can_update_marker`
- `errors`
- `warnings`
- `error_details`
- `warning_details`
- `stop_reasons`
- `normalized_plan`
- `normalized_plan_fingerprint`
- `context_file_fingerprint`
- `apply_context_snapshot`
- `apply_context_snapshot_fingerprint`
- `deterministic_actions`
- `manual_review_actions`
- `action_summary`
- `apply_gate_status`

Unknown extra plan fields must be removed during normalization and surfaced through fixed warning codes.

`apply_context_snapshot` must stay minimal. It exists only to let apply recheck HEAD and write the marker without reopening the full collected context. It should include:
- `repo_root`
- `state_file`
- `context_id`
- `context_fingerprint`
- `head_commit`
- `repo_hash`
- `repo_slug`
- `branch`
- `baseline_commit`
- `relevant_ref`
- `primary_pr_number`
- `primary_pr_url`
- `github_evidence_digest`
- `ref_selection_source`
- `audited_doc_paths`

`apply_gate_status` must distinguish:
- deterministic-edit safety
- marker-update safety
- explicit local hard stop categories, including:
  - `narrative_drift_remaining`
  - `deterministic_scope_exceeded`
  - `marker_update_without_doc_completion`
  - `stale_marker_context`

## Apply Contract

`scripts/apply_public_docs_sync.py` applies deterministic public-doc edits first, then persists the last-success marker only when the marker gate is clear.

- Apply consumes validator output, not raw plan JSON.
- Apply consumes `--validation` only. It does not reopen the collected context JSON.
- `--dry-run` follows the same rule and must read the validator-produced `normalized_plan`.
- Apply must compare the validator fingerprints and the current repo HEAD before writing repo files or the marker.
- Apply must consume the validator-classified deterministic-edit subset only.
- Apply must never perform manual-only-review or narrative actions.

It must refuse deterministic edits when:
- the plan fingerprint does not match the collected context
- the validator marks the deterministic edit gate as failed
- the validator reports `deterministic_scope_exceeded`
- the validator reports `stale_marker_context`
- required GitHub evidence is missing for the selected change unit

It must refuse marker updates when:
- deterministic edits failed
- `allow_marker_update` is not true
- `doc_update_status` is not `completed` or `noop`
- `overall_confidence` is `low`
- any manual-only-review or narrative residual remains
- the validator reports `marker_update_without_doc_completion`
- the validator reports `narrative_drift_remaining`

The written marker should capture:
- repo identity
- repo slug
- branch
- baseline commit
- current head commit
- selected relevant ref
- primary PR number and URL when present
- GitHub evidence digest
- ref-selection source
- context fingerprint
- audited doc paths
- active packets
- save timestamp

## Evaluation-Side Metrics

`packet_metrics.json` is evaluation-only and should contain:
- `packet_count`
- `packet_size_bytes`
- `largest_packet_bytes`
- `largest_two_packets_bytes`
- `estimated_local_only_tokens`
- `estimated_packet_tokens`
- `estimated_delegation_savings`

These numbers support regression tracking. They are not runtime branching inputs.

## Apply Boundaries

Allowed deterministic apply categories:
- settings-table default sync
- relative-link fixes
- simple public doc list or reference sync
- issue-template metadata sync

Do not treat these as deterministic:
- release status claims
- investigation conclusions
- evidence-strength or experiment-status prose

## Fixed Codes

Validator warning codes:

- `W_PLAN_UNKNOWN_TOP_LEVEL_FIELD`
- `W_PLAN_UNKNOWN_ACTION_FIELD`
- `W_PLAN_ACTION_STRING_NORMALIZED`

Validator error codes:

- `E_PLAN_MISSING_FIELD`
- `E_PLAN_CONTEXT_ID_MISMATCH`
- `E_PLAN_CONTEXT_FINGERPRINT_MISMATCH`
- `E_PLAN_HEAD_CHANGED`
- `E_PLAN_AMBIGUOUS_SELECTED_PACKET`
- `E_PLAN_MISSING_REQUIRED_EVIDENCE`
- `E_PLAN_DETERMINISTIC_SCOPE_EXCEEDED`
- `E_PLAN_STALE_MARKER_CONTEXT`
