# Packet Workflow Core Contract

This directory is the authoritative home for shared packet-workflow semantics in PacketFlow Foundry.

## Shared Runtime Surface

Every packet-workflow scaffold uses:
- `orchestrator.json`
- `global_packet.json`
- one or more focused packets

Optional runtime additions:
- `batch-packet-01.json` when grouped work items are justified
- `synthesis_packet.json` only when the `packet-heavy-orchestrator` overlay is selected

## Shared Repo-Local Temporary File Policy

- Use `.codex/tmp/` as the canonical gitignored repo-local scratch tree for
  temporary, helper, runtime-artifact, and ad hoc operator-input files.
- If a transient file must live inside the repo, place it under `.codex/tmp/`
  rather than the repo root or another tracked directory.
- Evaluation logs may default outside the repo under `~/.codex/tmp/`; if a
  repo-local fallback is required, keep it under `.codex/tmp/` as well.

## Shared Review Modes

The shared modes are:
- `local-only`
- `targeted-delegation`
- `broad-delegation`

Default review-mode support and default override signals live in `../../defaults/packet-workflow/review-modes.json`.

## Shared Default Authority And Stops

Default authority order lives in `../../defaults/packet-workflow/authority-order.json`.
Default stop conditions live in `../../defaults/packet-workflow/stop-taxonomy.json`.

Profiles may select or tighten behavior around these defaults, but they must not redefine their meaning.

## Related Contracts

- `validator-apply-contract.md`
- `common-path-contract.md`
- `worker-family-contract.md`
- `profile-boundary-contract.md`
- `evaluation-log-contract.md`
- `pattern-catalog.md`

## Composition Boundary

Compose shared and local inputs in this order:

`foundry baseline -> optional foundry overlay -> project-local profile -> project-local skill/agent overrides`
