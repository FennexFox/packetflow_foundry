# Worker Family Contract

Shared worker families:
- `context_findings`
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
- `candidate_producers`
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `verifiers`
  - `docs_verifier`

Routing rules:
- `worker_selection_guidance` is descriptive metadata only
- `packet_worker_map` is the routing authority when present
- `orchestrator.json.spawn_plan` is the execution-ready materialization of that routing
- family overlap is allowed
- surfaced optional workers are deduped after family composition

Projects may adjust worker selection defaults locally.
They should not redefine shared worker behavior semantics in profiles.
