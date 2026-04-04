# Release Copy Evaluation Contract

Use the shared envelope in `references/evaluation-log-contract.md` and keep workflow-specific metrics under `skill_specific.data`.

## Skill-Specific Focus

Record the signals that matter for release-copy preparation:
- release tag and branch context
- review mode and packet mix
- packet count and packet-size concentration
- token-proxy savings estimates
- common-path reread behavior
- changelog rewrite scope
- release issue creation status
- project scope availability and project add policy
- local helper handoff availability

## Skill-Specific Data

Keep these values in `skill_specific.data` when they are available:
- `release_tag`
- `branch`
- `review_mode`
- `selected_packets`
- `worker_count`
- `worker_mix`
- `packet_count`
- `largest_packet_bytes`
- `largest_two_packets_bytes`
- `estimated_local_only_tokens`
- `estimated_packet_tokens`
- `estimated_delegation_savings`
- `changelog_lines`
- `publish_fields_changed`
- `readme_sections_changed`
- `release_issue_url`
- `issue_creation_status`
- `project_mode`
- `project_scope_available`
- `project_flag_used`
- `local_release_helper_status`
- `local_release_helper_handoff_available`
- `stop_reasons`
- `raw_reread_count`
- `compensatory_reread_detected`
- `deterministic_file_edit_count`
- `issue_action_attempted`

## Phase Guidance

- `init`
  - capture the release context, lint report, and packet orchestration snapshot
- `build`
  - merge the build result JSON and `packet_metrics.json` so review-mode metadata plus token-efficiency and packet-size metrics live in evaluation data instead of the runtime contract
- `phase`
  - record lint, validate, dry-run, rewrite, or issue-action results
- `finalize`
  - record the final release issue URL and the helper handoff status

## Runtime Vs Eval Reminder

- runtime packet fields belong in `orchestrator.json` and the runtime packets
- packet sizing and token-proxy metrics belong in `packet_metrics.json`
- smoke summaries should keep a short operator schema and may append additional detail fields without replacing the core smoke keys

## Safety Signals

Prefer recording these when validator/apply runs are present:
- `validation_run`
- `validation_passed`
- `fingerprint_match`
- `apply_succeeded`
- `rollback_needed`
- `mutation_type`
- `stop_reasons`
- `raw_reread_count`
- `compensatory_reread_detected`
