---
name: packet-workflow-skill-builder
description: Thin entrypoint for the foundry packet-workflow builder. Use when Codex should invoke the authoritative root builder, contracts, templates, and defaults in this repository.
---

# Packet Workflow Skill Builder

Thin entry wiring for the foundry's packet-workflow builder.

This subtree is intentionally minimal:
- keep only `SKILL.md` and `agents/openai.yaml` here
- keep authoritative builder logic and tests in `../../../builders/packet-workflow/`
- keep authoritative contracts, templates, and default semantics in `../../../core/`
- do not reintroduce local copies of contracts, templates, scripts, or tests under this skill subtree

Use this skill only for repo packet workflows that follow `collect -> optional lint -> build packets -> optional validate -> optional apply`.

## Workflow

1. Ground the target workflow before scaffolding.
- Inspect the target repo artifacts and existing workflow entrypoints.
- Decide whether the new skill is `audit-only`, `audit-and-apply`, or `plan-validate-apply`.
- Read `../../../core/contracts/packet-workflow/pattern-catalog.md` only when you need help mapping the workflow to the packet pattern.

2. Draft a builder spec before generating files.
- Use `../../../builders/packet-workflow/builder-contract.md` to lock the `builder-spec.json` fields.
- Keep the workflow narrow: choose only the packets, scripts, and stop conditions the target workflow actually needs.
- Add `repo_profile` only for repo-specific path bindings, review-doc lists, and lint toggles.
- Keep repo profiles declarative and data-only: paths, globs, doc lists, booleans, defaults, and notes only.
- Choose `orchestrator_profile=standard` by default and use `packet-heavy-orchestrator` only when the workflow needs the packet-heavy common path from `../../../core/contracts/packet-workflow/common-path-contract.md`.

3. Generate the scaffold deterministically.
- Run `python ../../../builders/packet-workflow/scripts/init_packet_skill.py --spec <builder-spec.json> --output-dir <foundry-root>`.
- The generator consumes templates from `../../../core/templates/packet-workflow/` and defaults from `../../../core/defaults/packet-workflow/`.
- The generator writes the authoritative retained kernel to `../../../builders/packet-workflow/retained-skills/<skill-name>/`.
- The generator writes the thin discovery wrapper to `../../../.agents/skills/<skill-name>/`.
- Generated skills should treat `../../../.codex/tmp/` as the only repo-local home for temporary, helper, scratch, and ad hoc operator-input files that are not meant for source control.
- Generated skills should place runtime artifacts under the fixed gitignored repo-local root `../../../.codex/tmp/packet-workflow/<skill-name>/<run-id>/`.
- Generated skills should default evaluation logging to `~/.codex/tmp/evaluation_logs/<skill-name>/<run-id>.json` and use the fixed gitignored `.codex/tmp/` fallback only when sandbox rules require repo-local writes.

4. Validate the generated skill immediately.
- Run `python <codex-home>/skills/.system/skill-creator/scripts/quick_validate.py ../../../.agents/skills/<skill-name>`.
- Run `python -m py_compile ../../../builders/packet-workflow/retained-skills/<skill-name>/scripts/*.py` for every generated retained script.

## Guardrails

- Keep mutation, final synthesis, and broad code changes local in generated skills.
- Keep final adjudication local even when mini workers propose candidate classifications.
- Keep repo profiles data-only end to end; executable behavior stays in scripts and core contracts.
- Treat `worker_selection_guidance` as explanatory metadata only; `packet_worker_map` is the routing authority when present.
- Prefer foundry baseline behavior first, then optional foundry overlay, then project-local profile overrides outside this repo.
- Do not place authoritative builder specs, profiles, references, scripts, tests, or migration worksheets back under `.agents/skills/`.

## Output

- Tell the user which archetype and packet set you chose.
- Tell the user which generated scripts are placeholders versus ready-to-fill skeletons.
- Tell the user which defaults came from foundry core versus the repo profile scaffold.
