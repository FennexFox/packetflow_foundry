# Migration Worksheet: git-split-and-commit

## Workflow Snapshot
- `workflow_family`: `git-history`
- Current runtime shape: `standard`, `classification-oriented`, `hierarchical`, validator/apply split
- Primary packets: `global_packet`, `rules_packet`, `worktree_packet`, `candidate-batch-*`, `split-file-*`
- Current authoritative files:
  - references: `commit-plan-contract.md`, `architecture-rationale.md`
  - scripts: `collect_commit_rules.py`, `collect_worktree_context.py`, `build_commit_packets.py`, `validate_commit_plan.py`, `apply_commit_plan.py`
  - tests: build/validate/apply/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- repo commit-guidance docs and recent scope vocabulary
- path-to-area heuristics and scope suggestions
- targeted validation command hints derived from current repo layout

## Migration Classification
- `core`
  - decision-ready packet semantics
  - hierarchical worker contract
  - validator/apply boundary and apply rollback rules
- `profiles/default/profile.json`
  - commit-guidance doc paths
  - repo markers and source-path globs
  - declarative ownership hints
- Skill-local
  - commit plan schema and split safety rules
  - hunk rematch behavior
  - staged/apply rollback mechanics

## Legacy Inventory Mapping
- references kept as domain-local: `commit-plan-contract.md`
- new retained interface additions: `builder-spec.json`, `references/core-contract.md`, `profiles/default/profile.json`
- scripts to update for profile metadata wiring: `collect_worktree_context.py`, `build_commit_packets.py`

## Retained vs Consumer-Local Decision
- Data-only profile differences that should stay repo-specific:
  - commit guidance locations
  - ownership/source-path hints
  - repo markers
- Behavior that remains skill-local:
  - split validation, rollback semantics, and packet adjudication rules are reusable skill-local contracts.
- Decision: `retained`

## Core Escalation Check
- Shared gap already handled in foundry:
  - profile loading and packet profile metadata propagation repeat across retained skills
  - generic area/path heuristics repeat across Git-oriented retained skills
- Commit-splitting logic that should not move into core:
  - commit split safety, hunk rematch, and rollback behavior are one-skill domain logic
- Decision:
  - shared profile-loading and generic path classification boundaries should be documented at foundry level
  - commit-plan semantics stay local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.3.0 / epoch 3`
  - change reason: evaluation telemetry schema moved to `3.0`, runtime execution is now driven by `orchestrator.spawn_plan`, build results now emit `spawn_plan_preview`, and eval logs resolve `planned_workers` plus `spawn_activation` from runtime execution outcomes.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 3.

## Pilot Hardening Outcome
- Prose-only invariants moved into script or test enforcement:
  - nested retained-skill `scripts/**` paths now map to sibling `tests/test_*.py` coverage instead of only matching immediate `scripts/` parents
  - apply-stage targeted checks now reuse argv-shaped command execution without `shell=True`, with explicit no-input stdio handling for Windows stability
  - targeted unittest commands now reuse the same concrete Python interpreter path that launched the workflow helper
- Runtime to eval-only moves:
  - moved from `orchestrator.json` into build-result/eval-side artifacts: `review_mode_baseline`, `review_mode_adjustments`, worker recommendations, delegation non-use metadata, and override-signal summaries
  - kept in runtime: final `review_mode`, `packet_worker_map`, common-path/reread gates, and split/worktree blocker context
- Retained `SKILL.md` reduction:
  - reduced to the minimum operator-facing contract with execution roots, entry flow, continue gates, stop gates, final response requirements, and references
