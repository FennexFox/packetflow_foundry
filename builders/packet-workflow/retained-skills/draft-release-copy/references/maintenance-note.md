# Prepare Release Copy Maintenance Note

Use this note when updating the skill as a reference packet workflow, not just as an operational tool.

## Keep These Surfaces In Sync

- `scripts/release_copy_plan_contract.py`
- `scripts/build_release_copy_packets.py`
- `scripts/smoke_prepare_release_copy.py`
- `SKILL.md`
- `references/release-copy-contract.md`
- `references/architecture-note.md`
- tests that lock packet interface, runtime/eval split, and authority-vs-convenience fields

## Change Checklist

When changing packet or contract structure, confirm all of these:

- packet names still match the canonical interface
- authority fields and derived convenience fields are still clearly separated
- runtime artifacts did not absorb eval-only metrics
- smoke output schema still matches the documented fields
- out-of-scope boundaries are still documented
- tests still lock the changed contract shape

## Reference-Grade Standard

This skill counts as reference-grade only when the same shape appears in code, docs, and tests:

- packet interface
- authority order
- common-path semantics
- runtime/eval artifact split
- smoke output schema
- out-of-scope note
- maintenance note
