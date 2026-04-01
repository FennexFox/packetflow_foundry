# Vendoring PacketFlow Foundry

Use `packetflow_foundry` as a vendor subtree at `.codex/vendor/packetflow_foundry`.

## Compose Model

Compose in this order:

`foundry baseline -> optional foundry overlay -> project-local profile -> root .agents/skills wrapper/override surface`

Meaning:
- start from `profiles/baseline/profile.json`
- optionally add `profiles/packet-heavy-orchestrator/profile.json`
- add repo-specific profile data from `.codex/project/profiles/`
  - keep repo-wide defaults in `.codex/project/profiles/default/profile.json`
  - keep skill-specific overrides in `.codex/project/profiles/<skill-name>/profile.json`
- copy reusable foundry default agent TOMLs from `.codex/vendor/packetflow_foundry/.codex/agents/` into repo-root `.codex/agents/` as managed bootstrap artifacts
- expose repo-scoped skills from repo-root `.agents/skills/`
- copy reusable foundry thin wrappers from `.codex/vendor/packetflow_foundry/.agents/skills/` into the root discovery surface as managed bootstrap artifacts
- keep authoritative retained kernels in `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`

## Recommended Consumer Layout

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

Bootstrap the local overlay after vendoring:

```text
git subtree add --prefix=.codex/vendor/packetflow_foundry packetflow_foundry master --squash
python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py
```

Bootstrap now writes managed copies into repo-root `.codex/agents/` and `.agents/skills/`.
Those bootstrap-copied entries are managed artifacts only when they came from the
vendor subtree; do not patch those copied artifacts in place. Update the vendor source
or replace the entry with a project-local one, then rerun bootstrap.
After updating `.codex/vendor/packetflow_foundry`, rerun the same bootstrap command to
refresh those managed copies while leaving locally modified copies untouched.

Recommended update flow:

```text
git subtree pull --prefix=.codex/vendor/packetflow_foundry packetflow_foundry <upstream-branch> --squash
python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py
<run the relevant consumer smoke test(s)>
git diff
git commit
```

Bootstrap notes:
- repo-root `.gitignore` is created or appended so `.codex/tmp/` stays ignored
- repo-local temporary, helper, scratch, and ad hoc operator-input files belong under `.codex/tmp/`, not at repo root or in tracked source directories
- root `AGENTS.md` and `.codex/AGENTS.md` are append-only targets
- repo-root `.codex/agents/` is the canonical consumer subagent location
- `.codex/project/profiles/default/profile.json` is a project-local scaffold, not a reusable foundry overlay
- skill-specific project-local overrides belong in `.codex/project/profiles/<skill-name>/profile.json`
- vendored foundry default agent TOMLs are copied into repo-root `.codex/agents/` unless a root entry already exists
- repo-root `.agents/skills/` is the canonical consumer skill location
- vendored foundry thin wrappers are copied into root `.agents/skills/` unless a root entry already exists
- copied skill wrappers keep resolving authoritative retained kernels from `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`
- rerunning bootstrap refreshes managed copies that still match the last managed state
- `bridge-state.json` stores both raw and LF-normalized hashes so CRLF/LF-only drift does not trigger a refresh or local-modification warning
- `--bridge-mode copy-on-fail` is retained only as a deprecated compatibility alias for `copy`
- legacy `.codex/project/agents/` is deprecated and bridged only for migration
- legacy `.codex/project/skills/` is deprecated and bridged only for migration
- a compatible existing `.codex/project/profiles/default/profile.json` is left unchanged on rerun
- conflicting non-`AGENTS.md` bootstrap outputs still cause the helper to abort before creating or overwriting those managed artifacts, although append-only targets like `AGENTS.md` and `.gitignore` may already have been updated

## What Stays In The Vendor

Keep these in the foundry vendor subtree:
- shared contracts and templates
- reusable overlay profiles
- reusable builder logic
- reusable default managed agent registry under `.codex/vendor/packetflow_foundry/.codex/agents/`
- reusable foundry thin skill entrypoints under `.codex/vendor/packetflow_foundry/.agents/skills/`
- reusable foundry retained kernels under `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/`

## What Stays Outside The Vendor

Keep these in the consumer repo root or `.codex/project/`:
- repo-specific profile data in `.codex/project/profiles/`
  - repo-wide scaffold defaults in `.codex/project/profiles/default/profile.json`
  - skill-specific overrides in `.codex/project/profiles/<skill-name>/profile.json`
- repo-specific agents in `.codex/agents/`
- repo-specific skills in `.agents/skills/`
- legacy `.codex/project/agents/` only as a migration shim
- project-only overrides that should not be upstreamed

## No Direct Vendor Edits For Local Needs

Do not edit `.codex/vendor/packetflow_foundry` to satisfy one project's local layout.
Make those changes in repo-root `.agents/skills/`, repo-root `.codex/agents/`, or `.codex/project/` instead.

Edit the vendor subtree directly only when:
- fixing a reusable foundry bug
- adding a reusable foundry capability
- changing shared contracts or templates that should be kept upstream
