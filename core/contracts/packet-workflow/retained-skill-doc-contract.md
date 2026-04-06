# Retained Skill Doc Contract

This contract defines the minimum operator-facing surface for retained
`SKILL.md` files under `builders/packet-workflow/retained-skills/`.

Scope:
- authoritative retained kernels only
- not thin `.agents/skills/` wrappers
- not a replacement for domain contracts or script-level CLI help

Goal:
- keep invocation safe and obvious for operators
- keep generated retained docs consistent
- move packet schemas, field inventories, and validator/apply envelopes out of
  prose when they do not need to live in the operator entry contract

## Minimum Operator-Facing Contract

Every newly generated retained `SKILL.md` should tell an operator:
- when to use the skill
- how to enter the workflow
- what must be true before continuing
- what stops the workflow
- what the final response must include

Recommended section shape:
- `## Use When`
- `## Execution Roots`
- `## Entry`
- `## Continue Only If`
- `## Stop When`
- `## Final Response`
- optional `## References`

Section names may vary for hand-authored retained skills, but new builder output
should converge on this shape.

## Keep In Retained SKILL.md

Keep these items in the retained operator doc:
- the one-paragraph statement of purpose for when the skill should be used
- execution-root rules that operators must follow, including `<python-bin>` and
  `<skill-dir>`
- the first workflow entry commands needed to collect context, build packets,
  and continue safely
- the repo/profile/runtime assumptions that must be true before proceeding
- user-visible stop conditions
- final response requirements for the operator-facing answer
- short links to the domain contract, shared core contract, and other
  references that hold deeper detail

## Move Out Of Retained SKILL.md

Do not keep these as default generated prose in retained `SKILL.md`:
- long packet field inventories
- candidate/footer schema dumps
- full worker-family catalogs and routing tables
- evaluation-log field lists and observability-only metadata
- large script inventories whose filenames are not needed to enter the workflow
- architecture rationale and migration notes
- validator/apply normalization envelopes that belong in references or code

These details belong in `references/`, `scripts/`, tests, or builder contracts.

## Ownership Boundary

- retained `SKILL.md`
  - minimum operator-facing execution contract
  - domain-specific entry, stop, and final-response wording
- `references/`
  - packet schemas
  - domain contracts
  - worker-output semantics
  - evaluation contracts
  - architecture notes
- `scripts/`
  - CLI flags
  - deterministic collection/build/validate/apply behavior
  - normalization and mutation semantics
- `builder-contract.md`
  - scaffold fields, generated-file inventory, and shared builder-side defaults
- `.agents/skills/<skill>/`
  - thin discovery wrapper only

## Builder Alignment Rules

- builder templates should emit the minimum contract by default
- builder tests should verify the minimum retained section set for new
  scaffolds
- builder templates should not reintroduce `## Scripts` or `## Evaluation` as
  default bulk sections for newly generated retained skills
- existing retained skills may temporarily remain larger until migrated, but the
  migration target stays this contract
