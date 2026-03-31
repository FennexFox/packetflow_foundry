# Review Threads Contract

This file defines the packet, worker, and reply contract for the `gh-address-review-threads` skill.

For the workflow-shape rationale and the criteria for revisiting hierarchy, read [`architecture-note.md`](architecture-note.md).

## Builder Metadata

- `workflow_family`: `github-review`
- `archetype`: `audit-and-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

## Required Packet Outputs

- `orchestrator.json`
- `global_packet.json`
- `thread-batch-*.json` when clustered non-outdated threads share one fix surface
- `thread-*.json` for every unresolved thread

## Canonical Context Fields

- `context_fingerprint`
  - top-level collect fingerprint for the current unresolved-thread snapshot
  - must match across collect, build, validate, and apply in one run
- `reply_candidates`
  - canonical shape:
```json
{
  "ack": {
    "mode": "add|update",
    "comment_id": "123",
    "reason": "exact_managed_reply|adopt_latest_unmarked_reply_after_reviewer|no_existing_ack_reply",
    "managed": true,
    "adopted_unmarked_reply": false
  },
  "complete": {
    "mode": "add|update",
    "comment_id": "456",
    "reason": "exact_managed_reply|complete_never_adopts_unmarked_reply",
    "managed": true,
    "adopted_unmarked_reply": false
  }
}
```
- `marker_conflicts`
  - canonical shape is a severity-bearing object list
  - fields:
    - `phase`
    - `severity`
    - `reason`
    - `comment_ids`
    - `blocks_adoption`
    - `blocks_update`
    - `blocks_apply`

## Authority Order

Use evidence in this order:
- the current PR thread discussion and latest reviewer request
- current `HEAD` code and directly inspected diff slices
- managed reply markers and current self-authored replies
- repository PR guidance and validation output
- packet summaries and worker findings

## Worker Routing Metadata

- `packet_worker_map`
  - each delegated `thread-batch-*` packet routes to `packet_explorer`
  - each delegated non-outdated singleton `thread-*` packet routes to `packet_explorer`
- optional QA pass
  - `large_diff_auditor`

Rules:
- `packet_worker_map` is the routing authority for delegated thread analysis
- `preferred_worker_families` is registry metadata only
- `recommended_workers` and `optional_workers` are derived convenience fields only
- final per-thread decisions, reply wording, pushes, and resolution stay local
- runtime logic must never infer routing from `preferred_worker_families` or `optional_workers`

## Common-Path Contract

- default local adjudication basis:
  - `global_packet.json + one thread-batch packet`
  - `global_packet.json + one thread packet`
- allowed reread reasons:
  - `conflicting_signals`
  - `missing_required_evidence`
  - `insufficient_excerpt_quality`
  - `ownership_ambiguity`
  - `stale_context`
- `common_path_sufficient == true` only when all of these hold:
  - required evidence is present inside the packet set used for the decision
  - ownership ambiguity stays below the escape threshold
  - no explicit reread or escape reason is required
  - a validator-ready recommendation path is closed from packet contents alone
- `review_mode_overrides` may widen worker recommendation or review mode, but they must not upgrade missing evidence, ownership ambiguity, or reread need into `common_path_sufficient=true`
- `quality_escape_hints` is advisory only; explicit reread or escape decisions must still use the allowed reason enum or an explicit stop

## Marker Conflict Stop Rules

| Severity | Meaning | Validate | Apply |
|---|---|---|---|
| `warning` | latest exact managed target is unique and older duplicates remain | allow, record warning | allow |
| `adoption-blocking` | unmarked reply adoption path is unsafe | block adoption-based fallback update only | same |
| `hard-stop` | target ambiguity or marker corruption | block any non-`skip` action for the phase | same |

Notes:
- `adoption-blocking` does not block `add`.
- `adoption-blocking` allows `update` only when an explicit comment id targets the current exact managed reply.
- `hard-stop` allows only `skip` for the affected phase.

## Global Packet Semantics

Keep shared workflow facts here:
- PR identity and URL
- reply marker policy
- outdated-thread policy
- code-change delegation guardrails
- disallowed claims
- diff summary and review overrides
- `context_fingerprint`
- `marker_conflict_summary`
- `preferred_worker_families`
- `packet_worker_map`
- `routing_contract`

## Thread Packet Semantics

Each `thread-*.json` packet keeps:
- thread identity and path
- reviewer comment summary
- existing self reply and managed reply candidates
- canonical `marker_conflicts`
- file snippet and diff snippet
- small-fix applicability hints
- `validation_candidates`
- `ownership_summary`
- `reply_update_basis`
- `quality_escape_hints`

Each `thread-batch-*.json` packet keeps:
- batch identity and clustering reason
- shared file context
- grouped thread ids
- one narrow fix surface that can be analyzed together
- `shared_fix_surface`
- `validation_candidates`
- `quality_escape_hints`

## Runtime Vs Eval Artifacts

- runtime contract:
  - `orchestrator.json`
  - `global_packet.json`
  - `thread-batch-*.json`
  - `thread-*.json`
- eval-side artifacts:
  - build result JSON for review mode, worker derivation, packet/thread counts, override signals, and `common_path_sufficient`
  - `packet_metrics.json` for size and token-proxy metrics only
- do not duplicate token-efficiency counters into runtime packets

## Smoke Modes

- live operator smoke:
  - uses the current-branch PR
  - may return `blocked` or `noop` with the fixed `status/reason/thread_counts/next_action` schema
- synthetic reference smoke:
  - uses a temp fixture and no live GitHub state
  - must exercise collect-equivalent context, build, validate, apply `--dry-run`, and evaluation merge end to end
- both smoke modes keep the short summary schema at the top level

## Reply And Resolution Rules

- `ack`
  - summarize the reviewer request
  - state accept, reject, defer, or defer-outdated
  - state the implementation direction or blocker
- `complete`
  - summarize what changed
  - list validation that actually ran
  - note the remaining caveat only if it matters

Resolve only accepted threads after the relevant change is pushed and validation is complete.

## Thread Action Validation

- raw `thread_actions` must be normalized before apply
- normalized actions are sorted by:
  - `path`
  - `line or original_line or 0`
  - `thread_id`
- `apply_thread_action_plan.py` consumes only the normalized validator output
- `update` requires:
  - explicit `*_comment_id`, or
  - `reply_candidates.<phase>.comment_id` fallback
- `update` with no explicit or fallback id fails with:
  - `missing_update_target`
