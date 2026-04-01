# Weekly Update Core Contract

This file captures the reusable packet-workflow core for the retained `weekly-update` scaffold.
Keep repo-specific paths, review-doc lists, and weekly-update conventions in `profiles/default/profile.json`.
Repo profiles are data-only inputs. Do not place executable hooks, prompt text, worker-routing behavior, or validator/apply semantics in them.
Consumer repos should prefer `.codex/project/profiles/weekly-update/profile.json` over editing the retained default directly.

## Core Metadata

- `workflow_family`: `repo-audit`
- `archetype`: `plan-validate-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `true`
- `worker_return_contract`: `classification-oriented`
- `worker_output_shape`: `hierarchical`

## Shared Runtime Surface

- Required packet outputs:
- `orchestrator.json`
- `global_packet.json`
- `mapping_packet.json`
- `changes_packet.json`
- `incidents_packet.json`
- `risks_packet.json`

Review mode overrides inherited by default:
- reporting window includes more than 8 merged PRs or more than 15 relevant issues
- release, incident, and review surfaces are all active in the same window
- nested branch lineage or workflow-run failures materially expand the evidence graph

Authority order:
- published GitHub releases and linked release issues
- merged PR diffs and git history
- directly related review, issue, and workflow-run evidence
- structured workflow packets
- local last-success state as baseline only

Stop conditions:
- low confidence
- stale snapshot or stale structured context
- GitHub evidence is required but gh auth is invalid
- ambiguous incident versus blocker classification
- missing reporting window baseline when reuse is required

## Classification-Oriented Worker Contract

- This scaffold uses the `classification-oriented` worker return contract.
- XHigh reread policy: Do not reopen raw evidence by default after packet generation. Only reopen raw evidence when reread control points to an allowed reason such as conflicting signals, missing failure evidence, missing materiality evidence, schema mismatch, or insufficient excerpt quality.
- Final plan confidence is recomputed locally during synthesis. Do not copy worker confidence through unchanged.
- Hierarchical workers return top-level `candidates[]` plus `footer`.

Candidate field bundles:
- `identity`
  - `candidate_id`
  - `source_type`
  - `source_id`
  - `title`
- `proposal`
  - `summary`
  - `proposed_classification`
  - `classification_rationale`
- `evidence`
  - `materiality_evidence`
  - `concrete_failure_evidence`
  - `source_refs`
  - `excerpt_bundle`
- `adjudication`
  - `open_ambiguity`
  - `confidence`
  - `raw_reread_reason`
  - `packet_membership`
- `follow_up`
  - `risk`
  - `recommended_next_step`
  - `tests_or_checks`

Worker footer fields:
- `packet_ids`
- `candidate_ids`
- `primary_outcome`
- `overall_confidence`
- `coverage_gaps`
- `overall_risk`

Domain overlay:
- proposal enum values:
  - `actual_incident`
  - `blocker_or_risk`
  - `artifact_only`
  - `ignore`
- reference-only candidate values:
  - `artifact_only`
- output inclusion rules:
  - `standalone`
    - `actual_incident`
    - `blocker_or_risk`
  - `reference_only`
    - `artifact_only`
  - `excluded`
    - `ignore`

## Worker Families

- Preferred worker families for this scaffold:
- `context_findings`
  - `repo_mapper`
  - `docs_verifier`
- `candidate_producers`
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `verifiers`
  - `docs_verifier`

- Surfaced optional worker pool for docs stays deduped even when a worker belongs to multiple families:
- `docs_verifier`

- Packet routing hook:
- `packet_worker_map` is the routing authority when configured.
- `mapping_packet`
  - `repo_mapper`
- `changes_packet`
  - `large_diff_auditor`
- `incidents_packet`
  - `log_triager`
- `risks_packet`
  - `evidence_summarizer`

- `worker_selection_guidance` is explanatory only and does not override `packet_worker_map`.

## Repo Profile Boundary

- Default generated profile: `profiles/default/profile.json`
- Preferred project-local override path: `.codex/project/profiles/weekly-update/profile.json`
- Summary: Default reusable profile scaffold for weekly-update workflows. Replace review docs, path hints, and repo conventions in project-local profiles when vendored.
- Default bindings:
- `primary_readme_path`: `README.md`
- `settings_source_path`: `null`
- `publish_config_path`: `null`
- Default packet defaults:
- review docs:
  - `mapping_packet`
    - `README.md`
    - `CONTRIBUTING.md`
  - `changes_packet`
    - `README.md`
    - `CONTRIBUTING.md`
  - `incidents_packet`
    - `README.md`
    - `CONTRIBUTING.md`
  - `risks_packet`
    - `README.md`
    - `CONTRIBUTING.md`
- source path globs:
  - `mapping_packet`
    - `**/*`
  - `changes_packet`
    - `**/*`
  - `incidents_packet`
    - `**/*`
  - `risks_packet`
    - `**/*`
- Default lint rules:
- `require_readme_settings_table`: false
- `missing_review_docs_are_errors`: false
- Default repo-specific conventions stay in `repo_profile.extra.weekly_update`:
  - state namespace
  - review marker tokens
  - release issue title regex
  - priority marker regex

## Runtime vs Evaluation Metadata

- Keep runtime routing, authority, stop conditions, review mode, domain overlay, and adjudication support in `orchestrator.json` and `global_packet.json`.
- Keep packet sizing, byte proxies, and delegation-efficiency metrics in evaluation logs or `packet_metrics.json`, not in the core runtime packets.
- Keep any repo-local temporary, helper, scratch, or ad hoc operator-input file under `.codex/tmp/`, not at repo root or in tracked source directories.
- Keep repo-specific file layout and weekly-update conventions in the repo profile instead of hardcoding them into this core contract.
- Keep the repo profile declarative. Scripts may consume its data, but the profile itself should not define executable behavior.

## Notes

- Active profile metadata should appear in collected context plus `orchestrator.json`, `global_packet.json`, and build-result artifacts.
- Consumer repos should prefer the project-local `weekly-update` profile path above over editing the foundry-retained default.
