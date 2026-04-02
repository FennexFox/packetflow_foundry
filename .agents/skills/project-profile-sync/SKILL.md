---
name: project-profile-sync
description: Scaffold and safe-sync consumer-repo project-local profiles for PacketFlow Foundry workflows. Use when Codex needs to create or refresh `.codex/project/profiles/default/profile.json` or `.codex/project/profiles/<skill-name>/profile.json` after bootstrap, vendoring, or wrapper discovery without re-deriving the whole profile structure from scratch.
---

# Project Profile Sync

Thin entrypoint for consumer-repo project profile scaffold and safe sync.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative implementation in `../../../builders/consumer-bootstrap/scripts/`
- do not place profile scaffolding logic, retained defaults, or tests under this wrapper

## Workflow

1. Run `../../../builders/consumer-bootstrap/scripts/sync_project_profiles.py` first.
- Use `--repo-root <project-root>`.
- Add `--skill <skill-name>` only when the user wants a narrow sync.
- Read the JSON report before inspecting repo-specific semantics.

2. Treat the script as structure-only authority.
- Let the script create missing project-local profiles.
- Let the script normalize `kind`, `name`, `profile_path`, and `metadata.versioning`.
- Let the script add only missing keys from retained/default scaffolds.

3. Fill meaning only after reading the report.
- Inspect only the unresolved semantic gaps reported by the sync run.
- Choose canonical repo bindings, review docs, source globs, and skill-specific `extra` values locally.
- Do not re-derive already-synced structural fields unless the user asks for a manual migration.

## Guardrails

- Do not rewrite stale, ahead-of-builder, or invalid project-local profiles automatically.
- Treat `manual_migration_required` report entries as stop points until the profile is repaired deliberately.
- Keep project-local profiles data-only; do not encode executable behavior, prompt fragments, or routing authority there.

## Output

- Tell the user which profiles were created, updated, unchanged, ignored, or blocked.
- Use the sync report as the first input to any follow-up repo inspection.
