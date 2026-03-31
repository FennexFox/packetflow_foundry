---
name: gh-create-pr
description: Create a GitHub pull request from an already-pushed branch by collecting repo and PR-template context, drafting a repo-compliant title/body, validating duplicate-PR and stale-snapshot gates, and creating the PR with gh CLI only after the normalized create request passes validation. Use when Codex must open a new PR instead of rewriting an existing one.
---

# Guarded PR Creation

Thin entrypoint for the foundry retained `gh-create-pr` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/gh-create-pr/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/gh-create-pr/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/gh-create-pr/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
