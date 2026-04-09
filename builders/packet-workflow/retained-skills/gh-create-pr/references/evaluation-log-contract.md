# Evaluation Log Contract

Use this file for the shared evaluation-log envelope in `gh-create-pr`.

## Purpose

Track three outcomes consistently:
- efficiency
- quality
- safety

Default repo-local log path:

`<repo-root>/.codex/tmp/evaluation_logs/gh-create-pr/<run-id>.json`

The default path should stay under `.codex/tmp/evaluation_logs/`. An explicit
override path is allowed.

## Common Envelope

Use this top-level shape:
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

- Keep truly common fields in the shared envelope only.
- Put workflow-specific counters or mutation details in `skill_specific.data`.
- Keep packet sizing and packet-compaction telemetry in shared `packet_sizing` and `efficiency` blocks, not in `skill_specific.data`.
- Label estimated or unavailable data through shared provenance fields.
- Do not reintroduce legacy shared fields such as `baseline`, `measurement.token_source`, or `measurement.efficiency_source`.
- Renormalize scoring weights when a signal is missing.

## Helper Workflow

Use `scripts/write_evaluation_log.py` in three modes:
- `init`
  - `--context <json> --orchestrator <json> [--lint <json>] [--output <json>]`
- `phase`
  - `--log <json> --phase build|lint|validate|apply --result <json> [--duration-seconds <float>]`
- `finalize`
  - `--log <json> --final <json>`

Build-phase merge should populate shared `packet_sizing` and `efficiency`
fields, using `packet_sizing.json` only as an evaluation-side sidecar when
present.
