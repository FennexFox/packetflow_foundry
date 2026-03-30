# Architecture Rationale

- Keep the `standard` profile because packet generation shapes evidence, but commit planning, validation, and apply stay local.
- Keep whole-file handling as the default because safe partial splits depend on stable tracked-text hunks and clear packet evidence.
- Skip `packet_explorer` because this workflow needs commit-boundary judgment more than execution-path tracing.
- Use `broad-delegation` sparingly; most runs should stay local or targeted so the final plan remains easy to re-check against the live worktree.
