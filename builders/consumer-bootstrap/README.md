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
- creates `.codex/project/agents/.gitkeep`
- ensures repo-root `.agents/skills/` exists as the consumer discovery surface
- creates directory-symlink bridges from repo-root `.agents/skills/<skill-name>` to `.codex/vendor/packetflow_foundry/.agents/skills/<skill-name>`
- skips bridge creation when a root `.agents/skills/<skill-name>` entry already exists
- bridges legacy `.codex/project/skills/<skill-name>` only as a migration shim and emits a deprecation notice
- creates or appends `.codex/AGENTS.md`
- appends a short PacketFlow Foundry note to root `AGENTS.md` only when that file already exists
- keeps `AGENTS.md` handling append-only
- aborts the entire run when any tracked non-`AGENTS.md` scaffold output already exists
- aborts on symlink creation failure instead of copying skills
