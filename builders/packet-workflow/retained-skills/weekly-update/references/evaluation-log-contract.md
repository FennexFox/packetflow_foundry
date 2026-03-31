# Evaluation Log Contract

Use this file for the shared evaluation-log envelope in `weekly-update`.

## Purpose

Track three outcomes consistently:
- efficiency
- quality
- safety

Default log path:

`~/.codex/tmp/evaluation_logs/weekly-update/<run-id>.json`

The default path must stay outside the repo. An explicit override path is allowed.

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
