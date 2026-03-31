# Delegation Playbook

Read this file when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`: no workers
- `targeted-delegation`: 2 workers
- `broad-delegation`: 3-4 workers
- Optional QA worker: only when split risk is broad or worker findings conflict

## Local Gates

- Read `rules_packet.json` and `worktree_packet.json` locally before drafting a plan.
- Keep `rules_packet.json + worktree_packet.json + one focused packet at a time` as the common path for local adjudication.
- Treat `task_packet_names` as basename metadata only; use `packet_order` or concrete packet filenames when you need file-oriented references.
- Re-check the final plan against those packets locally before validation and before apply.
- Keep local hard stops local: `active_git_operation`, `ambiguous_split_rematch`, `partial_split_unsupported`, `targeted_check_unavailable`, and `rollback_failed`.
- Do not reread raw diffs unless an explicit exception reason applies; worker disagreement alone is not enough without a matching packet-level conflict.

## Preferred Worker Mapping

- `global_packet.json`
  - Every worker reads this first
  - Purpose: keep the shared packet contract, stop conditions, and routing metadata in view
- `rules_packet.json`
  - Prefer `docs_verifier`
  - Purpose: extract hard commit-message rules, allowed types, scope requirements, subject/body constraints, and scope vocabulary
- `worktree_packet.json`
  - Prefer `repo_mapper`
  - Purpose: extract touched-surface, fingerprint, and validation-candidate facts
- `candidate-batch-XX.json`
  - Prefer `evidence_summarizer`
  - If you need an explicit model override, use `gpt-5.4-mini`
  - Purpose: summarize one logical commit bucket and its likely type/scope
- `split-file-XX.json`
  - Prefer `large_diff_auditor`
  - If you need an explicit model override, use `gpt-5.4-mini`
  - Purpose: judge whether the file is one intent or multiple intents, and whether the split risk is acceptable
- Optional QA pass
  - Prefer `large_diff_auditor`
  - If you need an explicit model override, use `gpt-5.4-mini`
  - Purpose: compare the draft plan against the packet evidence before apply

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use [$git-split-and-commit](<skill-path>/SKILL.md) to analyze one packet.

Read only:
- <global-packet>
- <rules-or-worktree-packet>
- <specific candidate-batch or split-file packet>

Return exactly:
- packet ids
- primary intent
- evidence files
- recommended type/scope
- body needed
- unsupported split risk
```

Keep each worker narrow. Do not hand a worker the whole diff or the final plan.

## Integration Rules

- Start workers, then keep drafting the final plan locally instead of waiting immediately.
- Treat worker output as evidence, not as the final commit text.
- If workers disagree, inspect only the conflicting packets locally and add the optional QA worker if the disagreement changes the final plan.
- If packet evidence still cannot resolve the boundary, record an explicit reread reason instead of silently rereading the diff.
- Keep `apply_commit_plan.py` local. Do not delegate staging, hunk rematch, or `git commit`.
- Do not ask workers to adjudicate rollback or to reinterpret an ambiguous split rematch; those are local hard stops.
