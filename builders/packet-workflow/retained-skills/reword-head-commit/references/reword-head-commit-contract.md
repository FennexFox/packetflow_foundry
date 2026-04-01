# Reword Head Commit Contract

The express driver writes repo-local artifacts under:

- `.codex/tmp/packet-workflow/reword-head-commit/<run-id>/`

Artifacts:
- `rules.json`
- `context.json`
- `validation.json`
- `apply-result.json`
- `eval-log.json`

Validation contract:
- reuse the `reword-recent-commits` validator for subject/type/scope/body
  checks
- extend it with one express-only hard gate:
  - `explicit_rules_required`
- keep the target fixed to exactly one collected `HEAD` commit

`validation.json` includes:
- `valid`
- `errors`
- `warnings`
- `counters`
- `context_fingerprint`
- `message_set_fingerprint`
- `normalized_rewrite_actions`
- `rewrite_scope`
- `rules_reliability`
- `force_push_likely`
- `amend_allowed`

`apply-result.json` includes:
- `status`
- `dry_run`
- `amend_succeeded`
- `validation_boundary_enforced`
- `branch`
- `head_commit`
- `new_head`
- `force_push_likely`
- `warnings`
- `stop_reasons`
- `context_fingerprint`
- `message_set_fingerprint`

Status values:
- `dry-run`
- `blocked`
- `ok`
- `failed`
