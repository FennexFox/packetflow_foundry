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
- `baseline`
- `measurement`
- `tokens`
- `latency`
- `quality`
- `safety`
- `outputs`
- `scoring`
- `notes`
- `skill_specific`

## Common Rules

- Keep truly common fields in the shared envelope only.
- Put workflow-specific counters or mutation details in `skill_specific.data`.
- Keep runtime contract metadata out of the evaluation log unless the workflow explicitly mirrors it for regression analysis.
- Default `baseline.method` to `none`.
- Leave savings fields null when no baseline exists.
- Label estimated or unavailable data explicitly in `measurement`.
- Renormalize scoring weights when a signal is missing.

## Helper Workflow

Use `scripts/write_evaluation_log.py` in three modes:
- `init`
  - `--context <json> --orchestrator <json> [--lint <json>] [--output <json>]`
- `phase`
  - `--log <json> --phase build|lint|validate|apply --result <json> [--duration-seconds <float>]`
- `finalize`
  - `--log <json> --final <json>`

When a packet-heavy orchestrator profile emits `packet_metrics.json`, merge those counters through the build-phase result instead of copying them into runtime packets.
