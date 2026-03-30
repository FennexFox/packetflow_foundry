# Evaluation Log Contract

Use this file for the authoritative shared evaluation-log envelope across packet-driven repo workflow skills.

## Purpose

Track three outcomes consistently across runs:
- efficiency
- quality
- safety

The log is a local operational artifact. It should default outside the repo at:

`~/.codex/tmp/evaluation_logs/<skill-name>/<run-id>.json`

An explicit override path is allowed, but the default must never point into the repo.

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

- Keep only truly common fields in the shared envelope.
- Put workflow-specific counters and mutation details in `skill_specific.data`.
- Record observed values first. Estimated values must be labeled in `measurement` or `baseline`.
- If no baseline is available, leave savings fields null instead of inventing a comparison.
- Scores must renormalize weights when inputs are missing.

## Baseline

- `baseline.method`: `none | heuristic_local_only | paired_run | historical_cohort`
- default: `none`
- include estimate fields only when they actually exist:
  - `estimated_local_only_tokens`
  - `estimated_token_savings`
  - `estimated_delegation_savings`
- keep `baseline.confidence` explicit when a heuristic or historical estimate is used

## Measurement

At minimum record:
- `token_source`: `measured | estimated | unavailable`
- `latency_source`: `measured | estimated | unavailable`
- `quality_source`: `self_assessed | human_confirmed | mixed | unavailable`

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
  - merge deterministic phase outputs such as lint, validate, and apply results
- `finalize`
  - merge agent-only observations such as token usage, actual worker mix, final usability, outputs, and notes
