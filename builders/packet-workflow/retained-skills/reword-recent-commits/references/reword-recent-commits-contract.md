# Reword Recent Commits Contract

Use this file when drafting, validating, or evaluating the rewrite workflow built from `scripts/collect_recent_commits.py`.

The authoritative runtime source is `scripts/reword_plan_contract.py`.

## Packet Interface

- This workflow stays flat/generic by design:
  - `decision_ready_packets=false`
  - `worker_return_contract=generic`
  - `worker_output_shape=flat`
- Workers read `global_packet.json` first, then `rules_packet.json` or one `commit-XX.json` packet.
- The common path is `rules_packet.json + one commit packet at a time`.
- `raw_reread_reasons` must use only the enum from `scripts/reword_plan_contract.py`.
- This pass is a metadata/doc refresh; naming migration for `task_packet_names` and `task_packet_ids` is intentionally out of scope.

## Build Artifacts

`scripts/build_reword_packets.py` produces:

- collected input:
  - `plan.json` from `collect_recent_commits.py`
  - `rules.json` from `collect_commit_rules.py`
- packet artifacts:
  - `global_packet.json`
  - `rules_packet.json`
  - `commit-XX.json`
  - `orchestrator.json`
  - `packet_metrics.json`
- optional build artifact:
  - `build-result.json` when `--result-output` is supplied

## Builder Metadata

`global_packet.json` and `orchestrator.json` should carry the shared builder metadata from `scripts/reword_plan_contract.py`:

- flat/generic contract fields
- `common_path_contract`
- `task_packet_names`
- `task_packet_ids`
- `packet_worker_map`
- `preferred_worker_families`
- `worker_selection_guidance`
- `worker_output_fields`
- `reread_reason_values`
- `packet_metric_fields`
- `xhigh_reread_policy`

## Collected Plan Shape

Top-level fields:

- `repo_root`
- `branch`
- `detached_head`
- `count`
- `head_commit`
- `base_commit`
- `active_operation`
- `context_fingerprint`
- `rules_reliability`
- `commits`

Each item in `commits` must include:

- `index`
- `hash`
- `short_hash`
- `parent_hashes`
- `subject`
- `body`
- `full_message`
- `author_name`
- `author_email`
- `author_date`
- `files`
- `shortstat`
- `new_message`

## Build Result Shape

`build-result.json` must expose:

- `review_mode`
- `recommended_worker_count`
- `recommended_workers`
- `packet_files`
- `active_packets`
- `active_packet_count`
- `commit_packet_count`
- `applied_override_signals`
- `common_path_sufficient`
- `raw_reread_count`
- `raw_reread_reasons`
- `packet_metrics`

`packet_metrics` must use this calculation policy:

- local-only baseline: `rules.json + collected plan.json`
- packet-path estimate: `rules_packet.json + largest commit packet`
- `global_packet.json` is not part of the packet-path estimate

## Validation Envelope

`scripts/validate_reword_plan.py` must emit:

- `valid`
- `errors`
- `warnings`
- `counters`
- `context_fingerprint`
- `message_set_fingerprint`
- `normalized_rewrite_actions`

`normalized_rewrite_actions` entries keep:

- `index`
- `hash`
- `new_message`

They must always sort by:

- `index`
- `hash`

## Apply Boundary

- `scripts/apply_reword_plan.py` consumes only the validated envelope plus the collected context file.
- Raw drafted plans are never valid apply input.
- `--dry-run` must follow the same validation boundary and return structured operations without moving refs.
- Apply must reject stale `context_fingerprint` values and keep the branch ref unchanged on replay failure.
- Temp worktree removal and temp dir cleanup must always be attempted and reported in the result payload.

## Rewrite Expectations

- Keep commits in oldest-to-newest order.
- Treat `new_message` as empty until the replacement message is drafted.
- Stop when a target commit is a merge commit.
- Stop when the branch tip moved or another git operation is already in progress.
- `base_commit=null` is a collect-time exception shape only; validator and apply must fail it with `root_rewrite_unsupported`.
- Preserve the real behavior and intent of each original commit even when the wording changes.
