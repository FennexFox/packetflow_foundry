# Profile Boundary Contract

Profiles are data-only overlays.

## Allowed In Profiles

- repo markers
- path bindings
- globs
- review-doc lists
- lint and review defaults
- worker selection defaults
- `metadata.versioning` compatibility metadata
- notes

## Must Stay In Core

- validator/apply semantics
- stop taxonomy meaning
- common-path semantics
- worker-family semantics
- packet schema semantics
- shared default authority order

## Forbidden In Profiles

- executable hooks
- prompt fragments that define behavior
- packet routing authority
- validator/apply behavior
- stop taxonomy redefinition
- token-budget semantics

Foundry reusable overlays belong in `profiles/`.
Repo-specific profiles belong in `.codex/project/profiles/`.
