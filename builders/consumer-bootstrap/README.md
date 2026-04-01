# Consumer Bootstrap Builder

This builder initializes the minimum consumer-repo Codex layout after
vendoring PacketFlow Foundry under `.codex/vendor/packetflow_foundry`.

Primary entrypoint:
- `scripts/init_consumer_codex.py`

Usage:
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --repo-root <project-root>`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --bridge-mode copy`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --bridge-mode copy-on-fail`

Bridge mode note:
- bootstrap now writes managed copies for agent and skill bridges by default
- rerun bootstrap after updating `.codex/vendor/packetflow_foundry` to refresh managed copies that were not modified locally
- `--bridge-mode copy-on-fail` remains accepted as a deprecated compatibility alias for `copy`

Behavior:
- creates or appends repo-root `.gitignore` with `.codex/tmp/`
- reserves `.codex/tmp/` as the repo-local scratch tree for temporary, helper, runtime-artifact, and ad hoc operator-input files that are not meant to be tracked
- creates `.codex/project/profiles/default/profile.json`
- reserves `.codex/project/profiles/<skill-name>/profile.json` for skill-specific project-local overrides
- ensures repo-root `.codex/agents/` exists as the consumer subagent discovery surface
- copies vendored foundry agent TOMLs from `.codex/vendor/packetflow_foundry/.codex/agents/<agent>.toml` into repo-root `.codex/agents/<agent>.toml`
- skips agent bridge creation when a root `.codex/agents/<agent>.toml` entry already exists
- copies legacy `.codex/project/agents/<agent>.toml` only as a migration shim and emits a deprecation notice
- ensures repo-root `.agents/skills/` exists as the consumer discovery surface
- copies vendored foundry thin wrappers into repo-root `.agents/skills/<skill-name>` and rewrites wrapper `SKILL.md` references so retained kernels still resolve under `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/<skill-name>`
- skips bridge creation when a root `.agents/skills/<skill-name>` entry already exists
- copies legacy `.codex/project/skills/<skill-name>` only as a migration shim and emits a deprecation notice
- creates or appends `.codex/AGENTS.md`
- appends a short PacketFlow Foundry note to root `AGENTS.md` only when that file already exists
- keeps `AGENTS.md` handling append-only
- keeps a compatible existing `.codex/project/profiles/default/profile.json` unchanged on rerun
- aborts when conflicting non-`AGENTS.md` scaffold output already exists
- refreshes managed copies on later runs while they remain unchanged locally
- migrates legacy bootstrap symlink bridges to managed copies on rerun when they still point at the expected foundry source
