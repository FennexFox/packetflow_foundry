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

## Retained vs Consumer-Local 판정
- Data-only profile로 표현 가능한 repo-specific 차이:
  - PR guidance file locations
  - review-doc ownership lists
  - source-path glob hints
- 실행 의미/정책/행동 계약까지 건드리는 차이:
  - 없음. reply marker policy, thread action validation, and apply semantics are reusable skill-local contracts.
- Decision: `retained`

## Core 승격 기준
- 반복 shared gap 여부:
  - active profile loading and profile metadata propagation repeat across multiple retained skills
  - generic core-area path heuristics also repeat across multiple retained skills
- 일회성 우회 여부:
  - thread marker adoption and completion-reply semantics are skill-specific and stay local
- Decision:
  - shared profile-loading boundary belongs in foundry core/builder guidance
  - marker-policy logic stays skill-local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
