# Commit Reword Evaluation Contract

Use this file for `reword-recent-commits` evaluation logs.

## Recommended Skill-Specific Fields

- `branch`
- `count`
- `rules_reliability`
- `commit_packet_count`
- `delegation_non_use_cases`
- `common_path_sufficient`
- `raw_reread_count`
- `validation_commands`
- `new_head`
- `applied_commit_hashes`
- `force_push_needed`
- `cleanup_succeeded`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `build`
  - record `commit_packet_count`, `delegation_non_use_cases`,
    `common_path_sufficient`, and `raw_reread_count`
  - keep packet sizing and packet-compaction telemetry in shared `packet_sizing`
    and `efficiency` fields
- `validate`
  - record `validation_commands` and any updated `rules_reliability`
- `apply`
  - record `new_head`, `applied_commit_hashes`, `force_push_needed`, and
    `cleanup_succeeded`

## Logging Rules

- Keep raw commit bodies and packet bodies out of the evaluation log.
- Prefer counts, booleans, enums, and short lists over prose summaries.
