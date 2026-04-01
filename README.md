# PacketFlow Foundry

`packetflow_foundry` is a vendorable shared core for packet-first, token-efficient workflow orchestration.
It ships reusable contracts, templates, builders, overlay profiles, a default managed agent set, and reusable repo-scoped skills.

It is not a project-specific monolith.
Consumer projects should keep repo-specific profiles in `.codex/project/profiles/`, repo-specific skills in `.agents/skills/`, and project-scoped subagents in `.codex/agents/`.

Thin-entrypoint intent predates the current retained-skill layout. The earlier drift came from generator and test contracts that still emitted bundled skills under `.agents/skills/`. The current contract is enforced by layout generation and tests instead of prose alone.

## Compose Precedence

`foundry baseline -> optional foundry overlay -> project-local profile -> root .agents/skills wrapper/override surface`

## Layout

```text
packetflow_foundry/
  .agents/
    skills/
  .codex/
    agents/
    project/
      profiles/
  AGENTS.md
  README.md
  codex.example.toml
  core/
    contracts/packet-workflow/
    templates/packet-workflow/
    defaults/packet-workflow/
  profiles/
    baseline/
    packet-heavy-orchestrator/
  builders/
    consumer-bootstrap/
    packet-workflow/
      retained-skills/
  docs/
    vendoring.md
```

## Directory Roles

- `.codex/agents/`
  - Foundry default managed worker registry and the direct-repo project-scoped subagent discovery surface.
  - Vendored consumers should expose the foundry defaults and their own local agent TOMLs through repo-root `.codex/agents/`.
  - Legacy `.codex/project/agents/` entries are migration-only and should move to `.codex/agents/`.
- `core/contracts/packet-workflow/`
  - Authoritative shared semantics.
  - This is where validator/apply rules, common-path rules, profile boundaries, worker-family semantics, and evaluation-log rules live.
- `core/templates/packet-workflow/`
  - Authoritative scaffold templates consumed by the builder.
- `core/defaults/packet-workflow/`
  - Authoritative shared default values consumed by the builder.
- `profiles/`
  - Reusable overlay profiles only.
  - `baseline` is the default.
  - `packet-heavy-orchestrator` is opt-in and additive.
- `builders/packet-workflow/`
  - Builder logic, builder contract, helper scripts, and tests.
  - This builder consumes `core/`; it does not own shared semantics.
- `builders/packet-workflow/retained-skills/`
  - Authoritative retained skill kernels for reusable foundry workflows.
  - Owns reusable `builder-spec.json`, profiles, references, scripts, tests, and migration worksheets.
- `builders/consumer-bootstrap/`
  - Consumer-repo bootstrap helper for initializing the minimum project-local Codex overlay after vendoring.
  - This builder is append-only for `AGENTS.md` handling and otherwise keeps an all-or-nothing conflict policy for tracked scaffolds.
- `.agents/skills/`
  - Thin skill entrypoints only.
  - Authoritative contracts, templates, scripts, and tests must not live here.

## Managed Agents

The root `.codex/agents/` directory is the foundry's default managed agent set.
It is not a declaration that every consumer project must use only this exact global set unchanged.

The intended model is:
- foundry default managed agents under `.codex/vendor/packetflow_foundry/.codex/agents/`
- foundry thin skill wrappers under `.codex/vendor/packetflow_foundry/.agents/skills/`
- foundry authoritative retained skills under `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`
- consumer-local repo skill discovery under `.agents/skills/`
- consumer-local project-scoped subagent discovery under `.codex/agents/`
- legacy project-agent migration shim under `.codex/project/agents/`

Foundry owns reusable agent behavior semantics.
Projects should only adjust binding, selection, or routing locally.

## Using As A Vendor

Vendor the repo at `.codex/vendor/packetflow_foundry` and compose it with project-local overlays.

Typical consumer layout:

```text
project-root/
  .agents/
    skills/
  .codex/
    AGENTS.md
    agents/
    vendor/
      packetflow_foundry/
    project/
      profiles/
```

Rules:
- use foundry `profiles/baseline/profile.json` by default
- opt into `profiles/packet-heavy-orchestrator/profile.json` only when the workflow is packet-heavy
- put repo-specific profile data in `.codex/project/profiles/`
  - keep repo-wide defaults in `.codex/project/profiles/default/profile.json`
  - keep skill-specific overrides in `.codex/project/profiles/<skill-name>/profile.json`
- put repo-specific skills in repo-root `.agents/skills/`
- put repo-specific agents in `.codex/agents/`
- treat legacy `.codex/project/agents/` as migration-only
- treat legacy `.codex/project/skills/` as migration-only
- do not make repo-specific edits in the vendor subtree

Bootstrap the local overlay after vendoring:

```text
git subtree add --prefix=.codex/vendor/packetflow_foundry packetflow_foundry master --squash
python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py
```

Bootstrap now writes managed copies into repo-root `.codex/agents/` and `.agents/skills/`.
After updating `.codex/vendor/packetflow_foundry`, rerun the same bootstrap command to
refresh those managed copies while leaving locally modified copies untouched.

Bootstrap behavior:
- repo-root `.gitignore` is created or appended so `.codex/tmp/` stays ignored
- repo-local temporary, helper, scratch, and ad hoc operator-input files belong under `.codex/tmp/`, not at repo root or in tracked source directories
- root `AGENTS.md` and `.codex/AGENTS.md` are append-only targets
- repo-root `.codex/agents/` is the canonical project-scoped subagent discovery surface
- `.codex/project/profiles/default/profile.json` is a project-local scaffold, not a reusable foundry overlay
- skill-specific project-local overrides belong in `.codex/project/profiles/<skill-name>/profile.json`
- repo-root `.agents/skills/` is the canonical discovery surface in the consumer repo
- vendored foundry default agent TOMLs are copied into repo-root `.codex/agents/` unless a root entry already exists
- vendored foundry thin skill wrappers are copied into root `.agents/skills/` unless a root entry already exists
- copied skill wrappers keep resolving authoritative retained kernels from `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`
- rerunning bootstrap refreshes managed copies that still match the last managed state
- `--bridge-mode copy-on-fail` is retained only as a deprecated compatibility alias for `copy`
- legacy `.codex/project/agents/` entries are bridged only as a migration shim and should be moved to `.codex/agents/`
- legacy `.codex/project/skills/` entries are bridged only as a migration shim and should be moved to root `.agents/skills/`
- a compatible existing `.codex/project/profiles/default/profile.json` is left unchanged on rerun
- conflicting non-`AGENTS.md` bootstrap outputs still cause the helper to abort before creating or overwriting those managed artifacts, although append-only targets like `AGENTS.md` and `.gitignore` may already have been updated

See [docs/vendoring.md](./docs/vendoring.md) for the full model.

## Example Config

`codex.example.toml` is a repo convention example only.
It is not a Codex platform standard and should not be treated as one.
