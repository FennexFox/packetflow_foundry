---
name: weekly-update
description: Top-level orchestration skill for reusable weekly updates. Synthesize recent PRs, rollouts, incidents, reviews, and blockers using packet-driven evidence collection and narrow read-only delegation, keep worker outputs proposal-grade, keep final classification and wording local, and update only a last-success marker after a reviewed plan clears apply gates.
---

# Weekly Update

Thin entrypoint for the foundry retained `weekly-update` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/weekly-update/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/weekly-update/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/weekly-update/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
