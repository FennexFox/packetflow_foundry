# Contributing

`packetflow_foundry` is a shared foundry, not a consumer-project home.
Keep repo-specific profiles, skills, agents, and one-off workflow policy
out of this repository unless they are meant to be reusable upstream.

## What belongs here

Changes are a good fit for this repo when they improve reusable foundry
behavior such as:
- shared packet-workflow contracts, templates, and defaults
- reusable builder logic and regression coverage
- reusable overlay profiles
- default managed agents that should ship with the foundry
- general documentation for vendoring or operating the foundry

Changes are usually not a fit when they only support one consumer repo.
Put repo-specific profiles in `.codex/project/profiles/`, repo-specific
skills in `.agents/skills/`, and project-scoped subagents in
`.codex/agents/` in the consumer repository instead.

## Commit messages

The canonical rules live in
`.github/instructions/commit-message.instructions.md`.

Use Conventional Commits:
- `<type>(<scope>): <subject>`

Repository-specific guidance:
- `scope` is required
- prefer concrete surfaces such as `contracts`, `templates`,
  `defaults`, `builders`, `profiles`, or `agents`
- if a shared behavior change also updates docs/tests/config, title the
  shared behavior change rather than the support work

## Pull requests

The canonical rules live in
`.github/instructions/pull-request.instructions.md`.

Prefer filling `.github/pull_request_template.md`.

PRs should describe:
- what changed
- why the change exists
- how the change works
- what validation ran
- whether vendored consumers need to do anything
- what risks or rollback paths matter

## Issues

Prefer the repository issue templates:
- Bug report -> `bug`
- Feature request -> `enhancement`
- Release checklist -> `release`

Maintainers may add one `area:` label for the primary reusable foundry
surface and may use `question`, `duplicate`, `invalid`, or `wontfix`
for triage or disposition.

See `MAINTAINING.md` for the canonical label taxonomy and maintenance
rules.

## Change discipline

Keep shared semantics authoritative in `core/`.
Profiles can carry reusable values and defaults, but not executable
behavior or prompt fragments that redefine foundry semantics.

When a change touches `core/contracts`, `core/templates`, or
`core/defaults`, update `builders/` and the relevant tests in the same
change.

Do not add duplicate authoritative copies of contracts, templates,
scripts, or tests under `.agents/skills/`.

## Validation

Run the narrowest relevant validation for the surfaces you changed and
record it in the PR description.

Examples:
- builder tests when `builders/` changes
- generation or fixture validation when templates/defaults change
- manual doc review when contributor-facing instructions change

If you did not run validation, say so explicitly and explain why.
