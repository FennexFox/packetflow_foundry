# Migration Worksheet: gh-fix-pr-writeup

## Workflow Snapshot
- `workflow_family`: `github-review`
- Current runtime shape: `packet-heavy-orchestrator`, `generic`, `flat`
- Primary packets: `global_packet`, `rules_packet`, `synthesis_packet`, focused runtime/process/testing packets
- Current authoritative files:
  - references: `pr-writeup-contract.md`, `gh-fix-pr-writeup-evaluation-contract.md`
  - scripts: `collect_pr_context.py`, `lint_pr_writeup.py`, `build_pr_review_packets.py`, `validate_pr_writeup_edit.py`, `apply_pr_writeup.py`
  - tests: lint/build/validate/apply/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- PR template paths and repo instruction files
- repo-specific changed-file grouping and core-area hints
- review-doc sets used by rules/runtime/process/testing packets

## Migration Classification
- `core`
  - packet-heavy common-path semantics
  - validator-normalized apply boundary
  - worker-family semantics and packet-routing authority
- `profiles/default/profile.json`
  - PR guidance paths and review-doc lists
  - source-path globs for focused packet hints
  - lint toggles that stay declarative
- Skill-local
  - PR writeup contract and QA trigger policy
  - title/body validation logic
  - guarded `gh pr edit` apply flow

## Legacy Inventory Mapping
- references kept as domain-local: `pr-writeup-contract.md`
- new retained interface additions: `builder-spec.json`, `references/core-contract.md`, `profiles/default/profile.json`
- scripts to update for profile metadata wiring: `collect_pr_context.py`, `build_pr_review_packets.py`

## Retained vs Consumer-Local Decision
- Data-only profile differences that should stay repo-specific:
  - PR template file paths
  - repo instruction file bindings
  - review-doc sets and source globs
- Behavior that remains skill-local:
  - QA gating and validator/apply behavior remain reusable skill-local contracts.
- Decision: `retained`

## Core Escalation Check
- Shared gap already handled in foundry:
  - profile loading and profile metadata propagation repeat across multiple retained skills
  - packet-heavy common-path documentation already belongs in core and builder
- PR writeup logic that should not move into core:
  - PR title/body QA policy and writeup validation are local to this skill
- Decision:
  - shared profile-loading contract should be treated as foundry-wide
  - PR writeup QA behavior stays skill-local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.3.0 / epoch 3`
  - change reason: evaluation telemetry schema moved to `3.0`, runtime execution is now driven by `orchestrator.spawn_plan`, build results now emit `spawn_plan_preview`, and eval logs resolve `planned_workers` plus `spawn_activation` from runtime execution outcomes.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 3.
