# Migration Worksheet: draft-release-copy

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.3.0 / epoch 3`
  - change reason: evaluation telemetry schema moved to `3.0`, runtime execution is now driven by `orchestrator.spawn_plan`, build results now emit `spawn_plan_preview`, and eval logs resolve `planned_workers` plus `spawn_activation` from runtime execution outcomes.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 3.
