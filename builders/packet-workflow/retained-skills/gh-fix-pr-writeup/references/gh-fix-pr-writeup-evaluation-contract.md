# PR Writeup Evaluation Contract

Use the shared envelope in [`evaluation-log-contract.md`](evaluation-log-contract.md)
and keep PR-writeup-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `title_changed`
- `body_changed`
- `template_sections_required`
- `template_sections_filled`
- `rewrite_strategy`
- `qa_required`
- `qa_reason`
- `qa_ran`
- `validation_commands`
- `edited_pr_url`
- `delegation_non_use_cases`
- `common_path_sufficient`
- `raw_reread_count`
- `unsupported_claim_categories`
- `evidence_gap_categories`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Build-Phase Guidance

Build-phase merge should update:
- `rewrite_strategy`
- `qa_required`
- `qa_reason`
- `delegation_non_use_cases`
- `common_path_sufficient`
- `raw_reread_count`

Packet sizing and packet-compaction telemetry should stay in shared
`packet_sizing` and `efficiency` fields, with `packet_sizing.json` as an
evaluation-only sidecar when present.

## Validation And Apply Signals

- `validate`
  - update `qa_required`, `qa_reason`, and `validation_commands`
- `apply`
  - update whether QA actually ran and the final edited PR URL when available

## Logging Rules

- Keep packet bodies and rendered PR body text out of the evaluation log.
- Prefer enums, counts, booleans, and short reason strings over prose.
