# Address Review Threads Evaluation Contract

Use the shared envelope in [`evaluation-log-contract.md`](evaluation-log-contract.md)
and keep workflow-specific metrics under `skill_specific.data`.

## Recommended Skill-Specific Fields

- `threads_seen`
- `threads_accepted`
- `threads_rejected`
- `threads_deferred`
- `threads_defer_outdated`
- `threads_resolved`
- `outdated_threads_seen`
- `outdated_transition_candidates`
- `outdated_auto_resolved`
- `outdated_recheck_ambiguous`
- `adopted_unmarked_reply_count`
- `skipped_outdated_count`
- `invalid_complete_count`
- `resolve_after_complete_count`
- `common_path_sufficient`
- `build_phase_count`
- `build_phases`

## Shared Envelope Boundary

Keep these shared metrics out of `skill_specific.data`:
- `orchestration.planned_workers` and `orchestration.actual_workers`
- `packet_sizing`
- `efficiency.packet_compaction`
- `efficiency.model_tier_delegation`
- token costs under `tokens.*`

## Phase Guidance

- `build`
  - read thread counts, review-mode metadata, and `common_path_sufficient` from
    the build result
  - record per-phase packet snapshots in `build_phases`
  - keep packet sizing and token-compaction telemetry in the shared envelope
- `apply`
  - update accepted, rejected, deferred, resolved, and reconciliation counters
- `finalize`
  - record actual worker usage and any capture completeness notes through the
    shared envelope

## Logging Rules

- Keep full thread bodies and full reply bodies out of the evaluation log.
- Prefer counts, booleans, enums, and short reason lists over summaries.
- Treat `packet_sizing.json` as evaluation-only and never as runtime routing
  authority.
