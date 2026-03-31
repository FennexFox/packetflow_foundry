---
name: draft-release-copy
description: Draft and validate reusable release-copy updates by collecting release evidence, preparing publish configuration and README updates, and normalizing release-issue create or edit actions. Use when Codex must turn tracked repo state plus release evidence into guarded release-copy edits without encoding project-specific release policy in the retained kernel.
---

# Draft Release Copy

Thin entrypoint for the foundry retained `draft-release-copy` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/draft-release-copy/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/draft-release-copy/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/draft-release-copy/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
