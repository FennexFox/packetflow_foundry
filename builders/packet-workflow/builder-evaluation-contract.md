# Packet Workflow Skill Builder Evaluation Contract

Use the shared envelope in [`../../core/contracts/packet-workflow/evaluation-log-contract.md`](../../core/contracts/packet-workflow/evaluation-log-contract.md) and keep builder-only metrics under `skill_specific.data`.

Suggested builder-specific fields:

- `requested_archetype`
- `requested_orchestrator_profile`
- `requested_domain_slug`
- `generated_file_count`
- `includes_optional_local_helper`
- `template_validation_passed`

Guidance:

- Treat generated-file counts and chosen archetype as observed metrics.
- Mark `template_validation_passed` only after `quick_validate.py` and `py_compile` succeed on the generated sample.
- Keep domain semantics out of this schema. This skill evaluates scaffold generation quality, not the generated workflow's runtime behavior.
