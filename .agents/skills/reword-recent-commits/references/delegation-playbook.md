# Delegation Playbook

Read this file when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`: no workers
- `targeted-delegation`: 2 workers
- `broad-delegation`: 3-4 workers
- Optional QA worker: only when commit coverage is broad or worker findings conflict

## Local Gates

- Read `rules_packet.json` locally before drafting replacement messages.
- Treat builder-style efficiency metadata as supporting context only; the flat/generic worker contract remains the runtime boundary.
- This pass does not rename `task_packet_names` or `task_packet_ids`; use the emitted packet names as-is.
- Re-check the final message set against `rules_packet.json` locally before confirmation and before applying the rewrite.

## Preferred Worker Mapping

- `global_packet.json`
  - Every worker reads this first
  - Purpose: keep rewrite safety, required message rules, and routing metadata in view
- `rules_packet.json`
  - Prefer `docs_verifier`
  - Purpose: extract hard commit-message rules, allowed types, scope requirements, subject/body constraints, and scope vocabulary
- `commit-XX.json`
  - Prefer `evidence_summarizer`
  - If you need an explicit model override, use `gpt-5.4-mini`
  - Purpose: summarize commit intent, touched areas, suggested type/scope, and whether a body is needed
- Optional QA pass
  - Prefer `large_diff_auditor`
  - If you need an explicit model override, use `gpt-5.4-mini`
  - Purpose: compare the drafted replacement messages against the rules and per-commit evidence

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use [$reword-recent-commits](<skill-path>/SKILL.md) to analyze one commit packet.

Read only:
- <global-packet>
- <rules-or-commit-packet>
- <specific changed files if needed>

Return exactly:
- commit indexes
- primary intent
- evidence files
- suggested type/scope
- body needed
- ambiguity
- confidence
- reread_control
```

Keep each worker narrow. Do not hand a worker intended final commit messages.

## Integration Rules

- Start workers, then keep reading the current plan locally instead of waiting immediately.
- Treat worker output as evidence, not as the final commit text.
- If workers disagree, inspect only the conflicting commits locally and add the optional QA worker if the disagreement changes the final message set.
- Keep `apply_reword_plan.py` local. Do not delegate `git worktree`, `git update-ref`, or any ref-changing command.
