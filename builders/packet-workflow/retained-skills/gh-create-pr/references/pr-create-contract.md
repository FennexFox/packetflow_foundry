# Gh Create Pr Contract

This file defines the collector, packet, validator, and apply contract for `gh-create-pr`.

The shared packet-workflow core boundary lives in [core-contract.md](./core-contract.md). Repo-local bindings stay in [profile.json](../profiles/default/profile.json).

## Builder Metadata

- `workflow_family`: `github-review`
- `archetype`: `plan-validate-apply`
- `orchestrator_profile`: `packet-heavy-orchestrator`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

## Collector Contract

Collector CLI:
- `--repo-root`
- optional `--repo`
- optional `--base`
- optional `--head`
- repeated `--reviewer`
- repeated `--assignee`
- repeated `--label`
- optional `--milestone`
- optional `--draft`
- optional `--no-maintainer-edit`
- `--profile`
- `--output`

Resolution rules:
- base resolution order is `--base`, `branch.<current>.gh-merge-base`, remote default branch
- head resolution order is `--head`, current branch
- v1 stops closed when the resolved remote head does not exist

Collector output must include:
- `repo_root`
- `repo_slug`
- `resolved_base`
- `resolved_head`
- `current_branch`
- `local_head_oid`
- `remote_head_oid`
- `changed_files`
- `changed_files_fingerprint`
- `diff_stat`
- `template_selection`
- `expected_template_sections`
- `duplicate_check_hint`
- `issue_reference_hints`
- `testing_signal_candidates`
- `create_options`
- `checks`

Template selection policy:
- auto-select only a single unique default template
- fail closed with `template_not_found` when no default template exists
- fail closed with `template_ambiguous` when multiple candidates are eligible
- record `selected_path` and `fingerprint` when selection succeeds

Duplicate PR hint policy:
- authoritative duplicate key is `repo_slug + head`
- collector duplicate data is informational only
- validator and apply must both re-check live GitHub state

## Packet Contract

Required runtime outputs:
- `orchestrator.json`
- `global_packet.json`
- `rules_packet.json`
- `testing_packet.json`
- `synthesis_packet.json`

Conditional runtime outputs:
- `runtime_packet.json`
- `process_packet.json`

Evaluation-only output:
- `packet_metrics.json`

Packet responsibilities:
- `rules_packet.json`
  - title pattern
  - selected template path/fingerprint
  - required section order
  - strict claim gates
- `runtime_packet.json`
  - shipped runtime surface
  - `no behavior change` supportability
- `process_packet.json`
  - repo/base/head resolution
  - issue-reference hints
  - duplicate-check hint summary
  - raw create options
- `testing_packet.json`
  - exact-command testing evidence
  - positive testing claim limits
- `synthesis_packet.json`
  - active rule gates
  - coverage gaps
  - focused packet hint
  - common-path sufficiency

## Lint Contract

Context lint:
- fail or warn on unresolved repo/base/head/template state
- surface duplicate-PR hints as warnings only
- derive drafting-basis metadata for packet building

Candidate lint:
- title must match `<type>(<scope>): <summary>`
- body must satisfy selected template sections and ordering
- body must not retain placeholder text
- title/body claims must be grounded in runtime/process/testing packet evidence

Strict claim gates:
- issue references require process-packet issue hints
- positive testing claims require exact commands from testing evidence
- `no behavior change` is allowed only when runtime packet is empty
- rollout, restart/reload, migration, and compatibility claims fail closed by default

## Validate Contract

Validator CLI:
- `--context <json>`
- `--title "<title>"`
- `--body-file <body.md>`
- optional `--output <json>`

Validator output:
- `valid`
- `can_apply`
- `errors`
- `warnings`
- `error_details`
- `warning_details`
- `stop_reasons`
- `candidate_findings`
- `validation_commands`
- `stale_fields`
- `normalized_create_request`
- `normalized_create_request_fingerprint`
- `apply_gate_status`

`normalized_create_request` must include:
- `repo_root`
- `repo_slug`
- `base`
- `head`
- `title`
- `body`
- `draft`
- `reviewers`
- `assignees`
- `labels`
- `milestone`
- `maintainer_can_modify`
- `validation_commands`
- `review_mode`
- `qa_gate`
- `validated_snapshot`

`validated_snapshot` must include:
- `local_head_oid`
- `remote_head_oid`
- `repo_slug`
- `base_ref`
- `head_ref`
- `changed_files_fingerprint`
- `template_path`
- `template_fingerprint`
- `duplicate_check_summary`

`duplicate_check_summary` must include:
- `status`
- `matched_repo_slug`
- `matched_head`
- optional `existing_pr_number`
- optional `existing_pr_url`

Normalization rules:
- reviewers/assignees: comma-split, trim, case-insensitive dedupe, deterministic sort
- labels: comma-split, trim, exact-value dedupe, deterministic sort
- milestone: trimmed scalar or `null`
- maintainer edit: invert `no_maintainer_edit`

Public stop taxonomy:
- `missing_auth`
- `repo_inference_failed`
- `base_resolution_failed`
- `template_not_found`
- `template_ambiguous`
- `remote_head_missing`
- `head_oid_mismatch`
- `existing_open_pr`
- `invalid_title`
- `invalid_body`
- `unsupported_claim`
- `stale_snapshot`
- `fingerprint_mismatch`
- `apply_verification_failed`

Supplemental internal guard reasons used by the implementation:
- `validator_mismatch`
- `live_snapshot_unavailable`
- `unresolved_stop_reason`

## Apply Contract

Apply CLI:
- `--validation <json>`
- optional `--dry-run`
- optional `--result-output <json>`

Apply rules:
- consume validator-normalized output only
- recompute the normalized request fingerprint before doing anything else
- re-check auth and the entire validated snapshot before mutation
- re-check duplicate state immediately before creation
- do not call `gh pr create --dry-run`
- real apply uses `gh pr create --head --base --title --body-file` plus validated options only
- re-fetch the created PR by the same `repo_slug + head` key
- fail closed when the fetched PR does not match the normalized request

Apply result should report:
- `apply_succeeded`
- `stop_reason` / `stop_reasons` when blocked
- `command`
- `current_pr_url` when creation succeeds
- `created_pr_number` when creation succeeds
