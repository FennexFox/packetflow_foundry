# Git Split Evaluation Contract

Use this file for `git-split-and-commit` evaluation logs.

## Recommended Skill-Specific Fields

- `commit_buckets_planned`
- `commit_buckets_applied`
- `split_file_count`
- `decision_ready_packets`
- `common_path_sufficient`
- `raw_reread_count`
- `delegation_non_use_cases`
- `targeted_checks_failed`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `build`
  - update candidate-batch counts, split-file counts, `common_path_sufficient`,
    and raw-reread counters
  - keep packet sizing and packet-compaction telemetry in shared `packet_sizing`
    and `efficiency` fields
- `apply`
  - update `commit_buckets_applied`
- `finalize`
  - record actual worker usage or final token costs only through the shared
    envelope

## Logging Rules

- Keep hunk text, commit bodies, and packet bodies out of the evaluation log.
- Prefer counters and enums over narrative summaries.
- Derive packet counts from runtime packet order only for fallback reporting,
  not as a replacement for shared `packet_sizing`.
