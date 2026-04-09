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

## Retained vs Consumer-Local ?먯젙
- Data-only profile濡??쒗쁽 媛?ν븳 repo-specific 李⑥씠:
  - PR template file paths
  - repo instruction file bindings
  - review-doc sets and source globs
- ?ㅽ뻾 ?섎?/?뺤콉/?됰룞 怨꾩빟源뚯? 嫄대뱶由щ뒗 李⑥씠:
  - ?놁쓬. QA gating and validator/apply behavior remain reusable skill-local contracts.
- Decision: `retained`

## Core ?밴꺽 湲곗?
- 諛섎났 shared gap ?щ?:
  - profile loading and profile metadata propagation repeat across multiple retained skills
  - packet-heavy common-path documentation already belongs in core and builder
- ?쇳쉶???고쉶 ?щ?:
  - PR title/body QA policy and writeup validation are local to this skill
- Decision:
  - shared profile-loading contract should be treated as foundry-wide
  - PR writeup QA behavior stays skill-local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.2.0 / epoch 2`
  - change reason: evaluation telemetry schema moved to `2.0`, build results now emit `planned_workers`, `packet_sizing`, and `efficiency`, and pricing snapshot tracking became explicit.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 2.
