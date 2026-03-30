# Validator Apply Contract

Shared mutating workflow rules:
- validator and apply are separate phases
- apply consumes validator-normalized output only
- apply must not consume raw plan input directly
- `--dry-run` must use the same validator-normalized input path as real apply
- stale-context, fingerprint, and apply-gate checks belong on the validate/apply boundary

Profiles may select defaults around these phases, but they must not redefine this contract.
