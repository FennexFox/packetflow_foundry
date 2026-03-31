# Git Split Evaluation Contract

Use this file for `git-split-and-commit` evaluation logs.

## Skill-Specific Focus

Record the signals that matter for split planning and commit application:
- bucket count and split confidence
- validation commands and targeted checks
- staged commit hashes and final head
- hunk rematch or fingerprint failures
- hard-stop category and rollback status when apply stops
- dry-run versus applied-plan outcomes
- packet routing and decision-ready metadata when available

## Skill-Specific Data

Keep these values in `skill_specific.data` when they are available:
- `commit_buckets_planned`
- `commit_buckets_applied`
- `split_file_count`
- `decision_ready_packets`
- `worker_return_contract`
- `worker_output_shape`
- `common_path_sufficient`
- `raw_reread_count`
- `raw_reread_reasons`
- `packet_count`
- `estimated_packet_tokens`
- `estimated_delegation_savings`
- Derive fallback packet counts from the file-oriented `packet_order` or `packet_files` list when explicit packet metrics are absent.
- `validation_commands`
- `targeted_checks`
- `created_hashes`
- `final_head`
- `dry_run`
- `plan_validation`
- `apply_status`
- `stop_categories`
- `rollback_status`

## Phase Guidance

- `init`
  - capture the collected worktree and packet orchestration snapshot
- `phase`
  - record build-phase packet metrics and common-path sufficiency, then validation or apply-stage results
- `finalize`
  - record the created commit hashes and any remaining apply caveat
