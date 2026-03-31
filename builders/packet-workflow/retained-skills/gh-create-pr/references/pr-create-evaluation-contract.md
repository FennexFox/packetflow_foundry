# Gh Create Pr Evaluation Contract

Use the shared evaluation envelope in [evaluation-log-contract.md](./evaluation-log-contract.md) and keep create-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `title_changed`
- `body_changed`
- `template_sections_required`
- `template_sections_filled`
- `unsupported_claim_categories`
- `evidence_gap_categories`
- `packet_metrics`

Rules:
- `packet_metrics` comes from the build phase and stays evaluation-only
- store observed category lists, counts, and booleans instead of prose summaries
- do not mirror live validator/apply routing metadata into evaluation fields unless the value is explicitly used for regression analysis

## Phase Expectations

Build phase should be able to contribute:
- packet count and packet sizing
- common-path packet efficiency estimates
- estimated local-only versus packeted token cost

Lint phase should be able to contribute:
- unsupported-claim categories
- evidence-gap categories
- template-section coverage

Validate/apply phases should stay on the shared envelope for:
- result status
- validation/apply pass state
- stop reasons
- primary artifact URL

## Notes

- Keep the contract aligned with the guarded PR-create workflow, not the PR-writeup edit workflow.
- If the workflow later adds deterministic apply-side counters that matter for regression tracking, add them here rather than widening the shared envelope.
