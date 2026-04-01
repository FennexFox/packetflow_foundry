# PacketFlow Foundry AGENTS

This `AGENTS.md` governs the `packetflow_foundry` subtree itself.
It does not try to map or govern an entire consumer project.

## Identity

`packetflow_foundry` is a vendorable shared core for:
- packet-first workflow orchestration
- token-efficient packet and subagent patterns
- reusable contracts, templates, builders, and managed agents

It is not a project-specific monolith.
Repo-specific profiles belong in `.codex/project/profiles/`, repo-specific skills in `.agents/skills/`, and project-scoped subagents in `.codex/agents/`.

## Directory Ownership

- `.codex/agents/`
  - Foundry default managed worker registry and the direct-repo project-scoped subagent discovery surface.
  - This is the reusable default set shipped by the foundry, not a claim that every consumer project must use only these agents.
  - When vendored, bridge the foundry defaults into the consumer repo-root `.codex/agents/`.
  - Legacy `.codex/project/agents/` entries are migration-only and should move to `.codex/agents/`.
- `.codex/tmp/`
  - Gitignored repo-local scratch tree for temporary, helper, runtime-artifact, and ad hoc operator-input files that are not meant to be tracked.
  - If a workflow needs a repo-local temp file, keep it under `.codex/tmp/` rather than the repo root or another tracked directory.
  - Packet-workflow artifacts belong under `.codex/tmp/packet-workflow/`; repo-local evaluation-log fallbacks belong under `.codex/tmp/evaluation_logs/`.
- `core/`
  - Authoritative home for cross-project behavior semantics, contracts, templates, and shared defaults.
- `profiles/`
  - Reusable foundry overlay profiles only.
  - `baseline` is the default overlay.
  - `packet-heavy-orchestrator` is an opt-in upper overlay.
- `builders/`
  - Builder logic, builder-specific contracts, generators, and tests that consume `core/`.
- `builders/packet-workflow/retained-skills/`
  - Authoritative retained skill kernels.
  - Owns reusable builder specs, profiles, references, scripts, tests, and migration worksheets for foundry packet workflows.
- `.agents/skills/`
  - Thin skill entrypoints only.
  - Do not place authoritative contracts, templates, scripts, or tests here.

## Core Versus Profile

Keep in `core/`:
- validator/apply semantics
- stop taxonomy meaning
- common-path contract semantics
- worker-family and routing semantics
- packet schema and template semantics
- shared default authority order and review-mode defaults

Allowed in reusable or project-local profiles:
- repo-specific or overlay-specific values
- paths and globs
- review-doc lists
- lint and review defaults
- worker selection defaults and binding metadata
- notes

Never move into profiles:
- executable hooks
- prompt fragments that define behavior
- packet routing authority
- validator/apply behavior
- stop taxonomy meaning
- token-budget or common-path semantics

See `core/contracts/packet-workflow/profile-boundary-contract.md` for the authoritative boundary.

## Managed Agents

Foundry core owns reusable agent behavior semantics.
Consumer projects may adjust binding, selection, and routing locally, but should not fork shared semantics for repo-specific convenience.

Use this model when vendored:
- foundry default managed set: `.codex/vendor/packetflow_foundry/.codex/agents/`
- foundry thin skill wrapper surface: `.codex/vendor/packetflow_foundry/.agents/skills/`
- foundry authoritative retained skill source: `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`
- consumer-local skill discovery surface: `.agents/skills/`
- consumer-local subagent discovery surface: `.codex/agents/`
- legacy project-agent shim: `.codex/project/agents/`

## Vendoring Rules

When this repo is used as `.codex/vendor/packetflow_foundry`:
- do not make repo-specific edits inside the vendor subtree
- put repo-specific profiles in `.codex/project/profiles/`
- put repo-specific skills in `.agents/skills/`
- put repo-specific agents in `.codex/agents/`
- treat legacy `.codex/project/agents/` as migration-only, not canonical
- treat legacy `.codex/project/skills/` as migration-only, not canonical

Direct vendor edits are reserved for reusable fixes or reusable capability additions that should be kept upstream in the foundry.

## Change Discipline

- If you change `core/contracts`, `core/templates`, or `core/defaults`, update `builders/` and builder tests in the same change.
- If you add a new foundry profile, it must be reusable across multiple repos. Otherwise keep it in `.codex/project/profiles/`.
- Do not reintroduce duplicate authoritative copies of contracts, templates, scripts, or tests under `.agents/skills/`.
- Treat `codex.example.toml` as a repo convention example only, not a Codex platform standard.
