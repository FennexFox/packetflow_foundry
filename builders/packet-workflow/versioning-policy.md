# Packet-Workflow Versioning Policy

`packet-workflow` uses explicit builder-to-skill compatibility metadata.

## Canonical Source

- Canonical builder version metadata lives in `version.json`.
- Machine-readable authority order:
  1. `builders/packet-workflow/version.json`
  2. `builders/packet-workflow/retained-skills/<skill>/builder-spec.json` `builder_versioning`
  3. active `profiles/<name>/profile.json` `metadata.versioning`

## Version Fields

- `builder_semver`
  - Human-facing release trace only.
- `compatibility_epoch`
  - Manual migration gate for structure or behavior-shape changes.
- `builder_spec_schema_version`
  - `builder-spec.json` shape version.
- `repo_profile_schema_version`
  - active profile JSON shape version.

## Blocking Versus Non-Blocking

Validation and CI block on:
- stale skill epoch or schema
- stale profile epoch or schema
- missing or invalid skill version metadata
- missing or invalid profile version metadata
- skill or profile ahead of the current builder

Validation and CI do not block on:
- `builder_semver` drift only, when epoch and schema versions still match

Runtime collectors should:
- record a `builder_compatibility` block in context
- warn on stderr when compatibility status is not `current`

## When To Bump `compatibility_epoch`

Bump the epoch when a retained skill or profile must be manually migrated because:
- generated script expected contract shape changed
- required or meaningful `builder-spec.json` shape changed
- required `profile.json` shape changed
- runtime contract keys consumed by generated skills changed
- generated scaffold layout or required artifact set changed

Do not bump the epoch for:
- docs-only changes
- tests-only changes
- additive optional fields that leave existing skills and profiles structurally valid
- bug fixes that do not require skill or profile rewrites

## Upgrade Discipline

- Silent auto-bumps across epoch or schema changes are forbidden.
- If `compatibility_epoch`, `builder_spec_schema_version`, or `repo_profile_schema_version` changes, migration is manual.
- Retained skills must record these upgrades under `Builder Compatibility History` in `migration-worksheet.md`.
- Each compatibility-history entry should record:
  - `from -> to`
  - builder semver
  - change reason
  - manual migration scope

## Semver-Only Stamp Helper

- `scripts/stamp_skill_versions.py` may update `builder_semver` and `metadata.versioning.builder_semver`.
- It must refuse to run when epoch or schema versions are stale, missing, invalid, or ahead of the builder.

