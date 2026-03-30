# PacketFlow Foundry

`packetflow_foundry` is a vendorable shared core for packet-first, token-efficient workflow orchestration.
It ships reusable contracts, templates, builders, overlay profiles, and a default managed agent set.

It is not a project-specific monolith.
Consumer projects should keep repo-specific profiles, skills, and agents outside the foundry in `.codex/project/`.

## Compose Precedence

`foundry baseline -> optional foundry overlay -> project-local profile -> project-local skill/agent overrides`

## Layout

```text
packetflow_foundry/
  AGENTS.md
  README.md
  codex.example.toml
  agents/
  core/
    contracts/packet-workflow/
    templates/packet-workflow/
    defaults/packet-workflow/
  profiles/
    baseline/
    packet-heavy-orchestrator/
  builders/
    packet-workflow/
  skills/
    packet-workflow-skill-builder/
  docs/
    vendoring.md
```

## Directory Roles

- `agents/`
  - Foundry default managed worker registry.
  - Consumer projects can add `.codex/project/agents/` as additive overrides.
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
- `skills/packet-workflow-skill-builder/`
  - Thin skill entrypoint only.
  - Authoritative contracts, templates, scripts, and tests must not live here.

## Managed Agents

The root `agents/` directory is the foundry's default managed agent set.
It is not a declaration that every consumer project must use only this exact global set unchanged.

The intended model is:
- foundry default managed agents under `.codex/vendor/packetflow_foundry/agents/`
- project-local additive overrides under `.codex/project/agents/`

Foundry owns reusable agent behavior semantics.
Projects should only adjust binding, selection, or routing locally.

## Using As A Vendor

Vendor the repo at `.codex/vendor/packetflow_foundry` and compose it with project-local overlays.

Typical consumer layout:

```text
project-root/
  .codex/
    AGENTS.md
    vendor/
      packetflow_foundry/
    project/
      profiles/
      skills/
      agents/
```

Rules:
- use foundry `profiles/baseline/profile.json` by default
- opt into `profiles/packet-heavy-orchestrator/profile.json` only when the workflow is packet-heavy
- put repo-specific profile data in `.codex/project/profiles/`
- put repo-specific skills and agents in `.codex/project/`
- do not make repo-specific edits in the vendor subtree

See [docs/vendoring.md](./docs/vendoring.md) for the full model.

## Example Config

`codex.example.toml` is a repo convention example only.
It is not a Codex platform standard and should not be treated as one.
