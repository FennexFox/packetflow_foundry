# Address Review Threads Evaluation Contract

Use the shared envelope in [`evaluation-log-contract.md`](evaluation-log-contract.md) and keep workflow-specific metrics under `skill_specific.data`.

## Recommended Domain Fields

Record only workflow-specific counters and boundary signals that do not fit cleanly in the shared envelope.

Recommended fields:
- `pr_number`
- `review_mode`
- `packet_count`
- `worker_count`
- `thread_batch_count`
- `singleton_thread_packet_count`
- `common_path_sufficient`
- `threads_seen`
- `threads_accepted`
- `threads_rejected`
- `threads_deferred`
- `threads_defer_outdated`
- `threads_resolved`
- `outdated_threads_seen`
- `marker_conflicts`
- `marker_conflicts_warning`
- `marker_conflicts_adoption_blocking`
- `marker_conflicts_hard_stop`
- `adopted_unmarked_reply_count`
- `skipped_outdated_count`
- `invalid_complete_count`
- `resolve_after_complete_count`
- `validation_commands`
- `final_pr_url`
- `estimated_packet_tokens`
- `estimated_delegation_savings`

## Thread Decision Metrics

Track the per-run decision counts separately from the raw thread total.

- `threads_seen`
  - total unresolved threads seen at collection time
- `threads_accepted`
  - threads that reached implementation and completion
- `threads_rejected`
  - threads the main agent explicitly rejected
- `threads_deferred`
  - threads intentionally left unresolved for now
- `threads_defer_outdated`
  - threads deferred because the reviewer comment is stale against current `HEAD`
- `threads_resolved`
  - threads actually resolved after completion

## Boundary Signals

- `outdated_threads_seen`
  - count unresolved outdated threads surfaced by collection
- `marker_conflicts`
  - count threads with existing managed-reply marker conflicts
- `marker_conflicts_warning`
  - count warning-only conflict records
- `marker_conflicts_adoption_blocking`
  - count adoption-blocking conflict records
- `marker_conflicts_hard_stop`
  - count hard-stop conflict records

## Validator And Apply Counters

- `adopted_unmarked_reply_count`
  - count updates that safely reused the validator fallback from an unmarked self-authored reply
- `skipped_outdated_count`
  - count actions normalized to `decision=defer-outdated`
- `invalid_complete_count`
  - count invalid complete-phase attempts rejected by validation
- `resolve_after_complete_count`
  - count accepted complete actions that requested thread resolution

## Expected Behavior

- Keep full thread discussion bodies out of the evaluation log unless a debugging path explicitly requires them.
- Prefer counts, booleans, enums, and short reason lists over free-form summaries.
- Keep the contract aligned with the local reply markers, per-thread decision model, and push-before-complete rule.
- Build-phase review mode, worker derivation, packet/thread counts, and `common_path_sufficient` come from the build result JSON.
- Size and token-proxy metrics come only from `packet_metrics.json`.
- `packet_metrics.json` is evaluation-only and must not be treated as a runtime routing source.
