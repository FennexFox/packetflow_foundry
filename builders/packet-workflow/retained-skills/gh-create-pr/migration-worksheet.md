# Migration Worksheet: gh-create-pr

## Workflow Snapshot
- `workflow_family`: `github-pr`
- Current runtime shape: `packet-heavy-orchestrator`, `generic`, `flat`, lint/validate/apply split
- Primary packets: `global_packet`, `rules_packet`, `process_packet`, `runtime_packet`, `testing_packet`

## Builder Compatibility History
- `unversioned -> packet-workflow 0.1.0`
  - change reason: introduced explicit builder-version compatibility metadata and upgrade rules for packet-workflow retained skills.
  - manual migration scope: added `builder_versioning` to `builder-spec.json`, added `metadata.versioning` to `profiles/default/profile.json`, and wired collector-side `builder_compatibility` reporting.
- `packet-workflow 0.2.0 / epoch 2`
  - change reason: evaluation telemetry schema moved to `2.0`, build results now emit `planned_workers`, `packet_sizing`, and `efficiency`, and pricing snapshot tracking became explicit.
  - manual migration scope: update build-result/evaluation-log consumers, migrate retained build artifacts from `packet_metrics.json` to `packet_sizing.json`, and restamp retained skill/profile version metadata to epoch 2.
