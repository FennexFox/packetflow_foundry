# Commit Reword Evaluation Contract

Use this file for `reword-recent-commits` evaluation logs.

## Skill-Specific Focus

Record the signals that matter for history rewrite safety, build efficiency, and rewrite quality:

- commit count and branch identity
- planned versus applied commit hashes
- validation commands that actually ran
- whether the branch ref moved cleanly
- packet routing and flat/generic metadata
- packet-efficiency estimates from the build phase

## Skill-Specific Data

Keep these values in `skill_specific.data` when they are available:

- `branch`
- `count`
- `commit_packet_count`
- `decision_ready_packets`
- `worker_return_contract`
- `worker_output_shape`
- `base_commit`
- `head_commit`
- `new_head`
- `rewrite_mode`
- `validation_commands`
- `applied_commit_hashes`
- `rules_reliability`
- `context_fingerprint`
- `force_push_needed`
- `commits_rewritten`
- `cleanup_succeeded`
- `packet_count`
- `estimated_packet_tokens`
- `estimated_delegation_savings`
- `common_path_sufficient`
- `raw_reread_count`
- `raw_reread_reasons`

## Phase Guidance

- `init`
  - capture the collected commit plan and orchestrator snapshot
- `phase=build`
  - record `packet_metrics`
  - record `common_path_sufficient`
  - record `raw_reread_count` and `raw_reread_reasons`
  - populate baseline token estimates from the build result
- `phase=validate`
  - record `fingerprint_match`, stop reasons, and rules reliability
- `phase=apply`
  - record `new_head`, `applied_commit_hashes`, `commits_rewritten`, and cleanup outcome
- `finalize`
  - record the final rewritten tip and any remaining caution
