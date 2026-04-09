# Migration Worksheet: gh-address-review-threads

## Workflow Snapshot
- `workflow_family`: `github-review`
- Current runtime shape: `standard`, `generic`, `flat`, validator/apply split
- Primary packets: `global_packet`, per-thread packets, thread batch packets
- Current authoritative files:
  - references: `review-threads-contract.md`, `thread-action-contract.md`, `comment-contract.md`
  - scripts: `collect_review_threads.py`, `build_review_packets.py`, `validate_thread_action_plan.py`, `apply_thread_action_plan.py`
  - tests: collect/build/validate/apply/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- PR template and repo guidance file discovery
- Changed-file grouping heuristics and core-area hints
- Optional repo guidance paths surfaced in packets

## Migration Classification
- `core`
  - validator/apply separation
  - reply-plan normalization boundary
  - review-mode semantics
  - worker-family semantics and packet-routing authority rules
- `profiles/default/profile.json`
  - review-doc paths for thread packets
  - repo markers and primary README binding
  - source-path globs for packet ownership hints
- Skill-local
  - review-thread packet schema
  - acknowledgement/completion marker policy
  - GitHub thread action validation and apply logic

## Legacy Inventory Mapping
- references kept as domain-local: `comment-contract.md`, `review-threads-contract.md`, `thread-action-contract.md`
- new retained interface additions: `builder-spec.json`, `references/core-contract.md`, `profiles/default/profile.json`
- scripts to update for profile metadata wiring: `collect_review_threads.py`, `build_review_packets.py`

## Retained vs Consumer-Local Decision
- Data-only profile differences that should stay repo-specific:
  - PR guidance file locations
  - review-doc ownership lists
  - source-path glob hints
- Behavior that remains skill-local:
  - reply marker policy, thread action validation, and apply semantics are reusable skill-local contracts.
- Decision: `retained`

## Core Escalation Check
- Shared gap already handled in foundry:
  - active profile loading and profile metadata propagation repeat across multiple retained skills
  - generic core-area path heuristics also repeat across multiple retained skills
- Review-thread workflow logic that should not move into core:
  - thread marker adoption and completion-reply semantics are skill-specific and stay local
- Decision:
  - shared profile-loading boundary belongs in foundry core/builder guidance
  - marker-policy logic stays skill-local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.2.0 / epoch 2`
  - change reason: evaluation telemetry schema moved to `2.0`, build results now emit `planned_workers`, `packet_sizing`, and `efficiency`, and pricing snapshot tracking became explicit.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 2.

## Pilot Hardening Outcome
- Prose-only invariants moved into script or test enforcement:
  - `ack-before-work` now requires a recorded `ack-applied` checkpoint before `record-validation` or `post-push`
  - `record-apply` now requires `apply_succeeded=true`, `fingerprint_match=true`, and a non-dry-run result for live manifest advancement
  - synthetic smoke now mirrors the manifest lifecycle by recording `ack` and `complete` apply results instead of skipping directly from validation to later phases
- Delegation non-use classification:
  - record-only: `review_mode_local_only`, `code_change_guardrail_blockers`, `broad_or_cross_cutting_fix_kept_local`, `validation_path_unclear`, `optional_qa_not_requested`
  - fatal: none in this pilot; lifecycle, fingerprint, marker-conflict, and missing-target failures stay on separate fatal gates
- Runtime to eval-only moves:
  - moved from runtime packets into build-result/eval-side artifacts: `review_mode_baseline`, `review_mode_adjustments`, `override_signals`, `recommended_workers`, `optional_workers`, `active_paths`, `active_areas`, `analysis_targets`, `thread_batches`, `delegation_non_use_cases`
  - kept in runtime: final `review_mode`, `packet_worker_map`, `routing_contract`, `same_run_reconciliation`, `context_fingerprint`, and marker-conflict safety context
- Retained `SKILL.md` reduction:
  - reduced from 179 lines to 73 lines while keeping the minimum operator execution contract in the retained file
- Extracted helper boundary check:
  - `review_thread_run.py` and `review_thread_packet_contract.py` remain skill-local shared helpers for this retained skill only
  - no new generic core helper was introduced; domain-local GitHub reply, reconciliation, and delegation policy stayed inside the skill
