# Release Copy Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep
release-copy-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `base_tag`
- `evidence_gate_status`
- `publish_fields_changed`
- `readme_sections_changed`
- `release_issue_created`
- `qa_required`
- `qa_reason`
- `qa_ran`
- `validation_commands`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `build`
  - merge build-result review-mode metadata into the shared envelope
  - update `qa_required` and `qa_reason` from `qa_gate_guidance`
  - keep packet sizing and packet-compaction telemetry in shared `packet_sizing`
    and `efficiency` fields, with `packet_sizing.json` as evaluation-only sidecar
- `validate`
  - record `qa_required`, `qa_reason`, `qa_ran`, and `validation_commands`
- `apply` or `finalize`
  - record whether release issue creation actually completed

## Logging Rules

- Keep publish payload bodies and README bodies out of the evaluation log.
- Prefer booleans, enums, counts, and short lists over free-form prose.
- Treat packet-compaction numbers as estimated evaluation telemetry, not runtime
  routing inputs.
