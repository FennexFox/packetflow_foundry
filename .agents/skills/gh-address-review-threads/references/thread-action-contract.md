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
  - `skip`: ignore explicit id

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
- `stale_context_fingerprint`

## Apply Boundary

- `apply_thread_action_plan.py` must consume only the normalized validator output
- raw `thread_actions` JSON is never a valid apply input
- `apply --dry-run` follows the same rule and must not bypass normalization
- apply must stop when the normalized plan `context_fingerprint` does not match the current context
