# Maintaining

`packetflow_foundry` maintainer workflow rules should stay small,
reusable, and explicit.
Avoid inventing ad hoc labels or repo-local shortcuts that are not
reflected in tracked docs and templates.

## Issue labels

Use labels to answer three separate questions:
- what kind of issue is this?
- which reusable foundry surface owns it?
- what triage or disposition state matters right now?

Prefer a small fixed taxonomy over one-off labels.

## Intake labels

These are the default labels applied by the issue templates.

- `bug`
  - confirmed or reproducible incorrect behavior in
    `packetflow_foundry`
  - default for `.github/ISSUE_TEMPLATE/bug_report.yml`
- `enhancement`
  - a new reusable capability or a meaningful improvement
  - default for `.github/ISSUE_TEMPLATE/feature_request.yml`
- `release`
  - release preparation, validation, and version-tracking work
  - default for `.github/ISSUE_TEMPLATE/release_checklist.yml`

Keep one intake label on an issue unless the issue is reclassified.

## Area labels

Apply one `area:` label when the primary owned surface is clear.
These labels should stay aligned with the `Area` dropdown in the bug and
feature issue templates.

- `area:agents`
  - default managed agents and agent-routing surfaces
- `area:builders`
  - builder logic, generators, and builder-side tests
- `area:contracts`
  - shared contracts and authoritative foundry semantics
- `area:defaults`
  - shared defaults and shipped baseline behavior
- `area:docs`
  - contributor-facing docs, templates, and instructions
- `area:profiles`
  - reusable overlay profiles and profile defaults
- `area:skills`
  - reusable skill entrypoints and skill-side workflow glue
- `area:templates`
  - shared templates and generated scaffolding
- `area:vendoring`
  - consumer vendoring, adoption, and upgrade path concerns

If an issue spans multiple surfaces, label the primary owner and capture
secondary surfaces in the issue body or comments instead of stacking
multiple `area:` labels.

## Triage and disposition labels

Use these only when they change how the issue should be handled:

- `question`
  - clarification or usage question about the foundry
- `duplicate`
  - already tracked elsewhere
- `invalid`
  - report does not describe a valid repo issue
- `wontfix`
  - acknowledged but not planned for work

These labels complement the intake label; they do not replace it unless
the issue is being closed as pure triage.

## Labeling rules

- Prefer issue templates over blank issues so the intake label and area
  context are captured up front.
- Add an `area:` label during triage when the owner is clear.
- Keep `release` issues focused on release gating, validation, and
  version tracking rather than using ad hoc milestone-style labels.
- Do not recreate removed generic labels such as `documentation`,
  `good first issue`, or `help wanted` unless repo policy changes and
  the docs and templates are updated in the same change.
- If the template taxonomy changes, update the live GitHub labels and
  the corresponding docs in the same change.
