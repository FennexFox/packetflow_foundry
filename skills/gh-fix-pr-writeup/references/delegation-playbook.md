# Delegation Playbook

Read this file only when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`
  - no workers
- `targeted-delegation`
  - 1-2 workers
- `broad-delegation`
  - 3-4 workers
- Optional QA worker
  - only when `qa_required` is true or an explicit claim conflict triggers it

## Local Gates

- Read `rules_packet.json` locally before drafting any replacement title/body.
- Read `synthesis_packet.json` locally before final drafting.
- Keep common-path drafting on `rules_packet.json + synthesis_packet.json + <=1 focused packet`.
- Re-check the final draft against `rules_packet.json` locally before `validate_pr_writeup_edit.py`.
- Run `apply_pr_writeup.py` only from validator output.
- Treat `packet_insufficiency` as failure, not as permission to compensate with raw reread.
- Treat `packet_worker_map` as the routing authority for delegated packet analysis.

## Shared Packet Discipline

Every worker reads `global_packet.json` first.

Then give the worker only:
- one focused packet or one narrow slice from a focused packet
- any explicitly referenced file slice only when the packet cannot carry the required evidence

Do not ask workers to:
- rediscover the whole repo state from scratch
- reread long raw diffs without an explicit allowed reread reason
- draft the final user-facing PR text
- emit embedded edit code or take over the guarded `apply_pr_writeup.py` step

## Worker Roles

Prefer these roles:
- `packet_explorer`
  - `runtime_packet.json` and `process_packet.json`
- `evidence_summarizer`
  - `testing_packet.json`
- optional `docs_verifier`
  - `rules_packet.json` cross-check when the local gate still leaves ambiguity
- optional `large_diff_auditor`
  - QA cross-check only when `qa_required` is true

## Worker Output Contract

Require each worker to return exactly:
- `primary outcome`
- `evidence files`
- `unsupported claims`
- `suggested PR bullets`

For the optional QA worker, require:
- `keep_or_revise`
- `rule violations`
- `coverage gaps`
- `unsupported claims`

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use $gh-fix-pr-writeup at <skill-path> to analyze one PR packet.

Read only:
- <global-packet>
- <packet-file>
- <specific changed files if needed>

Return exactly:
- primary outcome
- evidence files
- unsupported claims
- suggested PR bullets
```

Keep each worker narrow. Do not ask one worker to cover multiple packets unless `orchestrator.json` explicitly recommends a smaller split.
