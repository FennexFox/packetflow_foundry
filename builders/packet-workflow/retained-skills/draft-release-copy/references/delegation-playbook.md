# Delegation Playbook

Read this file only when `orchestrator.json` sets `review_mode` to `targeted-delegation` or `broad-delegation`.

## Worker Budget

- `local-only`: no workers
- `targeted-delegation`: 1-2 analysis workers
- `broad-delegation`: 3-4 analysis workers
- Optional QA worker: only when packet findings conflict or broad mutation needs a final coverage pass

## Packet Order

- Every worker reads `global_packet.json` first.
- Prefer `batch-packet-*.json` when it exists and the orchestrator points to grouped work.
- Read singleton focused packets only for work not covered by a batch.
- Keep each worker on one small packet slice.

## Shared Context

`global_packet.json` keeps all workers aligned on:
- workflow family
- primary goal
- authority order
- stop conditions
- review mode overrides
- preferred worker families
- packet worker map when configured
- worker selection guidance
- worker return contract
- worker output shape
- xHigh reread policy
- candidate field bundles when decision-ready packets are enabled
- worker footer fields when hierarchical output is enabled
- reread reason values when decision-ready packets are enabled
- domain overlay semantics when configured
- optional local helper policy

## Worker Return Modes

- `generic`
  - Use for simple workflows where the local orchestrator mainly needs a narrow outcome and evidence pointers.
- `classification-oriented`
  - Use for adjudication-heavy workflows where final adjudication stays local but workers must return proposal-grade candidate records.
  - Prefer hierarchical `candidates[] + footer` output.

## Worker Families

- Preferred worker families for this scaffold:
- `context_findings`: mapping, packet-scoped code analysis, touched-surface, and packet-membership findings
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
- `verifiers`: narrow claim or version-sensitive verification
  - `docs_verifier`
- Surfaced optional worker list below is the delegated-mode exposed list after stable dedupe and after subtracting explicitly mapped recommended worker types:
- `repo_mapper`
- `packet_worker_map` is the routing authority when configured.
- The same agent type may appear on multiple packets when those assignments are intentional.
- `publish_packet`
  - `packet_explorer`
- `readme_packet`
  - `packet_explorer`
- `changes_packet`
  - `evidence_summarizer`
- `checklist_packet`
  - `docs_verifier`
- `evidence_packet`
  - `docs_verifier`
- `worker_selection_guidance` is explanatory only and does not override `packet_worker_map`.
- Guidance notes:
  - Use `repo_mapper` when packet membership, execution path, touched surfaces, or authority mapping is unclear.
  - Use `packet_explorer` when one focused packet needs narrow code, behavior, or workflow analysis grounded by only the explicitly referenced file slices.
  - Use `docs_verifier` only when a disputed claim, version-sensitive assumption, or policy interpretation needs exact verification.
  - Use `evidence_summarizer` for long narrative evidence that should be condensed into decision-ready candidate records.
  - Use `large_diff_auditor` for large diffs, high-risk hotspots, regressions, invariants, and missing tests.
  - Use `log_triager` for logs, CI failures, runtime incidents, and earliest-useful-signal triage.
  - Treat `worker_selection_guidance` as explanatory only. `packet_worker_map` is the concrete routing authority when configured.

## Analysis Worker Contract

Prefer the named worker families above before falling back to an unspecified narrow `gpt-5.4-mini` worker.

- Active worker return contract: `generic`.
- Active worker output shape: `flat`.
- Return exactly:
  - `packet ids`
  - `primary outcome`
  - `evidence files`
  - `recommended next step`
  - `risk`
  - `tests or checks`

Do not draft the final user-facing response in worker output. The main agent owns final synthesis.
Final plan confidence is recomputed locally even when worker confidence signals are present.

## Mutation Guardrails

- Keep final mutation local unless the generated skill explicitly narrows a safe worker-owned edit slice.
- If the skill handles repo or remote mutations, do not ask a worker to own the whole mutation path from scratch.
- If findings conflict, keep the result local and add QA instead of widening worker scope.

## Prompt Skeleton

Use a prompt shaped like this:

```text
Use $draft-release-copy to analyze packet-driven workflow inputs.

Read only:
- <global-packet>
- <focused-packet-or-batch-packet>
- <specific file slice if needed>

Return exactly:
- packet ids
- primary outcome
- evidence files
- recommended next step
- risk
- tests or checks
```

Keep each worker narrow. Do not ask a worker to rediscover the whole repo state from scratch.
