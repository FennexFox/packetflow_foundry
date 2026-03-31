# Packet Workflow Builder

This builder scaffolds packet-driven repo workflow skills.

Authoritative ownership:
- shared contracts live under `../../core/contracts/packet-workflow/`
- shared templates live under `../../core/templates/packet-workflow/`
- shared default semantics live under `../../core/defaults/packet-workflow/`
- this builder consumes those assets and is not their authoritative owner

Use this directory for:
- `builder-contract.md`
- builder-specific evaluation schema
- scaffold generation scripts
- builder tests
- authoritative retained skill kernels under `retained-skills/`
- generated collectors should prefer `.codex/project/profiles/<skill-name>/profile.json`, then `.codex/project/profiles/default/profile.json`, before falling back to the retained skill-local profile scaffold

Do not define contract semantics here first.
- If validator/apply rules, stop taxonomy, common-path behavior, worker-family semantics, or profile boundaries change, update `core/` first.
- Then update this builder so generation output and tests match the new core semantics.

Primary entrypoint:
- `scripts/init_packet_skill.py`
  - generates an authoritative retained kernel under `retained-skills/<skill-name>/`
  - generates a thin discovery wrapper under `../../.agents/skills/<skill-name>/`

Generated operator docs:
- retained `SKILL.md` files are the operator-facing execution contract for bundled helper scripts
- generated script invocations must use `<python-bin> -B <skill-dir>/scripts/...`
- generated docs must not prescribe launcher-specific shims such as bare `python` or `py`

Companion references:
- `builder-contract.md`
- `builder-evaluation-contract.md`
- `../../core/contracts/packet-workflow/pattern-catalog.md`

Supported retained pattern:
- weekly-update-like retained skills stay in this builder family
- use `decision_ready_packets=true`,
  `worker_return_contract=classification-oriented`, and
  `worker_output_shape=hierarchical`
- keep repo-specific weekly-update conventions in
  `repo_profile.extra.weekly_update`

Guarded invalid combinations:
- explicit `candidate_field_bundles` with `worker_return_contract=generic`
- `classification-oriented` without `decision_ready_packets=true`
- explicit `worker_footer_fields` without decision-ready hierarchical output
