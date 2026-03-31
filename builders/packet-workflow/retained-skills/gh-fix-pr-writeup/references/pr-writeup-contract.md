# PR Writeup Contract

This file defines the packet, worker, validator, and apply contract for `gh-fix-pr-writeup`.

## Builder Metadata

- `workflow_family`: `github-review`
- `archetype`: `audit-and-apply`
- `orchestrator_profile`: `packet-heavy-orchestrator`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

## Runtime vs Evaluation Split

- `orchestrator.json` is a lean runtime contract.
- `packet_metrics.json` is evaluation/regression metadata only.
- Runtime packets must not carry token-efficiency counters.
- Build-phase metrics are merged into the evaluation log from `build-result.json` / `packet_metrics.json`, not read from runtime routing metadata.

## Required Packet Outputs

- `orchestrator.json`
- `global_packet.json`
- `rules_packet.json`
- `runtime_packet.json` when runtime evidence is active
- `process_packet.json` when workflow/docs/config evidence is active
- `testing_packet.json`
- `synthesis_packet.json`
- `packet_metrics.json`

## Packet Semantics

### `rules_packet.json`

This is the authoritative hard-rule source.

Keep only:
- title pattern
- required section order
- disallowed claim categories
- issue-ref policy
- repo instruction excerpts
- local gate reminders

Do not put run-specific failures or drafting decisions here.

### `synthesis_packet.json`

This is the run-specific drafting decision packet.

It must not duplicate the full rule prose from `rules_packet.json`.

It must contain:
- `rewrite_strategy`
- `qa_required`
- `qa_reason`
- `active_rule_gates`
- `current_failures`
- `title_direction`
- `required_sections_status`
- `section_rewrite_requirements`
- `supported_claims`
- `unsupported_claim_risks`
- `testing_evidence_status`
- `issue_ref_status`
- `coverage_gaps`
- `focused_packet_hint`

## Common Path Contract

Common-path local drafting must close with:
- `rules_packet.json`
- `synthesis_packet.json`
- at most one focused packet

Rules:
- `packet_insufficiency` is failure, not an allowed reread reason
- raw reread is allowed only for:
  - `sample_omission`
  - `worker_conflict`
  - `claim_dispute`
  - `validator_blocker`

## Worker Routing Metadata

- `packet_worker_map`
  - `runtime_packet.json -> packet_explorer`
  - `process_packet.json -> packet_explorer`
  - `testing_packet.json -> evidence_summarizer`
- optional rules cross-check
  - `rules_packet.json -> docs_verifier`
- optional QA pass
  - `large_diff_auditor`

Rules:
- `packet_worker_map` is the routing authority
- `worker_selection_guidance` is explanatory only
- `rules_packet.json` remains local-first even when a rules verifier is available

## QA Trigger Policy

`qa_required` must stay a rare exception.

It becomes `true` only when:
- `rewrite_strategy == full-rewrite` and `review_mode == broad-delegation`
- worker/local findings conflict on the same claim cluster
- raw reread reason is `worker_conflict` or `claim_dispute`

It must remain `false` for:
- `full_rewrite_likely` alone
- small PR full rewrites without conflicting claim evidence

## Validate/Apply Boundary

- Final title/body synthesis stays local.
- `validate_pr_writeup_edit.py` is the required validator.
- `apply_pr_writeup.py` is the only supported mutation helper.
- Apply consumes validator output only.
- `--dry-run` follows the same validated-input path.
- Validator output must expose:
  - `valid`
  - `can_apply`
  - `errors`
  - `warnings`
  - `stop_reasons`
  - `normalized_edit`
  - `normalized_edit_fingerprint`
  - `apply_gate_status`
- `normalized_edit` must include:
  - replacement title/body
  - minimal validated snapshot
  - validation commands
  - review mode
  - QA gate state
- The minimal validated snapshot is limited to apply recheck fields:
  - `title`
  - `body`
  - `url`
  - `headRefName`
  - `headRefOid`
  - `baseRefName`
  - `changed_files`
- A `qa_required` draft must not become apply-safe without QA clear.
- Apply must fail closed when live snapshot state changes after validation.

## Final Output Shape

The final user-visible result must:
- say whether the PR already matched the rules or what changed
- include the final PR URL
- mention the validation commands that actually ran
- call out blockers precisely when safe repair was not possible
