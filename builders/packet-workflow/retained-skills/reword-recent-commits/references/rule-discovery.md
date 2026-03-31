# Rule Discovery

Use this checklist before drafting replacement commit messages.

## Discovery Order

1. Read a repo-local commit instruction file if it exists.
   Common locations:
   - `.github/instructions/commit-message.instructions.md`
   - `.github/copilot-instructions.md`
   - `docs/` or `instructions/` files that mention commits or PR titles
2. Read contributor docs such as `CONTRIBUTING.md`.
3. Read maintainer docs only if contributor docs point there or they contain
   stricter writing rules.
4. Inspect recent `git log --oneline` output for recurring scopes and subjects.

## What To Extract

- Required subject format, such as `type(scope): subject`
- Allowed `type` values
- Whether `scope` is required and how specific it should be
- Subject length limit
- Imperative-mood requirements
- Body and footer rules
- Repo-specific defaults, such as preferring `fix` over `feat`
- Example scopes already used in the repo

## Commit Intent Heuristics

- Title the primary behavior or workflow change, not the file list.
- If runtime logic changed and tests or docs changed with it, keep the title on
  the logic change and mention the supporting work in the body.
- Prefer a narrower scope taken from the repo's module vocabulary over a broad
  catch-all scope.
- If the repo's rules say to prefer `fix` when uncertain, follow that instead
  of generic Conventional Commit advice.

## Subagent Split

When subagents are available:

- Ask one read-only subagent to summarize the rules and scope vocabulary.
- Ask another read-only subagent to summarize the last `n` commits from
  subjects, diffstats, and touched files.
- Keep both prompts artifact-driven. Do not hand them the message you want.
