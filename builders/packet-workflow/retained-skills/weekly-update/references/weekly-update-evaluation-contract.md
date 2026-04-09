# Weekly Update Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep
workflow-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `reporting_window`
- `review_mode`
- `selected_packets`
- `candidate_counts_by_proposed_classification`
- `raw_reread_reason_counts`
- `raw_reread_count`
- `coverage_gap_count`
- `common_path_sufficient`
- `plan_overall_confidence`
- `allow_marker_update`
- `marker_update_attempted`
- `marker_update_written`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `build`
  - merge selected packets, candidate classification counts, raw-reread reason
    counts, coverage-gap counts, and `common_path_sufficient`
  - keep packet sizing and packet-compaction telemetry in shared `packet_sizing`
    and `efficiency` fields
- `validate`
  - record `plan_overall_confidence` and `allow_marker_update`
- `apply`
  - record `marker_update_attempted` and `marker_update_written`

## Logging Rules

- Keep full candidate bodies and final weekly-update text out of the evaluation
  log unless a debug path explicitly requires them.
- Prefer counts, booleans, enums, and short reason lists over prose.
