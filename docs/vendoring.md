# Vendoring PacketFlow Foundry

Use `packetflow_foundry` as a vendor subtree at `.codex/vendor/packetflow_foundry`.

## Compose Model

Compose in this order:

`foundry baseline -> optional foundry overlay -> project-local profile -> project-local skill/agent overrides`

Meaning:
- start from `profiles/baseline/profile.json`
- optionally add `profiles/packet-heavy-orchestrator/profile.json`
- add repo-specific profile data from `.codex/project/profiles/`
- layer project-local skills and agents from `.codex/project/skills/` and `.codex/project/agents/`

## Recommended Consumer Layout

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

## What Stays In The Vendor

Keep these in the foundry vendor subtree:
- shared contracts and templates
- reusable overlay profiles
- reusable builder logic
- reusable default managed agent registry

## What Stays Outside The Vendor

Keep these in `.codex/project/`:
- repo-specific profile data
- repo-specific skills
- repo-specific agent bindings or additive agents
- project-only overrides that should not be upstreamed

## No Direct Vendor Edits For Local Needs

Do not edit `.codex/vendor/packetflow_foundry` to satisfy one project's local layout.
Make those changes in `.codex/project/` instead.

Edit the vendor subtree directly only when:
- fixing a reusable foundry bug
- adding a reusable foundry capability
- changing shared contracts or templates that should be kept upstream
