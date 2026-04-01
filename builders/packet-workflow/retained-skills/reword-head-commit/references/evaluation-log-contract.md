# Evaluation Log Contract

`eval-log.json` is a compact execution record for `reword-head-commit`.

Shared envelope:
- `schema_version`
- `run_id`
- `timestamp_utc`
- `skill`
- `repo`
- `quality`
- `safety`
- `outputs`
- `skill_specific`

This skill does not record packet metrics because it has no packet build path.
