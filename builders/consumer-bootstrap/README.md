# Consumer Bootstrap Builder

This builder initializes the minimum consumer-repo Codex layout after
vendoring PacketFlow Foundry under `.codex/vendor/packetflow_foundry`.

Primary entrypoint:
- `scripts/init_consumer_codex.py`
- `scripts/sync_project_profiles.py`

Usage:
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --repo-root <project-root>`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --bridge-mode copy`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py --bridge-mode copy-on-fail`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/sync_project_profiles.py --repo-root <project-root>`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/sync_project_profiles.py --repo-root <project-root> --dry-run`
- `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/sync_project_profiles.py --repo-root <project-root> --skill <skill-name>`

Bridge mode note:
- bootstrap now writes managed copies for agent and skill bridges by default
- rerun bootstrap after updating `.codex/vendor/packetflow_foundry` to refresh managed copies that were not modified locally
- bootstrap tracks both raw and LF-normalized hashes in `bridge-state.json` so CRLF/LF-only drift does not force a refresh or local-modification skip
- `--bridge-mode copy-on-fail` remains accepted as a deprecated compatibility alias for `copy`

Recommended vendor update flow:
- `git subtree pull --prefix=.codex/vendor/packetflow_foundry packetflow_foundry <upstream-branch> --squash`
- rerun `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/init_consumer_codex.py`
- rerun `python .codex/vendor/packetflow_foundry/builders/consumer-bootstrap/scripts/sync_project_profiles.py --repo-root <project-root>` when you want fresh project-local skill profile scaffolds and version metadata
- run the relevant consumer smoke test(s)
- inspect the resulting diff
- commit the subtree update and bootstrap refresh together

Behavior:
- creates or appends repo-root `.gitignore` with `.codex/tmp/`
- reserves `.codex/tmp/` as the repo-local scratch tree for temporary, helper, runtime-artifact, and ad hoc operator-input files that are not meant to be tracked
- creates `.codex/project/profiles/default/profile.json`
- reserves `.codex/project/profiles/<skill-name>/profile.json` for skill-specific project-local overrides
- ensures repo-root `.codex/agents/` exists as the consumer subagent discovery surface
- copies vendored foundry agent TOMLs from `.codex/vendor/packetflow_foundry/.codex/agents/<agent>.toml` into repo-root `.codex/agents/<agent>.toml`
- bootstrap-copied entries under `.codex/agents/` are managed bootstrap artifacts; update the vendor source or replace them with a project-local entry, then rerun bootstrap instead of patching the copied artifact in place
- skips agent bridge creation when a root `.codex/agents/<agent>.toml` entry already exists
- copies legacy `.codex/project/agents/<agent>.toml` only as a migration shim and emits a deprecation notice
- ensures repo-root `.agents/skills/` exists as the consumer discovery surface
- copies vendored foundry thin wrappers into repo-root `.agents/skills/<skill-name>` and rewrites wrapper `SKILL.md` references so retained kernels still resolve under `.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/<skill-name>`
- bootstrap-copied entries under `.agents/skills/` are managed bootstrap artifacts; update the vendor source or replace them with a project-local entry, then rerun bootstrap instead of patching the copied artifact in place
- skips bridge creation when a root `.agents/skills/<skill-name>` entry already exists
- copies legacy `.codex/project/skills/<skill-name>` only as a migration shim and emits a deprecation notice
- creates or appends `.codex/AGENTS.md`
- appends a short PacketFlow Foundry note to root `AGENTS.md` only when that file already exists
- keeps `AGENTS.md` handling append-only
- keeps a compatible existing `.codex/project/profiles/default/profile.json` unchanged on rerun
- aborts when conflicting non-`AGENTS.md` scaffold output already exists
- refreshes managed copies on later runs while they remain unchanged locally
- migrates legacy bootstrap symlink bridges to managed copies on rerun when they still point at the expected foundry source

Project profile sync behavior:
- creates missing `.codex/project/profiles/default/profile.json` when needed
- discovers packet-workflow thin wrappers under repo-root `.agents/skills/`
- creates missing `.codex/project/profiles/<skill-name>/profile.json` from retained default scaffolds
- normalizes project-local `kind`, `name`, `profile_path`, and `metadata.versioning`
- adds only missing nested keys from retained/default scaffolds and preserves existing semantic values
- reports `created`, `updated`, `unchanged`, `ignored`, or `manual_migration_required` in a JSON report under `.codex/tmp/project-profile-sync/` by default
- refuses to rewrite invalid, stale, or ahead-of-builder project-local profiles and leaves those for manual migration
