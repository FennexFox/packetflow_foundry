# Consumer Bootstrap Builder

This builder initializes the minimum consumer-repo `.codex` layout after
vendoring PacketFlow Foundry under `.codex/vendor/packetflow_foundry`.

Primary entrypoint:
- `scripts/init_consumer_codex.py`

Usage:
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --repo-root <project-root>`

Behavior:
- creates `.codex/project/profiles/default/profile.json`
- creates `.codex/project/skills/.gitkeep`
- creates `.codex/project/agents/.gitkeep`
- creates or appends `.codex/AGENTS.md`
- appends a short PacketFlow Foundry note to root `AGENTS.md` only when that file already exists
- keeps `AGENTS.md` handling append-only
- aborts the entire run when any non-`AGENTS.md` output already exists
