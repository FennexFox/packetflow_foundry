---
name: weekly-update
description: Top-level orchestration skill for reusable weekly updates. Synthesize recent PRs, rollouts, incidents, reviews, and blockers using packet-driven evidence collection and narrow read-only delegation, keep worker outputs proposal-grade, keep final classification and wording local, and update only a last-success marker after a reviewed plan clears apply gates.
---

# Weekly Update

Use this skill to produce a reusable weekly update with packet-driven evidence collection, optional narrow read-only delegation, and local final adjudication.

## Use When

- the user wants a weekly update grounded in repo state plus directly related GitHub evidence
- final classification, section placement, wording, and marker updates must stay local
- mini workers are used only for narrow packet analysis, not for the final writeup

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/weekly-update/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/weekly-update/<run-id>.json`

## Entry

1. Run `gh auth status`; stop if authentication is missing.
2. Collect, lint, and build with `<python-bin> -B <skill-dir>/scripts/collect_weekly_update_context.py`, `lint_weekly_update.py`, and `build_weekly_update_packets.py --result-output <build-result-json>`.
3. Initialize the evaluation log, merge the build result, then read `orchestrator.json`, `global_packet.json`, `mapping_packet.json`, and only the focused packet needed for the current decision.
4. Draft `weekly-update-plan.json` locally, validate it with `validate_weekly_update_plan.py`, and run `apply_weekly_update.py` only from the reviewed plan.
5. Finalize the evaluation log after validate/apply results are recorded.

## Continue Only If

- `packet_worker_map` remains the routing authority for delegated packets
- review-mode baselines, adjustments, worker recommendations, and token metrics stay in build/eval artifacts instead of widening runtime packets
- `artifact_only` candidates stay reference-only and do not surface as standalone weekly items
- the common path stays on `global_packet.json`, `mapping_packet.json`, and at most one focused packet unless an explicit reread reason is required
- apply reads only the reviewed plan fields `overall_confidence`, `stop_reasons`, and `allow_marker_update`

## Stop When

- `gh` auth is missing or GitHub evidence required for the reporting window cannot be collected
- structured context is stale or the selected analysis ref cannot support the needed reread
- unresolved raw-reread candidates, low confidence, or marker-update gates block the plan
- incident-versus-blocker classification remains ambiguous after local review

## Final Response

- state the exact reporting window
- say which packets and evidence categories drove the result and whether mini workers were used
- say whether the run stopped at planning, validation, or apply
- if blocked, name the blocker precisely

## References

- `references/weekly-update-contract.md`
- `references/architecture-note.md`
- `references/delegation-playbook.md`
- `references/weekly-update-evaluation-contract.md`
- `references/core-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_weekly_update.py --repo-root <repo-root>`
