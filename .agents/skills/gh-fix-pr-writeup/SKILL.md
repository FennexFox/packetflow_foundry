---
name: gh-fix-pr-writeup
description: Verify and repair a GitHub pull request title and body when the user gives a PR number or asks to audit, rewrite, or fix PR text. Use when Codex must compare a PR's current writeup against repository PR instructions/templates and the actual code changes, then update it with gh CLI if the title/body are missing, truncated, generic, misleading, or unsupported by the diff.
---

# PR Writeup Repair

Thin entrypoint for the foundry retained `gh-fix-pr-writeup` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/gh-fix-pr-writeup/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/gh-fix-pr-writeup/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/gh-fix-pr-writeup/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
