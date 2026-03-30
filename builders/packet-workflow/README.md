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

Do not define contract semantics here first.
- If validator/apply rules, stop taxonomy, common-path behavior, worker-family semantics, or profile boundaries change, update `core/` first.
- Then update this builder so generation output and tests match the new core semantics.

Primary entrypoint:
- `scripts/init_packet_skill.py`

Companion references:
- `builder-contract.md`
- `builder-evaluation-contract.md`
- `../../core/contracts/packet-workflow/pattern-catalog.md`
