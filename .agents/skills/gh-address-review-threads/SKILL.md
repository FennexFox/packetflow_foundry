---
name: gh-address-review-threads
description: Inspect unresolved GitHub PR review threads on the open pull request for the current branch, decide whether to accept, reject, defer, or defer outdated threads, post acknowledgement and completion replies with gh CLI, apply accepted fixes, and resolve completed threads. Use when Codex needs to read open PR review threads, summarize the planned direction or rejection, perform the work, then post a completion reply and resolve the finished threads.
---

# Address Review Threads

Thin entrypoint for the foundry retained `gh-address-review-threads` kernel.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative retained workflow assets in `../../../builders/packet-workflow/retained-skills/gh-address-review-threads/`
- do not reintroduce local copies of builder specs, profiles, references, scripts, tests, or migration worksheets under this wrapper

Use this skill by reading and following the retained kernel instructions at `../../../builders/packet-workflow/retained-skills/gh-address-review-threads/SKILL.md`.

When working on this skill:
- treat `../../../builders/packet-workflow/retained-skills/gh-address-review-threads/` as the source of truth
- apply reusable fixes in the retained kernel, not in this wrapper
- keep consumer-local overrides outside the vendor subtree
