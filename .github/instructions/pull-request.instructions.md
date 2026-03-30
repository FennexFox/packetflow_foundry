# Pull Request Instructions

This file is the canonical source for generated PR titles and
descriptions in this repository. Read it before drafting PR text.

When asked to generate a PR title or description, follow this structure.
Prefer filling the repository template at
`.github/pull_request_template.md`.

## PR Title
- Use Conventional Commit style:
  - `<type>(<scope>): <summary>`
- Choose `type` and `scope` using the same rules as commit messages.
- Summary 72 characters or fewer, imperative mood, no trailing period.
- The PR title is also the default subject for PR merge commits into
  long-running branches, so it must stand on its own in
  `git log --oneline`.
- Determine `type` from the full PR outcome, not the active file, latest
  commit, or noisiest part of the diff.
- Title the primary behavior or workflow change, not the biggest file or
  supporting test/doc churn.
- If shared behavior changed and tests/docs/config changed alongside it,
  title the behavior change.
- Use `docs` only when the meaningful change is limited to
  documentation.
- Use `test` only when the meaningful change is limited to tests or test
  infrastructure.
- If the PR adds a new reusable workflow, managed-agent capability,
  overlay, or builder path, prefer `feat` unless the change is clearly a
  correction to existing behavior.
- Prefer `contracts`, `defaults`, or `templates` over generic `core`
  when one core surface is primary.

## Title Selection Heuristics
- Start from the highest-impact non-doc behavior change in the PR, then
  treat docs/tests/config as supporting detail.
- For multi-commit PRs, ignore intermediate cleanup or follow-up commit
  messages and summarize the final merged state instead.
- Because PR merge commits usually reuse the PR title without a body,
  keep the title specific enough that the merge commit still reads well
  on its own.
- Avoid generic or misleading titles like `fix(docs): ...` when the PR
  also introduces or changes shared semantics, builder behavior, or
  shipped templates/defaults.

## PR Description Template
Use these sections in template order. Keep bullets concise, concrete,
and non-redundant.

The PR description is the canonical detailed summary for PR merges. Do
not rely on merge commit bodies for routine reviewer context.

## What changed
- 2-6 bullets covering the main functional or behavioral changes
- Start with the primary consumer-facing or reviewer-relevant change

## Why
- State the problem being solved or the reason for the change
- Link issues if known (e.g. `Refs: #123`)

## How
- Capture key implementation choices, constraints, and tradeoffs
- Mention important authority-order, routing, validation, or template
  assumptions when relevant

## Testing
- State what was tested: targeted tests, generated output validation,
  manual review, or none
- Include reviewer verification commands or steps when applicable

## Compatibility / Adoption
- Call out consumer or vendoring impact only when it exists
- Mention required regeneration, profile changes, migration notes, or
  rollout constraints when relevant

## Risk / Rollback
- Call out meaningful risk areas only
- Include rollback or mitigation when shipped behavior could regress

## Reviewer Checklist
- Keep the template checklist when filling the full repository template.
- Mark items only when the diff or provided context supports them.

## PR Classification (optional)
If asked to classify the PR, use one label:
- `Feature`, `Bugfix`, `Refactor`, `Docs`, `Chore/Maintenance`,
  `Build/CI`, `Test`

Provide a one to two sentence justification.

## Examples
- `feat(templates): add reusable packet review starter set`
- `fix(builders): keep generated defaults aligned with core`
- `docs(contracts): clarify foundry profile boundary`
