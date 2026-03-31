---
name: git-split-and-commit
description: Review the active repository's current working tree, split local changes into logical commits, draft repo-compliant commit messages, and commit automatically when confidence is high. Use when Codex needs to inspect staged, unstaged, and untracked non-ignored changes, decide whether they belong in one or more commits, and apply the commits safely with packetized evidence and targeted validation.
---

# Git Split And Commit

Thin entrypoint for the foundry retained `git-split-and-commit` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/git-split-and-commit/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/git-split-and-commit/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/git-split-and-commit/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
