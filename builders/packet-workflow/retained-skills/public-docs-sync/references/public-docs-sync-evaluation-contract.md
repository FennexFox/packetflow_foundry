# Repo Public Docs Sync Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep
public-docs-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `hard_drift_count`
- `review_required_count`
- `link_error_count`
- `stale_baseline_count`
- `auto_apply_candidate_count`
- `selected_packets`
- `deterministic_edit_count`
- `manual_review_count`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `init`
  - capture collected lint classifications and selected packet metadata
- `build`
  - update `selected_packets` and `auto_apply_candidate_count`
  - keep packet sizing and packet-compaction telemetry in the shared envelope
- `finalize`
  - record actual token usage and cost-equivalent telemetry through shared fields

## Logging Rules

- Keep document bodies out of the evaluation log unless a debug path explicitly
  requires them.
- Prefer counts, booleans, enums, and short reason lists over prose.
