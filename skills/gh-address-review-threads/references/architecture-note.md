# Address Review Threads Architecture Note

This note records why `gh-address-review-threads` currently keeps a flat/generic packet workflow and when that decision should be revisited.

## Why Flat Stays

- The core output is a local `thread_actions` execution plan, not a reusable cross-packet candidate inventory.
- Final adjudication stays local because each unresolved thread still needs local ownership checks, reply wording, fix application, and mutation gating.
- Workers analyze one `thread-batch` or one singleton `thread` packet at a time and return proposal-grade findings; they do not emit decision-ready candidates.
- The deterministic boundary that matters most here is `collect -> build -> validate -> apply`, so the workflow gains more from a strong flat contract than from an extra hierarchical synthesis layer.

## What The Flat Contract Means

- `decision_ready_packets=false`
- `worker_return_contract=generic`
- `worker_output_shape=flat`
- `packet_worker_map` routes only delegated `thread-batch-*` and eligible singleton `thread-*` packets.
- The local agent owns final decisions, final reply text, pushes, and thread resolution.
- Token-efficiency retrofit does not imply hierarchy here; runtime routing stays flat and token metrics stay evaluation-side.

## When To Revisit Hierarchy

Revisit a hierarchical result model if two or more of these become normal workflow patterns:

- local code repeatedly reassembles worker findings into candidate-like intermediate structures
- per-thread ambiguity or reread control becomes a recurring candidate-management problem
- one thread decision regularly depends on combining findings from multiple packets
- apply-time logic starts reconstructing something equivalent to `candidates[] + footer`

Until those conditions appear, a flat/generic contract is the simpler and more stable shape for this skill.
