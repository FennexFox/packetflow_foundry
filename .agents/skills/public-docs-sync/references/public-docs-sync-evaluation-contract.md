# Repo Public Docs Sync Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep public-docs-specific metrics under `skill_specific.data`.

## Skill-Specific Focus

Record the signals that matter for recurring public-doc audits:
- baseline mode and fallback reason
- review mode and packet mix
- active packet count and names
- deterministic finding counts by classification
- auto-apply candidate count
- deterministic edit count versus manual-review count
- marker write status
- packet metrics and estimated delegation savings

## Skill-Specific Data

Keep these values when they are available:
- `baseline_mode`
- `baseline_fallback_reason`
- `review_mode`
- `selected_packets`
- `active_packets`
- `worker_count`
- `worker_mix`
- `hard_drift_count`
- `review_required_count`
- `link_error_count`
- `stale_baseline_count`
- `auto_apply_candidate_count`
- `deterministic_edit_count`
- `manual_review_count`
- `plan_overall_confidence`
- `allow_marker_update`
- `marker_update_attempted`
- `marker_update_written`
- `marker_written`
- `stop_reasons`
- `packet_count`
- `packet_size_bytes`
- `largest_packet_bytes`
- `largest_two_packets_bytes`
- `estimated_local_only_tokens`
- `estimated_packet_tokens`
- `estimated_delegation_savings`

## Phase Guidance

- `init`
  - capture the collected context, selected baseline, and packet orchestration snapshot
- `phase`
  - record lint results, build-result packet metrics, and any apply dry-run or marker-write results
- `finalize`
  - record final packet usage, marker status, and observed versus estimated savings when available
