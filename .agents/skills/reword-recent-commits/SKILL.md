---
name: reword-recent-commits
description: Rewrite or reword a recent range of Git commit messages to the active repository's commit-message rules. Use when Codex needs replay-style safety, packet/audit artifacts, or anything broader than a trivial HEAD-only amend path.
---

# Reword Recent Commits

Thin entrypoint for the foundry retained `reword-recent-commits` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/reword-recent-commits/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/reword-recent-commits/SKILL.md`.

Decision guide:
- use `reword-head-commit` for a trivial `HEAD`-only rewrite on a clean branch
  tip with explicit repo rules
- use `reword-recent-commits` for broader or riskier history rewrites

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/reword-recent-commits/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
