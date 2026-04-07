# Migration Worksheet: reword-head-commit

## Workflow Snapshot
- `workflow_family`: `git-history`
- Current runtime shape: express single-commit amend, shared validator/apply contract, no packet build phase
- Primary artifacts: `rules.json`, `context.json`, `validation.json`, `apply-result.json`, `eval-log.json`
- Current authoritative files:
  - references: `reword-head-commit-contract.md`, `amend-safety.md`
  - scripts: `reword_head_commit.py`, `smoke_reword_head_commit.py`
  - tests: driver/smoke coverage exists

## Repo-Specific Inputs Seen In Legacy Skill
- repo commit-guidance docs reused through the shared reword collector
- branch/upstream state used only for local amend and later force-push warning decisions

## Migration Classification
- `core`
  - shared reword validation semantics
  - explicit-rules gate
  - repo-local temp-file policy and evaluation-log envelope
- Skill-local
  - one-commit express amend path
  - direct `git commit --amend` apply behavior
  - force-push-likely reporting for the amended head

## Retained vs Consumer-Local Decision
- Data-only repo differences stay outside the skill and continue to come from shared rule discovery.
- Amend preconditions, apply behavior, and express-path boundaries remain reusable skill-local logic.
- Decision: `retained`

## Pilot Hardening Outcome
- Prose-only invariants moved into script or test enforcement:
  - express-path validation blocks derived/fallback rule sets with `explicit_rules_required`
  - amend applies only after the same runtime blockers as the shared reword validator are re-checked locally
- Runtime to eval-only moves:
  - no packet-routing worker recommendations are carried at runtime for this express path
  - validation/apply/evaluation artifacts stay repo-local under `.codex/tmp/`
- Retained `SKILL.md` reduction:
  - reduced to the minimum operator-facing contract while keeping the direct amend path and shared-validator dependency explicit
