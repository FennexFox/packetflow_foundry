# Consumer Bootstrap Builder

This builder initializes the minimum consumer-repo Codex layout after
vendoring PacketFlow Foundry under `.codex/vendor/packetflow_foundry`.

Primary entrypoint:
- `scripts/init_consumer_codex.py`

Usage:
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --repo-root <project-root>`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --bridge-mode copy-on-fail`

Windows note:
- this helper creates filesystem symlinks for agent and skill bridges
- run it from an elevated PowerShell window (`Run as Administrator`) unless Windows Developer Mode is enabled
- without symlink permission, bootstrap can create early scaffold outputs and then abort on the first bridge
- if you cannot grant symlink permission, use `--bridge-mode copy-on-fail` to write managed copies instead

Behavior:
- creates or appends repo-root `.gitignore` with `.codex/tmp/`
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
- keeps a compatible existing `.codex/project/profiles/default/profile.json` unchanged on rerun
- aborts when conflicting non-`AGENTS.md` scaffold output already exists
- default `symlink` mode aborts on symlink creation failure instead of silently copying bridges
- optional `--bridge-mode copy-on-fail` retries failed bridges as managed copies and refreshes them on later runs while they remain unchanged locally
