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

## Retained vs Consumer-Local ?먯젙
- Data-only profile濡??쒗쁽 媛?ν븳 repo-specific 李⑥씠:
  - commit-guidance file paths
  - review-doc ownership and path hints
  - repo markers
- ?ㅽ뻾 ?섎?/?뺤콉/?됰룞 怨꾩빟源뚯? 嫄대뱶由щ뒗 李⑥씠:
  - ?놁쓬. rewrite safety, confirmation, and apply behavior remain reusable skill-local contracts.
- Decision: `retained`

## Core ?밴꺽 湲곗?
- 諛섎났 shared gap ?щ?:
  - profile loading and profile metadata propagation repeat across retained skills
  - generic path/area heuristics repeat across Git-oriented retained skills
- ?쇳쉶???고쉶 ?щ?:
  - rewrite-plan semantics and replay safety remain one-skill logic
- Decision:
  - shared profile-loading boundary is foundry-wide
  - rewrite-specific safety rules stay local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.2.0 / epoch 2`
  - change reason: evaluation telemetry schema moved to `2.0`, build results now emit `planned_workers`, `packet_sizing`, and `efficiency`, and pricing snapshot tracking became explicit.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 2.

## Pilot Hardening Outcome
- Prose-only invariants moved into script or test enforcement:
  - the single driver remains the only normal entrypoint for prepare, validate, dry-run apply, live apply, and evaluation-log finalization
  - replay/apply keeps reusing the same concrete Python interpreter path across helper phases by launching child helpers from the running driver interpreter
- Runtime to eval-only moves:
  - moved from `orchestrator.json` into build-result/eval-side artifacts: `review_mode_baseline`, `review_mode_adjustments`, worker recommendations, optional workers, delegation non-use metadata, and override-signal summaries
  - kept in runtime: final `review_mode`, packet-routing metadata, rewrite blockers, common-path gating, and rules/context fingerprints
- Retained `SKILL.md` reduction:
  - reduced to the minimum operator-facing contract with explicit entry, continue, stop, and final-response sections
