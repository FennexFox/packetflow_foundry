---
name: reword-recent-commits
description: Rewrite or reword the latest n Git commit messages to the active repository's commit-message rules. Use when Codex needs to inspect repo-specific commit guidance, draft replacement commit messages for recent local commits, and optionally apply the rewrite safely without hand-driving an interactive rebase. Keep orchestration, final message synthesis, confirmation, and ref updates local while offloading narrow read-only packet analysis to gpt-5.4-mini workers when the rewrite spans multiple commits or areas.
---

# Reword Recent Commits

Thin entrypoint for the foundry retained `reword-recent-commits` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/reword-recent-commits/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/reword-recent-commits/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/reword-recent-commits/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
