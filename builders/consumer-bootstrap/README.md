# Consumer Bootstrap Builder

This builder initializes the minimum consumer-repo Codex layout after
vendoring PacketFlow Foundry under `.codex/vendor/packetflow_foundry`.

Primary entrypoint:
- `scripts/init_consumer_codex.py`

Usage:
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --repo-root <project-root>`

Behavior:
- creates `.codex/project/profiles/default/profile.json`
- reserves `.codex/project/profiles/<skill-name>/profile.json` for skill-specific project-local overrides
- ensures repo-root `.codex/agents/` exists as the consumer subagent discovery surface
- creates file-symlink bridges from repo-root `.codex/agents/<agent>.toml` to `.codex/vendor/packetflow_foundry/.codex/agents/<agent>.toml`
- skips agent bridge creation when a root `.codex/agents/<agent>.toml` entry already exists
- bridges legacy `.codex/project/agents/<agent>.toml` only as a migration shim and emits a deprecation notice
- ensures repo-root `.agents/skills/` exists as the consumer discovery surface
- creates directory-symlink bridges from repo-root `.agents/skills/<skill-name>` to `.codex/vendor/packetflow_foundry/.agents/skills/<skill-name>`
- bridges thin wrappers only; authoritative retained kernels stay under `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/<skill-name>`
- skips bridge creation when a root `.agents/skills/<skill-name>` entry already exists
- bridges legacy `.codex/project/skills/<skill-name>` only as a migration shim and emits a deprecation notice
- creates or appends `.codex/AGENTS.md`
- appends a short PacketFlow Foundry note to root `AGENTS.md` only when that file already exists
- keeps `AGENTS.md` handling append-only
- aborts the entire run when any tracked non-`AGENTS.md` scaffold output already exists
- aborts on symlink creation failure instead of copying skills
