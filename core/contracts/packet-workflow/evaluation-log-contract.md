# Evaluation Log Contract

Use this file for the authoritative shared evaluation-log envelope across packet-driven repo workflow skills.

## Purpose

Track three outcomes consistently across runs:
- efficiency
- quality
- safety

The log is a local operational artifact. It should default under the repo-local
scratch tree at:

`<repo-root>/.codex/tmp/evaluation_logs/<skill-name>/<run-id>.json`

An explicit override path is allowed, but the default should stay under
`.codex/tmp/evaluation_logs/`.

## Top-Level Shape

Every evaluation log should contain:

- `schema_version`
- `run_id`
- `timestamp_utc`
- `skill`
- `repo`
- `request`
- `input_size`
- `orchestration`
- `measurement`
- `tokens`
- `latency`
- `packet_sizing`
- `efficiency`
- `quality`
- `safety`
- `outputs`
- `scoring`
- `notes`
- `skill_specific`

## Common Rules

- Keep only truly common fields in the shared envelope.
- Put workflow-specific counters and mutation details in `skill_specific.data`.
- Record observed values first. Estimated or unavailable values must be labeled through per-component provenance fields.
- Do not reintroduce legacy shared fields such as `baseline`, `measurement.token_source`, or `measurement.efficiency_source`.
- Merge packet-sizing and packet-compaction telemetry from build results or finalize payloads. They are evaluation artifacts, not runtime routing inputs.
- Build-phase logs may record `spawn_plan`, but `planned_workers` stays empty until finalize resolves activation outcomes for this run.
- Scores must renormalize weights when inputs are missing.

## Orchestration

- `orchestration.orchestrator_fingerprint`
  - canonical SHA-256 fingerprint of the authoritative orchestrator payload
- `orchestration.spawn_plan`
  - authoritative runtime execution plan snapshot from `orchestrator.json`
  - contains `schema_version`, `routing_authority`, `default_spawn_enabled`, `default_spawn_blockers`, `retry_policy`, `workers[]`
- `orchestration.spawn_activation`
  - runtime activation and spawn-attempt ledger
  - contains `activated_worker_ids`, `skipped_worker_ids`, `local_fallback_worker_ids`, `trigger_events[]`, `drift_events[]`, `summary`, `workers[]`
  - `summary` must contain `attempted_count`, `succeeded_count`, `failed_count`, `local_fallback_count`, `not_activated_count`
  - `workers[]` must contain `worker_id`, `planned_worker_id`, `stage`, `spawn_attempted`, `spawn_succeeded`, `spawn_failed`, `attempt_count`, `failure_kind`, `fallback_reason`, `resolved_as`
- `orchestration.planned_workers`
  - `count`, `roles`, `workers[]`
  - finalize-resolved execution intent only; build/init phases should keep it empty
  - `workers[]` must contain `worker_id`, `name`, `agent_type`, `model`, `reasoning_effort`, `packets`, `responsibility`
- `orchestration.actual_workers`
  - `summary`, `workers[]`
  - execution outcome ledger, not an executed-only list
  - `summary` must contain `materialized_count`, `planned_row_count`, `unplanned_row_count`, `executed_count`, `completed_count`, `failed_count`, `cancelled_count`, `spawn_failed_count`, `planned_not_run_count`, `capture_complete`, `capture_incomplete_reason`
  - `workers[]` must contain `row_kind`, `worker_id`, `planned_worker_id`, `agent_type`, `model`, `reasoning_effort`, `status`
  - `row_kind` is `planned | unplanned`
  - planned rows allow `completed | failed | cancelled | spawn_failed | planned_not_run`, plus `started` only when `capture_complete=false`
  - unplanned rows allow `unplanned_completed | unplanned_failed | unplanned_cancelled`, plus `unplanned_started` only when `capture_complete=false`
  - finalize outputs should contain terminal statuses only unless `capture_complete=false`; `capture_complete=true` with nonterminal statuses is invalid

## Measurement

At minimum record:
- `latency_source`: `measured | estimated | unavailable`
- `quality_source`: `self_assessed | human_confirmed | mixed | unavailable`

## Packet Sizing And Efficiency

- `packet_sizing` contains only sizing counters:
  - `packet_count`
  - `packet_size_bytes`
  - `largest_packet_bytes`
  - `largest_two_packets_bytes`
  - optional `packet_size_breakdown`
- `efficiency.packet_compaction` records packet-compaction telemetry:
  - `local_only_tokens`
  - `packet_tokens`
  - `savings_tokens`
  - `main_model_input_cost_nanousd`
  - `provenance`
  - `pricing_snapshot_id`
- `efficiency.model_tier_delegation` records delegation telemetry:
  - `gross_avoided_main_cost_nanousd`
  - `delegation_overhead_cost_nanousd`
  - `net_savings_cost_nanousd`
  - `gross_avoided_provenance`
  - `overhead_provenance`
  - `net_provenance`
  - `pricing_snapshot_id`
- `efficiency.combined` records combined cost-equivalent telemetry:
  - `packet_compaction_cost_nanousd`
  - `delegation_net_cost_nanousd`
  - `total_net_cost_nanousd`
  - `component_provenance`

## Scoring

- `scoring.formula_version` is required
- `efficiency_score` should prefer observed signals:
  - worker fit
  - packet use
  - raw reread
  - reruns
  - token share when available
- `quality_score` should use first-pass usability, human post-edit needs, unsupported claims, evidence gaps, template violations, and final-output stability
- `safety_score` should use validate/apply boundaries, fingerprint checks, ambiguous matches, marker conflicts, rollback, and apply-after-failed-validation violations
- `overall_score` should weight safety highest, then quality, then efficiency

## Lifecycle

The common helper should support:
- `init`
  - build a base log from `context`, `orchestrator`, and optional `lint`
- `phase`
  - merge deterministic phase outputs such as build, lint, validate, and apply results
  - build-phase merges should populate shared `packet_sizing` and `efficiency` fields, using `packet_sizing.json` only as an evaluation-side sidecar when present
- `finalize`
  - merge agent-only observations such as token usage, actual worker mix, final usability, outputs, and notes
