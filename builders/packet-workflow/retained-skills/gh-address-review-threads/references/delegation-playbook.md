# Delegation Playbook

Read this file only when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`
  - no workers
- `targeted-delegation`
  - 1-2 analysis workers
- `broad-delegation`
  - 3-4 analysis workers
- Optional QA worker
  - only when worker findings conflict or a broad fix needs a second coverage pass

## Packet Order

- Every worker reads `global_packet.json` first.
- Prefer `thread-batch-*.json` when it exists.
- Read singleton `thread-*.json` only for threads not covered by a batch.
- Keep each worker on exactly one routed packet.
- Treat `packet_worker_map` as the routing authority for delegated thread analysis.

## Shared Context

`global_packet.json` keeps all workers aligned on:
- PR intent
- user-visible impact
- reply-marker rules
- outdated-thread policy
- context fingerprint
- local reply contract
- code-change delegation guardrails
- review mode overrides
- worker selection guidance
- worker return contract
- worker output shape
- xHigh reread policy

Thread packets may also include existing self-authored replies. Keep that context in view and surface any mismatch between the existing reply and the current reviewer request in `problem summary` or `risk` so the main agent can reconcile it before choosing a decision.

## Analysis Worker Contract

Prefer `packet_explorer`.

Return exactly:
- `thread ids`
- `problem summary`
- `fix direction`
- `risk`
- `files to edit`
- `tests to run`

Do not draft the final acknowledgement or completion reply in the worker output. The main agent owns final wording.

## Local Validation Gate

- draft raw `thread_actions` locally
- run `validate_thread_action_plan.py` before any apply step
- keep apply on the normalized validator output only
- if `context_fingerprint` changed, rebuild packets and revalidate instead of forcing apply

## Code-Change Delegation Guardrails

Use a worker for code edits only when all of these are true:
- one batch or one thread
- two files or fewer
- one subsystem
- no schema, public interface, config, or workflow changes
- validation path is clear

If any guardrail fails, keep the implementation local and use mini workers only for analysis.

## QA Pass

Prefer `large_diff_auditor` or explicit `gpt-5.4-mini`.

Provide:
- `global_packet.json`
- the relevant `thread-batch-*.json` or `thread-*.json`
- the proposed completion reply
- the changed files or diff slice being resolved

Require:
- `thread ids`
- `resolution verdict`
- `coverage gaps`
- `unsupported claims`
- `remaining risk`

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use $gh-address-review-threads at <skill-path> to analyze PR review-thread packets.

Read only:
- <global-packet>
- <thread-batch-or-thread-packets>
- <specific file slice if needed>

Return exactly:
- thread ids
- problem summary
- fix direction
- risk
- files to edit
- tests to run
```

Keep each worker narrow. Do not ask a worker to reread the whole PR conversation or whole diff.
