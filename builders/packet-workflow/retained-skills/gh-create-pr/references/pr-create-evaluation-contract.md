# Gh Create Pr Evaluation Contract

Use the shared evaluation envelope in [evaluation-log-contract.md](./evaluation-log-contract.md)
and keep create-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `title_changed`
- `body_changed`
- `template_sections_required`
- `template_sections_filled`
- `unsupported_claim_categories`
- `evidence_gap_categories`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Expectations

- `build`
  - may contribute packet sizing, packet-compaction telemetry, and
    `common_path_sufficient` through the shared envelope
- `lint`
  - should populate unsupported-claim and evidence-gap categories
- `validate` and `apply`
  - should continue to rely on shared quality and safety fields for status,
    validation state, stop reasons, and artifact URL

## Notes

- Keep the contract aligned with the guarded PR-create workflow, not the
  PR-writeup edit workflow.
- `packet_sizing.json` is evaluation-only and should not be mirrored into
  `skill_specific.data`.
