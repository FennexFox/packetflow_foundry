# Release Copy Contract

This file is the canonical top-level interface reference for `draft-release-copy`.

Read [`architecture-note.md`](architecture-note.md) for why this skill keeps the current `packet-heavy-orchestrator` profile. Read [`maintenance-note.md`](maintenance-note.md) before changing packet names, authority order, or runtime/eval boundaries.

## Canonical Interface

### Runtime Artifacts

- `orchestrator.json`
- `global_packet.json`
- `publish_packet.json`
- `readme_packet.json`
- `changes_packet.json`
- `checklist_packet.json`
- `synthesis_packet.json`
- optional `evidence_packet.json`

### Eval Artifacts

- `packet_metrics.json`
- `eval-log.json`

### Canonical Local Interfaces

- local draft: `release-copy-plan.json`
- validator output: normalized validation JSON from `validate_release_copy.py`
- apply input: validator output only
- apply result: JSON from `apply_release_copy.py --result-output ...`

## Builder Metadata

- `workflow_family`: `release-copy`
- `archetype`: `audit-and-apply`
- `orchestrator_profile`: `packet-heavy-orchestrator`
- `decision_ready_packets`: `local-only synthesis packet plus compact worker packets`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

Trigger phrases:
- prepare release copy
- update release changelog
- draft release checklist issue
- verify release gate evidence

## Packet Interface

- `global_packet.json`
  - shared operational context
  - authority order
  - gate summary
  - helper policy
  - disallowed claims
- `publish_packet.json`
  - current publish fields
  - prior release changelog
  - rewrite-required publish fields
- `readme_packet.json`
  - README intro
  - current release/status sections
  - settings-default drift
- `changes_packet.json`
  - shipped-change topic signals
  - top churn files
  - representative files
  - condensed commit subjects
- `checklist_packet.json`
  - release issue delta
  - template structure
  - unresolved placeholders
- `evidence_packet.json`
  - normalized evidence fields only
  - missing evidence summary only
- `synthesis_packet.json`
  - local final drafting packet
  - common-path decision basis
  - publish/readme/issue rewrite guidance
  - explicit stop risks

## Authority Order

Use this order when sources disagree:

1. tracked release rules and metadata
2. tracked runtime defaults
3. tracked release diff since the base tag
4. optional evidence input
5. optional repo-relative local helper

The local helper is never the authority for player-facing wording.

## Runtime Vs Eval Split

- `orchestrator.json` is the runtime contract.
  - Keep worker routing, common-path drafting, and validator/apply guardrails here.
- `packet_metrics.json` is eval-only.
  - Keep packet sizes, token-proxy estimates, and savings here.
- `eval-log.json` is the accumulated regression and run-quality artifact.
  - Merge `packet_metrics.json` during the build phase instead of treating sizing metrics as runtime routing inputs.

## Field Roles

### Authority Fields

- `authority_order`
- `packet_worker_map`
- `common_path_contract`
- `shared_packet`
- `shared_local_packet`

### Registry Metadata

- `preferred_worker_families`

### Derived Convenience Fields

- `recommended_workers`
- `optional_workers`

### Explanatory Fields

- `worker_selection_guidance`

Rules:
- `packet_worker_map` is the routing authority.
- `preferred_worker_families` is descriptive registry metadata only.
- `recommended_workers` and `optional_workers` are derived convenience fields only.
- `worker_selection_guidance` is explanatory only and must not be treated as a routing source.

## Common-Path Semantics

- common-path local drafting must finish from:
  - `global_packet.json`
  - `synthesis_packet.json`
  - at most one focused packet
- `synthesis_packet.json` must be sufficient for local final drafting in the common path.
- raw reread is exceptional, not compensatory.
- `packet insufficiency` is a failure, not a normal fallback.
- deterministic apply is narrower than local drafting:
  - `PublishConfiguration.xml`: allowlisted field replacement only
  - `README.md`: intro text and allowlisted section replacement only
  - release issue: validator-normalized issue action only

## Required Release Copy Properties

- Keep `PublishConfiguration.xml` and `README.md` aligned on what is shipped now.
- Treat `PublishConfiguration.xml` `ChangeLog` as first-class release copy.
- Treat `ChangeLog` as release-scoped, not cumulative.
- Keep setting-default claims aligned with `Setting.cs`.
- Keep `ChangeLog` bullets supported by the diff since the base tag.
- Keep helper wording local and optional.

## Freshness Before Apply

- Treat collected context, lint output, packets, and any auto-discovered existing release issue snapshot as stale once `HEAD`, `base_tag`, `target_version`, evidence inputs, or the open release issue title/body changes.
- Refresh `collect -> lint -> build` before editing files or invoking `create_release_issue.py` after a stale change.
- Validator/apply must compare the collected freshness tuple and source fingerprints against live repo state before mutation.

## Plan / Validate / Apply Contract

- Local draft output is `release-copy-plan.json`.
- Validator normalizes and strips unknown extra fields.
- Local input-contract failures must stop before any `gh` command runs.
- Validator fails closed on:
  - stale `HEAD`
  - stale release source fingerprints
  - stale existing issue snapshots
  - missing auth
  - missing required project scope
  - packet insufficiency / compensatory rereads
- Apply consumes validator-normalized output only.
- `--dry-run` uses the same normalized input path as real apply.

## Release Checklist Issue Contract

- Title format: `[Release] vX.Y.Z`
- Label: `release`
- Prefer reusing an existing open `[Release] vX.Y.Z` issue over creating a duplicate.
- Template section order:
  - `Target version`
  - `Included changes`
  - `Release-gate evidence / validation`
  - `Checklist`

## Gate Policy

- Determine applicable release-gate or validation tracks from shipped change scope.
- Software-track changes require software evidence when applicable.
- Telemetry validation never replaces software evidence when both apply.
- If no scoped gate applies, say so explicitly instead of inventing one.

## Smoke Output Schema

`smoke_prepare_release_copy.py` should emit:

- `status`
- `reason`
- `repo_root`
- `next_action`

It may include additional run details such as packet counts and token-proxy metrics.

## Out Of Scope

- broad README restructuring
- unsupported XML layout rewrites
- narrative-only release prose that cannot be expressed through deterministic apply
- executing the local helper
- treating worker output as final player-facing text

## Maintenance Note

When changing this skill, keep these in sync:

- `release_copy_plan_contract.py`
- `build_release_copy_packets.py`
- `SKILL.md`
- `architecture-note.md`
- this contract file
- smoke output expectations
- tests that lock field roles, packet interface, and eval/runtime split
