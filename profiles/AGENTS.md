# Profiles AGENTS

This subtree contains reusable foundry overlay profiles only.

Default model:
- `baseline` is the default overlay
- `packet-heavy-orchestrator` is an opt-in upper overlay

Profiles here must stay:
- reusable across multiple repos
- data-only
- limited to selection defaults, bindings, review defaults, and notes

Do not place these in foundry profiles:
- repo-specific path bindings for one consumer repo
- project-only review docs
- executable hooks
- behavior semantics
- packet routing authority

If a profile is only useful to one consumer repo, put it in `.codex/project/profiles/` instead of here.
