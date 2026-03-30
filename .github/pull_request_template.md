<!--
Before filling this template, read:
- .github/instructions/pull-request.instructions.md

PR title format:
<type>(<scope>): <summary>

Examples:
- fix(builders): keep generated defaults aligned with core
- docs(contracts): clarify profile boundary contract

Automation guardrails:
- Treat the instruction file above as the canonical source for generated
  PR text.
- Replace every placeholder bullet with concrete details from the final
  diff, or remove the bullet if it does not apply.
- Do not fill this template from memory or the latest commit summary
  when the instruction file above applies.
-->

## What changed
- 
- 

## Why
- 
- Refs: #

## How
- 
- Note any important authority-order, routing, validation, or template
  constraints.

## Testing
- Validation / tests:
  - 
- Manual review:
  - 
- If not tested, state why.

## Compatibility / Adoption
- Consumer / vendor impact:
  - [ ] None
  - [ ] Requires regenerating builder output
  - [ ] Requires updating project-local profiles or agents
  - [ ] Requires a migration note for vendored consumers
- Details:
  - 

## Risk / Rollback
- Risk areas:
  - 
- Rollback / mitigation:
  - 

## Reviewer Checklist
- [ ] Linked issue, design note, or release item when applicable
- [ ] Docs or templates updated if shared behavior changed
- [ ] Builder/tests updated with core contract/template/default changes
- [ ] Consumer impact called out when applicable
- [ ] Validation steps are specific enough to reproduce
- [ ] Risk and rollback are concrete when behavior could regress

## PR Classification (optional)
- [ ] Feature
- [ ] Bugfix
- [ ] Refactor
- [ ] Docs
- [ ] Chore/Maintenance
- [ ] Build/CI
- [ ] Test

Justification:
