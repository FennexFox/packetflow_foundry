# Retained Skill Taxonomy And Invariant Ownership

This document is the checked-in migration map for retained packet-workflow
skills. It records the current workflow classes, the first invariant ownership
matrix, and a migration priority table before shared-helper extraction starts.

## Current Inventory

| Retained skill | Primary workflow class | Current shape | Notes |
| --- | --- | --- | --- |
| `draft-release-copy` | generic packet mutation | `audit-and-apply`, `generic`, `flat` | builder-generated retained scaffold |
| `gh-address-review-threads` | two-phase GitHub review lifecycle | `audit-and-apply`, `generic`, `flat` | hand-specialized packet workflow with `ack` and `complete` phases |
| `gh-create-pr` | packet-heavy drafting and create | `plan-validate-apply`, `generic`, `flat`, `packet-heavy-orchestrator` | packet-heavy common-path drafting |
| `gh-fix-pr-writeup` | generic packet mutation | `audit-and-apply`, `generic`, `flat` | builder-generated retained scaffold |
| `git-split-and-commit` | decision-ready hierarchical adjudication | `plan-validate-apply`, `classification-oriented`, `hierarchical` | builder-generated retained scaffold |
| `public-docs-sync` | generic packet mutation | `audit-and-apply`, `generic`, `flat` | builder-generated retained scaffold |
| `reword-head-commit` | express direct-driver utility | no packet build | intentionally outside the packet builder family |
| `reword-recent-commits` | generic packet planning | `plan-validate-apply`, `generic`, `flat` | builder-generated retained scaffold |
| `weekly-update` | decision-ready hierarchical adjudication | `plan-validate-apply`, `classification-oriented`, `hierarchical` | hand-specialized retained exemplar |

## Workflow Classes

- `generic packet mutation`
  - deterministic collect/build plus optional validate/apply
  - flat worker outputs and local final synthesis
- `decision-ready hierarchical adjudication`
  - packet-first local adjudication with `candidates[]` plus `footer`
  - domain-specific candidate semantics stay skill-local
- `packet-heavy drafting and create`
  - common-path local drafting on `global + synthesis + <=1 focused packet`
  - evaluation-side packet metrics stay out of runtime routing
- `two-phase GitHub review lifecycle`
  - collect/build happens twice around push state
  - `ack` and `complete` semantics are domain-local and should not be flattened
    into the generic builder
- `express direct-driver utility`
  - no packet generation
  - still retained, but not a signal that all retained skills should share one
    template or one helper surface

## Invariant Ownership Matrix

| Invariant name | Owner layer | Classification | Enforcement point | Fatal vs record-only | Expected test coverage |
| --- | --- | --- | --- | --- | --- |
| Thin wrapper subtree stays limited to `SKILL.md` plus `agents/openai.yaml` | builder generator + builder tests | builder-time contract | generated output layout, wrapper-thinness tests | fatal | builder contract tests over generated wrappers and repo wrappers |
| Retained `SKILL.md` keeps only the minimum operator-facing contract by default | core doc contract + builder template | builder-time contract | `retained-skill-doc-contract.md`, `skill_md.tmpl`, generated-doc tests | fatal for new scaffolds | generated retained `SKILL.md` section-shape tests |
| Operators must resolve `<python-bin>` and `<skill-dir>` before helper execution | retained skill runtime contract | retained-skill-local runtime rule | retained `SKILL.md`, smoke paths, direct driver entrypoints | fatal | doc contract assertions plus smoke or direct-driver tests |
| Repo profiles stay data-only and never carry executable hooks or prompt behavior | core profile boundary + builder normalization | builder-time contract | `profile-boundary-contract.md`, builder spec/profile normalization, collector loading | fatal | builder validation tests and profile-resolution tests |
| Shared review-mode, authority-order, and stop-taxonomy meaning come from core contracts and defaults | core contracts/defaults | shared runtime helper | packet builders, validators, generated metadata | fatal | core-aware build/validate tests in generated skills |
| Apply consumes validator-normalized output only | core validator/apply contract | shared runtime helper | domain validators and apply scripts | fatal | validate/apply contract tests and smoke coverage |
| `packet_worker_map` owns concrete routing when configured; prose does not | core worker-family contract + builder | shared runtime helper | builder spec validation, generated packet metadata, packet-build tests | fatal | builder tests for routing metadata and dedupe behavior |
| Hierarchical `classification-oriented` packet shape is shared, but only for skills that opt in | core pattern + builder guards | shared runtime helper | builder spec validation, packet builders, domain contracts | fatal | builder guard tests and hierarchical packet contract tests |
| Domain proposal enums, section order, inclusion rules, and apply gates stay inside each retained skill | domain contract + domain scripts | retained-skill-local runtime rule | per-skill references, validators, apply scripts | fatal | skill-local contract, validate, apply, and smoke tests |
| GitHub auth and remote snapshot freshness gates stay in GitHub skills, not in the generic builder | domain collectors/validators | retained-skill-local runtime rule | `collect_*` and `validate_*` scripts for GitHub workflows | fatal | GitHub skill collect/validate tests and dry-run smoke coverage |
| Evaluation logs, packet metrics, and similar observability artifacts must not become runtime routing authority | evaluation contracts + packet builders | evaluation-only / observability-only | eval-log writers, build-result sidecars, packet metrics | record-only when absent; fatal if promoted into runtime authority | build-result/eval-log tests and packet-heavy metrics tests |
| Migration worksheets and architecture notes are maintainer guidance, not runtime authority | retained references/docs | operator guidance only | docs review and migration planning | record-only | no runtime assertions; reference-link sanity only |

## Migration Priority

| Priority | Retained skills | Why this bucket moves first | Migration target |
| --- | --- | --- | --- |
| `P0` | `weekly-update`, `gh-address-review-threads`, `gh-create-pr` | these three define the highest-variance retained shapes already in active use: hierarchical adjudication, two-phase GitHub lifecycle, and packet-heavy common-path drafting | move only the operator entry contract into `SKILL.md`; keep packet schemas, worker field lists, evaluation detail, and rationale in references |
| `P1` | `draft-release-copy`, `gh-fix-pr-writeup`, `git-split-and-commit`, `public-docs-sync`, `reword-recent-commits` | these are closest to the builder family and can usually converge by applying the agreed boundary without inventing new retained semantics | trim repeated builder-wide prose and keep only domain-local entry, stop, and output rules |
| `P2` | `reword-head-commit` | it is intentionally retained but outside the packet builder family, so it should not distort the generic packet template before the packet family converges | keep the express path separate and only align the minimum operator contract headings where that helps readability |

## Extraction Guard

Do not extract a shared helper just because multiple skills mention similar
language. Extract only when the invariant is classified above as a shared
runtime helper or builder-time contract. Leave retained-skill-local runtime
rules inside the owning skill until a later change proves the behavior is truly
shared.
