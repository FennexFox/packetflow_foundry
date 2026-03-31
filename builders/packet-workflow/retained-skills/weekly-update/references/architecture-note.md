# Weekly Update Architecture Note

`weekly-update` keeps a hierarchical worker contract on purpose.

Flat-contract skills are the default in this environment because they are usually easier to validate, easier to keep lean, and easier for the main agent to trust. That remains true here as well. This skill is an exception, not the template.

## Why Hierarchy Is Necessary Here

`weekly-update` is not a narrow mutation workflow and not a single-decision audit. It has to:

- review many heterogeneous evidence items from one reporting window
- keep proposal-only candidate classifications separate from final local adjudication
- move candidates across final sections during local synthesis
- recompute run-level confidence locally instead of inheriting worker confidence
- control raw reread exceptions at candidate granularity, not only at batch granularity

That combination requires two distinct layers:

- `candidates[]`
  - candidate-level facts, proposed classification, evidence, ambiguity, and reread control
- `footer`
  - worker-level batch summary, overall confidence, coverage gaps, and batch risk

If these are flattened into one contract here, one of two bad outcomes follows:

- candidate-level evidence gets duplicated into every worker summary and packets bloat
- worker-level summary absorbs candidate distinctions and the main agent has to reopen raw evidence more often

The current hierarchy avoids both. It preserves candidate-local evidence while still giving the main agent one packet-level summary to compare across workers.

## Why Flat Contract Is Still The Default

Use a flat contract when the workflow is primarily:

- one object in, one decision out
- one plan in, one validated mutation out
- one focused packet in, one local judgment out

That shape usually has:

- less duplicated structure
- fewer ways for runtime and evaluation metadata to blur together
- simpler validator/apply boundaries
- easier common-path sufficiency

Most PR writeup, release-copy, docs-sync, and commit-mutation skills fit that model better than `weekly-update`.

## When Hierarchy Is Warranted

Keep hierarchy only when all of these are true:

- the worker must return multiple proposal-grade candidates from one packet
- the final local pass may materially reclassify or suppress those candidates
- batch-level confidence and coverage gaps matter separately from candidate-level evidence
- raw reread exceptions must remain candidate-scoped

If any of those stop being true, flatten the contract instead of preserving hierarchy out of habit.

## Non-Goals

This note does not justify broader runtime packets, extra local summary packets, or token-efficiency counters in runtime metadata.

- `weekly-update` stays on `orchestrator_profile=standard`
- token/size metrics stay in `packet_metrics.json` and evaluation logs
- hierarchy explains worker output shape only; it does not justify packet sprawl
