---
name: reword-head-commit
description: Rewrite only the current HEAD commit message to the active repository's commit-message rules. Use when Codex needs a fast amend-based path for one clean HEAD commit with explicit repo guidance and no packet or replay audit requirements.
---

# Reword Head Commit

Thin entrypoint for the foundry retained `reword-head-commit` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/reword-head-commit/`
- do not reintroduce local copies of references, scripts, tests, or helper
  code under this wrapper

Use this skill by reading and following the retained kernel instructions at
`../../../builders/packet-workflow/retained-skills/reword-head-commit/SKILL.md`.

Decision guide:
- use `reword-head-commit` for a trivial `HEAD`-only rewrite on a clean branch
  tip with explicit repo rules
- use `reword-recent-commits` for broader or riskier history rewrites

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/reword-head-commit/`
  as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
