# Weekly Update Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep workflow-specific metrics under `skill_specific.data`.

## Recommended Domain Fields

Record only workflow-specific counters and boundary signals that do not fit cleanly in the shared envelope.

Recommended fields:
- `reporting_window`
- `review_mode`
- `selected_packets`
- `worker_count`
- `worker_mix`
- `worker_packet_usage`
- `worker_footer_confidences`
- `candidate_counts_by_proposed_classification`
- `candidate_counts_by_final_section`
- `raw_reread_reason_counts`
- `raw_reread_count`
- `proposal_override_count`
- `coverage_gap_count`
- `packet_count`
- `estimated_packet_tokens`
- `estimated_delegation_savings`
- `common_path_sufficient`
- `stop_reasons`
- `plan_overall_confidence`
- `allow_marker_update`
- `marker_update_attempted`
- `marker_update_written`

## Candidate And Plan Metrics

Track proposal-stage and final-plan metrics separately.

- `candidate_counts_by_proposed_classification`
  - count worker or collector proposals before final adjudication
- `candidate_counts_by_final_section`
  - count only final section placements after local adjudication
- `proposal_override_count`
  - count candidates whose final local classification or section placement differs materially from the worker proposal
- `raw_reread_reason_counts`
  - count exception-path candidates by reread reason

## Confidence Semantics

- `worker_footer_confidences`
  - record worker-level `overall_confidence` values for each worker response when workers were used
- `plan_overall_confidence`
  - record the final run-level confidence from `weekly-update-plan.json`
  - this is the confidence the apply step uses

Do not treat worker-footer confidence as the final apply gate by itself.

## Marker Update Semantics

Record marker-update outcomes explicitly:
- `allow_marker_update`
  - final gate from `weekly-update-plan.json`
- `marker_update_attempted`
  - whether the apply step attempted a state write
- `marker_update_written`
  - whether the last-success marker was actually updated

If marker update is skipped, capture the reason in `stop_reasons` or a short workflow-specific note.

## Build-Phase Metrics

`build_weekly_update_packets.py --result-output` is the source for build-phase evaluation merge.

- merge `packet_metrics.json` and the build result during `write_evaluation_log.py phase --phase build`
- keep token-efficiency counters out of runtime packets
- treat `common_path_sufficient` and `raw_reread_count` as packet-quality regression signals, not as runtime routing inputs

## Expected Behavior

- Keep full candidate bodies out of the evaluation log unless a debugging path explicitly requires them.
- Prefer counts, booleans, enums, and short reason lists over free-form summaries.
- Keep `coverage_gap_count` focused on unread or insufficiently verified scope, not on ordinary low-priority follow-ups.
- Keep the evaluation contract aligned with the worker proposal model, packet membership tracking, and the plan-driven apply gate.
- `scripts/apply_weekly_update.py` should read only `weekly-update-plan.json` fields `overall_confidence`, `stop_reasons`, and `allow_marker_update`, not worker footers.
- Keep `estimated_packet_tokens` and `estimated_delegation_savings` as evaluation/regression signals only.
