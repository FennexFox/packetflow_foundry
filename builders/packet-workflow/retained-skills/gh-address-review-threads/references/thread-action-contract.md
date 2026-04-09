# Thread Action Contract

This file defines the canonical `thread_actions` contract shared by the validator, apply script, tests, and smoke workflows.

For the rationale behind keeping the workflow flat/generic, read [`architecture-note.md`](architecture-note.md).

## Source Of Truth

- `scripts/thread_action_contract.py`
  - canonical field policy
  - canonical validation codes
  - context fingerprint rules
  - deterministic action ordering

## Phase Field Policy

`ack`
- mode field: `ack_mode`
- body field: `ack_body`
- comment id field: `ack_comment_id`
- allowed modes: `add`, `update`, `skip`
- body required for: `add`, `update`
- comment id rules:
  - `add`: ignore explicit id
  - `update`: use explicit id first, then `reply_candidates.ack.comment_id`
  - `skip`: ignore explicit id and preserve only the latest exact managed `ack` reply target
- extra rules:
  - `ack_mode=add` and `ack_mode=update` require an explicit parseable decision line in `ack_body`
  - that explicit `ack_body` decision line must match the plan `decision`
  - `skip` is valid only when the thread already has a latest exact managed `ack` reply
  - the current exact managed `ack` reply must already encode the same decision as the plan on an explicit decision line
    such as `defer`, `defer until rerun`, or `Decision: defer until rerun`; otherwise use `update`
  - adoptable unmarked replies may be used as `update` fallback targets, but never as `skip` targets

`complete`
- mode field: `complete_mode`
- body field: `complete_body`
- comment id field: `complete_comment_id`
- allowed modes: `add`, `update`, `skip`
- body required for: `add`, `update`
- comment id rules:
  - `add`: ignore explicit id
  - `update`: use explicit id first, then `reply_candidates.complete.comment_id`
  - `skip`: ignore explicit id
- extra rules:
  - `complete` actions are valid only for `decision=accept`
  - `resolve_after_complete` is valid only when `complete_mode != skip`

## Deterministic Ordering

Normalized actions must always sort by:
- `path`
- `line or original_line or 0`
- `thread_id`

This ordering uses the current context thread metadata, not the input plan order.

## Warning Codes

- `unknown_action_field_ignored`
- `ignored_comment_id_for_add`
- `ignored_comment_id_for_skip`
- `ignored_body_for_skip`
- `ignored_resolve_after_complete_outside_complete`

## Error Codes

- `invalid_plan_shape`
- `missing_thread_id`
- `unknown_thread_id`
- `invalid_decision`
- `invalid_mode`
- `missing_required_body`
- `missing_update_target`
- `invalid_complete_for_non_accept`
- `invalid_resolve_after_complete`
- `adoption_blocked_update`
- `hard_stop_marker_conflict`
- `missing_exact_managed_skip_target`
- `non_exact_reply_candidate_for_skip`
- `missing_exact_managed_skip_decision`
- `mismatched_exact_managed_skip_decision`
- `missing_ack_body_decision`
- `mismatched_ack_body_decision`
- `stale_context_fingerprint`

## Apply Boundary

- `apply_thread_action_plan.py` must consume only the normalized validator output
- raw `thread_actions` JSON is never a valid apply input
- `apply --dry-run` follows the same rule and must not bypass normalization
- apply must stop when the normalized plan `context_fingerprint` does not match the current context
