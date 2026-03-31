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

## Retained vs Consumer-Local 판정
- Data-only profile로 표현 가능한 repo-specific 차이:
  - commit guidance locations
  - ownership/source-path hints
  - repo markers
- 실행 의미/정책/행동 계약까지 건드리는 차이:
  - 없음. split validation, rollback semantics, and packet adjudication rules are reusable skill-local contracts.
- Decision: `retained`

## Core 승격 기준
- 반복 shared gap 여부:
  - profile loading and packet profile metadata propagation repeat across retained skills
  - generic area/path heuristics repeat across Git-oriented retained skills
- 일회성 우회 여부:
  - commit split safety, hunk rematch, and rollback behavior are one-skill domain logic
- Decision:
  - shared profile-loading and generic path classification boundaries should be documented at foundry level
  - commit-plan semantics stay local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
