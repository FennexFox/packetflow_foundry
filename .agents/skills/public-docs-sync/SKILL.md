---
name: public-docs-sync
description: Audit and synchronize public repository docs against tracked runtime metadata, selected GitHub evidence, and validator-normalized deterministic edits. Use when Codex must detect public-doc drift, propose scoped fixes, and update marker state without embedding repo-specific governance policy in the retained kernel.
---

# Public Docs Sync

Thin entrypoint for the foundry retained `public-docs-sync` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/public-docs-sync/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/public-docs-sync/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/public-docs-sync/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
