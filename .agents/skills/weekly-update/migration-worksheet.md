# Migration Worksheet: weekly-update

## Workflow Snapshot
- `workflow_family`: `repo-audit`
- Current runtime shape: `standard`, `classification-oriented`, `hierarchical`, lint/validate/apply split
- Primary packets: `global_packet`, `mapping_packet`, `changes_packet`, `incidents_packet`, `risks_packet`
- Current authoritative files:
  - references: `weekly-update-contract.md`, `weekly-update-evaluation-contract.md`, `architecture-note.md`
  - scripts: `collect_weekly_update_context.py`, `build_weekly_update_packets.py`, `validate_weekly_update_plan.py`, `apply_weekly_update.py`
  - tests: collect/build/validate/apply/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- state-marker namespace and marker path conventions
- release-issue title matching
- review-thread marker tokens
- priority marker extraction
- optional review-doc lists and source-path hints

## Migration Classification
- `core`
  - validator/apply separation
  - review-mode semantics
  - worker-family semantics and packet-routing authority rules
  - decision-ready hierarchical packet semantics
- `profiles/default/profile.json`
  - repo markers and README binding
  - review-doc paths and source-path globs
  - repo-specific weekly-update conventions under `extra.weekly_update`
- Skill-local
  - weekly-update section order and candidate schema
  - classification values and `artifact_only` handling
  - raw-reread gating and marker-update gates
  - incident versus blocker adjudication rules

## Legacy Inventory Mapping
- references kept as domain-local: `weekly-update-contract.md`, `weekly-update-evaluation-contract.md`, `architecture-note.md`, `delegation-playbook.md`
- new retained interface additions: `builder-spec.json`, `references/core-contract.md`, `profiles/default/profile.json`
- scripts updated for profile metadata wiring: `collect_weekly_update_context.py`, `smoke_weekly_update.py`, `refresh_weekly_update_live_fixture.py`, `weekly_update_lib.py`

## Retained vs Consumer-Local Decision
- Data-only profile differences that should stay declarative:
  - state namespace
  - review marker tokens
  - release title regex
  - priority marker regex
  - packet review-doc lists and path globs
- Behavior that remains skill-local:
  - candidate classification semantics
  - final section ordering
  - marker-update validation and apply rules
  - raw-reread exception handling
- Decision: `retained`

## Core Escalation Check
- Shared gap already handled in foundry:
  - profile-aware retained skills need active-profile metadata in collected context and packets
  - builder validation must reject invalid hierarchical retained-shape combinations
- Weekly-update-specific logic that should not move into core:
  - incident versus blocker heuristics
  - review-finding filtering rules
  - marker-update gating for weekly status runs
- Decision:
  - keep builder/core changes generic
  - keep weekly-update adjudication and apply semantics skill-local

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
