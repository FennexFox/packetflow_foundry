# Commit Message Instructions

This file is the canonical source for generated commit messages in this
repository. Read it before drafting commit text.

When asked to generate a commit message, output only the final commit
message.

## Format
- For ordinary commits and squash-merge commit text, use Conventional
  Commits:
  - `<type>(<scope>): <subject>`
  - Body and footer are optional.
  - If a body is present, separate subject, body, and footer with blank
    lines.

## PR Merge Commits
- For PR merge commits into long-running branches, use the PR title
  exactly as the merge commit subject.
- Leave the body empty unless the merge itself adds release or
  integration context not already captured in the PR description.
- Do not use `Merge pull request #123 from ...` as the subject.

## Types
Use one of:
- `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
  `ci`, `chore`, `revert`

## Type Selection (strict)
- Choose `feat` only for a clearly new reusable capability, new reusable
  profile, new builder workflow, or new managed-agent behavior.
- Choose `fix` for behavior correction, compatibility alignment, broken
  generation, incorrect vendoring guidance, or keeping existing foundry
  workflows usable.
- Choose `refactor` only when behavior is unchanged and the change is
  primarily structural.
- Choose `test` only when the meaningful change is limited to tests or
  test infrastructure.
- If shared behavior changed and tests/docs/config changed alongside it,
  do not choose `test` or `docs`; title the logic or contract change and
  mention the supporting work in the body instead.
- If a change touches `core/contracts`, `core/templates`, or
  `core/defaults` together with `builders/` or tests, title the primary
  shared behavior change rather than the follow-up sync work.
- If uncertain between `feat` and `fix`, choose `fix`.

## Scopes
- `scope` is required.
- Prefer the concrete changed surface. If unsure, choose one of:
  - `agents`, `builders`, `contracts`, `defaults`, `templates`,
    `profiles`, `skills`, `docs`, `tests`, `infra`, `config`
- Prefer `contracts`, `defaults`, or `templates` over generic `core`
  when one core surface is primary.
- Keep scope lowercase and short (1-2 words).

## Subject Rules
- Imperative mood: "add", "fix", "remove", "align", "clarify",
  "prevent", "rename"
- 50 characters or fewer
- No trailing period
- Describe the primary behavior or workflow intent, not the file list.
- Do not let tests, deleted files, or doc cleanup override the subject
  when they only support a behavior change.
- Avoid generic subjects like "update files", "clean up repo", or "add
  tests for behavior" when a more specific shared intent is visible in
  the diff.
- Prefer the narrowest real module or behavior scope.

## Body Rules (only when needed)
Add a body when:
- more than one file changed, or
- a new file/system/component was added, or
- behavior changed in a way reviewers should verify, or
- consumer adoption or migration notes matter

Body should:
- explain what changed and why
- wrap lines at about 72 chars
- use 2-4 bullets
- each bullet starts with `- ` and an imperative verb

## Breaking Changes
- If breaking, add `!` after type or scope, e.g. `feat(templates)!: ...`
- Add footer:
  - `BREAKING CHANGE: <what breaks and what to do>`

## References
- If an issue or PR number is known from context, add:
  - `Refs: #123`

## Examples
- `fix(builders): preserve validator defaults in generated output`
- `feat(templates): add common packet review scaffolding`
- `docs(contracts): clarify profile boundary contract`
- `test(builders): cover overlay composition edge cases`

Example with body:

```text
fix(templates): align common-path packet defaults

- update shared packet template defaults for common-path planning
- keep builder-generated output in sync with the template change
- add regression coverage for the packet-workflow builder path
```
