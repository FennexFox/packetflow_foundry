# PR Writeup Evaluation Contract

Use the shared envelope in [`evaluation-log-contract.md`](evaluation-log-contract.md) and keep PR-writeup-specific metrics under `skill_specific.data`.

## Required Skill-Specific Fields

- `review_mode`
- `packet_count`
- `worker_count`
- `rewrite_strategy`
- `qa_required`
- `qa_reason`
- `qa_ran`
- `validation_commands`
- `edited_pr_url`
- `common_path_sufficient`
- `raw_reread_count`
- `estimated_packet_tokens`
- `estimated_delegation_savings`
- `unsupported_claim_categories`
- `evidence_gap_categories`

## Build-Phase Metrics

Build-phase merge should populate:
- `packet_count`
- `rewrite_strategy`
- `qa_required`
- `qa_reason`
- `common_path_sufficient`
- `raw_reread_count`
- `estimated_packet_tokens`
- `estimated_delegation_savings`

It should also update baseline byte-proxy fields when `packet_metrics.json` is available:
- `baseline.estimated_local_only_tokens`
- `baseline.estimated_token_savings`
- `baseline.estimated_delegation_savings`

## Validation / Apply Signals

- `validation_commands`
  - concrete checks that actually ran before guarded mutation
- `qa_ran`
  - true only when a QA-required draft was actually cleared or reviewed
- `edited_pr_url`
  - final PR URL after a successful edit or dry-run confirmation path

## Logging Rules

- Keep packet bodies out of the evaluation log.
- Keep runtime routing metadata separate from packet-size and token-efficiency metrics.
- Prefer enums, counts, booleans, and short reason strings over free-form summaries.
- Treat token-efficiency numbers as estimated byte-proxy regression metrics, not runtime routing inputs.
