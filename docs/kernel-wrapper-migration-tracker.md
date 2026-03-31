# Kernel / Wrapper Migration Tracker

This tracker records the split status for legacy source imports that are being
decomposed into:

- retained foundry kernels
- consumer-local wrappers
- profile-only data
- cannot-migrate items

## Foundry Boundary

Current foundry ownership:
- authoritative retained kernels live under `builders/packet-workflow/retained-skills/`
- thin discovery wrappers live under `.agents/skills/`
- wrappers may contain only `SKILL.md` and `agents/openai.yaml`

Drift origin:
- thin-entrypoint intent existed in repo prose from bootstrap
- the original generator and retained-skill tests still treated `.agents/skills/` as a bundled output root
- this migration closes that gap by moving authoritative retained assets and enforcing wrapper thinness in generator output and tests

## Status Key

- `source-import`: restored legacy copy is still the working source
- `retained-in-progress`: retained skill scaffold exists and is being filled
- `wrapper-in-progress`: consumer-local wrapper exists and is being trimmed
- `ready-to-remove`: retained and wrapper characterization tests are green, the
  worksheet ledger is complete, and the legacy source copy may be removed from
  foundry
- `removed`: legacy source copy has been removed from foundry

## Skills

| Legacy Source Skill | Retained Kernel | Consumer-Local Wrapper | Profile Split | Characterization Tests | Legacy Source Removal |
| --- | --- | --- | --- | --- | --- |
| `prepare-release-copy` | `draft-release-copy` | `prepare-release-copy` | retained profile complete; wrapper out-of-repo | retained green; wrapper out-of-repo | removed |
| `repo-public-docs-sync` | `public-docs-sync` | `repo-public-docs-sync` | retained profile complete; wrapper out-of-repo | retained green; wrapper out-of-repo | removed |
