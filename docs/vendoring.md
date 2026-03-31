# Vendoring PacketFlow Foundry

Use `packetflow_foundry` as a vendor subtree at `.codex/vendor/packetflow_foundry`.

## Compose Model

Compose in this order:

`foundry baseline -> optional foundry overlay -> project-local profile -> root .agents/skills override surface`

Meaning:
- start from `profiles/baseline/profile.json`
- optionally add `profiles/packet-heavy-orchestrator/profile.json`
- add repo-specific profile data from `.codex/project/profiles/`
- expose repo-scoped skills from repo-root `.agents/skills/`
- bridge reusable foundry skills from `.codex/vendor/packetflow_foundry/.agents/skills/` into the root discovery surface

## Recommended Consumer Layout

```text
project-root/
  .agents/
    skills/
  .codex/
    AGENTS.md
    vendor/
      packetflow_foundry/
    project/
      profiles/
      agents/
```

Bootstrap the local overlay after vendoring:

```text
git subtree add --prefix=.codex/vendor/packetflow_foundry packetflow_foundry master --squash
python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py
```

Bootstrap notes:
- root `AGENTS.md` and `.codex/AGENTS.md` are append-only targets
- `.codex/project/profiles/default/profile.json` is a project-local scaffold, not a reusable foundry overlay
- repo-root `.agents/skills/` is the canonical consumer skill location
- vendored foundry skills are bridged into root `.agents/skills/` unless a root entry already exists
- legacy `.codex/project/skills/` is deprecated and bridged only for migration
- if any tracked non-`AGENTS.md` bootstrap output already exists, the helper aborts without writing files
- if symlink creation fails, the helper aborts with environment guidance instead of copying skills

## What Stays In The Vendor

Keep these in the foundry vendor subtree:
- shared contracts and templates
- reusable overlay profiles
- reusable builder logic
- reusable default managed agent registry
- reusable foundry skill entrypoints under `.codex/vendor/packetflow_foundry/.agents/skills/`

## What Stays Outside The Vendor

Keep these in the consumer repo root or `.codex/project/`:
- repo-specific profile data in `.codex/project/profiles/`
- repo-specific skills in `.agents/skills/`
- repo-specific agent bindings or additive agents in `.codex/project/agents/`
- project-only overrides that should not be upstreamed

## No Direct Vendor Edits For Local Needs

Do not edit `.codex/vendor/packetflow_foundry` to satisfy one project's local layout.
Make those changes in repo-root `.agents/skills/` or `.codex/project/` instead.

Edit the vendor subtree directly only when:
- fixing a reusable foundry bug
- adding a reusable foundry capability
- changing shared contracts or templates that should be kept upstream
