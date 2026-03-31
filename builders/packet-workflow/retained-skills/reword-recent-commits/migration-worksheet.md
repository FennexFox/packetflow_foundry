# Migration Worksheet: reword-recent-commits

## Workflow Snapshot
- `workflow_family`: `git-history`
- Current runtime shape: `standard`, `generic`, `flat`, validator/apply split
- Primary packets: `global_packet`, `rules_packet`, `commit-*`
- Current authoritative files:
  - references: `reword-recent-commits-contract.md`, `history-rewrite-safety.md`, `rule-discovery.md`
  - scripts: `collect_commit_rules.py`, `collect_recent_commits.py`, `build_reword_packets.py`, `validate_reword_plan.py`, `apply_reword_plan.py`
  - tests: build/validate/apply/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- repo-specific commit-guidance docs
- path-to-area heuristics used for review depth
- source vocabulary hints derived from current repo history

## Migration Classification
- `core`
  - validator/apply split and stale-context guard semantics
  - review-mode semantics
  - worker-family semantics and packet-routing authority
- `profiles/default/profile.json`
  - commit-guidance doc paths
  - source-path globs and repo markers
  - declarative review-doc ownership
- Skill-local
  - rewrite plan schema
  - confirmation-before-history-mutation rule
  - replay/apply behavior and rewrite safety rules

## Legacy Inventory Mapping
- references kept as domain-local: `reword-recent-commits-contract.md`, `history-rewrite-safety.md`
- new retained interface additions: `builder-spec.json`, `references/core-contract.md`, `profiles/default/profile.json`
- scripts to update for profile metadata wiring: `collect_recent_commits.py`, `build_reword_packets.py`

## Retained vs Consumer-Local 판정
- Data-only profile로 표현 가능한 repo-specific 차이:
  - commit-guidance file paths
  - review-doc ownership and path hints
  - repo markers
- 실행 의미/정책/행동 계약까지 건드리는 차이:
  - 없음. rewrite safety, confirmation, and apply behavior remain reusable skill-local contracts.
- Decision: `retained`

## Core 승격 기준
- 반복 shared gap 여부:
  - profile loading and profile metadata propagation repeat across retained skills
  - generic path/area heuristics repeat across Git-oriented retained skills
- 일회성 우회 여부:
  - rewrite-plan semantics and replay safety remain one-skill logic
- Decision:
  - shared profile-loading boundary is foundry-wide
  - rewrite-specific safety rules stay local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
