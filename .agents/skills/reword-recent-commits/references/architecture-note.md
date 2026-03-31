# Reword Recent Commits Architecture Note

This note records why `reword-recent-commits` now uses a flat/generic worker contract and when that choice should be revisited.
This pass is a metadata/doc refresh; naming migration for `task_packet_names` and `task_packet_ids` is intentionally out of scope.

## Why Flat Stays

- The real output is a local ordered rewrite plan, not a reusable cross-packet candidate inventory.
- Workers summarize rules and commit intent, but the local agent still drafts the final commit text, confirms with the user, validates the final set, and performs the history rewrite.
- There is no real runtime consumer for hierarchical `candidates[] + footer`; that metadata added ceremony without closing a safety boundary.
- The workflow gains more from a strong `collect -> build -> validate -> apply` contract than from a hierarchy that the local orchestrator never truly consumes.

## What The Flat Contract Means

- `decision_ready_packets=false`
- `worker_return_contract=generic`
- `worker_output_shape=flat`
- workers return proposal-grade summaries only
- final message synthesis, confirmation, and ref mutation stay local

## When To Revisit Hierarchy

Revisit a hierarchical model only if two or more of these become normal:

- local code repeatedly reassembles multiple worker outputs into competing per-commit candidates
- commit-level reread control becomes a recurring candidate-management problem
- one final commit message regularly depends on merging multiple packet findings into a scored candidate set
- apply-time logic starts reconstructing an intermediate candidate inventory before mutation
