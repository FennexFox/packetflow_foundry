# Public Docs Sync Core Contract

This file captures the reusable packet-workflow core for the generated `public-docs-sync` scaffold.
Keep repo-specific paths, review-doc lists, and lint toggles in `profiles/default/profile.json`.
Repo profiles are data-only inputs. Do not place executable hooks, prompt text, or worker-routing behavior in them.

## Core Metadata

- `workflow_family`: `repo-audit`
- `archetype`: `audit-and-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `false`
- `worker_return_contract`: `generic`
- `worker_output_shape`: `flat`

## Shared Runtime Surface

- Required packet outputs:
- `orchestrator.json`
- `global_packet.json`
- `claims_packet.json`
- `reporting_packet.json`
- `workflow_packet.json`
- `forms_batch_packet.json`
- No additional orchestrator-profile-specific runtime packet is required.

Review mode overrides inherited by default:
- diff churn exceeds a configured threshold
- core runtime, config, or process files span multiple groups
- generated files are present but are not the majority of the change

Authority order:
- tracked repo materials
- structured workflow packets
- optional local helper

Stop conditions:
- low confidence
- stale snapshot or stale context
- ambiguous packet or ownership match

## Generic Worker Contract

## Generic Adjudication Structure

- This scaffold uses the `generic` worker return contract.
- XHigh reread policy: Do not reopen raw evidence by default after packet generation. Only reopen raw evidence when reread control points to an allowed reason such as conflicting signals, missing required evidence, schema mismatch, or insufficient excerpt quality.
- Final plan confidence is recomputed locally during synthesis. Do not copy worker confidence through unchanged.
- Generic flat mode does not require hierarchical `candidates[]` plus `footer` worker output.

## Worker Families

- The builder keeps worker-family structure generic and reusable across packet-driven workflows.
- Preferred worker families for this scaffold:
- `context_findings`: mapping, packet-scoped code analysis, touched-surface, and packet-membership findings
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
- `verifiers`: narrow claim or version-sensitive verification
  - `docs_verifier`

- Surfaced optional worker pool for generated docs stays deduped even when a worker belongs to multiple families:
- `repo_mapper`
- `packet_explorer`
- `docs_verifier`

- Packet routing hook:
- `packet_worker_map` is the routing authority when configured.
- The same agent type may appear on multiple packets when those assignments are intentional.
- `claims_packet`
  - `docs_verifier`
- `reporting_packet`
  - `evidence_summarizer`
- `workflow_packet`
  - `packet_explorer`
- `forms_batch_packet`
  - `docs_verifier`

- `worker_selection_guidance` is explanatory only and does not override `packet_worker_map`.
- Guidance notes:
  - Use `repo_mapper` when packet membership, execution path, touched surfaces, or authority mapping is unclear.
  - Use `packet_explorer` when one focused packet needs narrow code, behavior, or workflow analysis grounded by only the explicitly referenced file slices.
  - Use `docs_verifier` only when a disputed claim, version-sensitive assumption, or policy interpretation needs exact verification.
  - Use `evidence_summarizer` for long narrative evidence that should be condensed into decision-ready candidate records.
  - Use `large_diff_auditor` for large diffs, high-risk hotspots, regressions, invariants, and missing tests.
  - Use `log_triager` for logs, CI failures, runtime incidents, and earliest-useful-signal triage.
  - Treat `worker_selection_guidance` as explanatory only. `packet_worker_map` is the concrete routing authority when configured.

## Repo Profile Boundary

- Default generated profile: `profiles/default/profile.json`
- Summary: Neutral reusable profile scaffold for public-doc drift auditing. Add audited doc inventory, packet ownership, and marker metadata in project-local profiles when vendored.
- Default bindings:
- `primary_readme_path`: `README.md`
- `settings_source_path`: `null`
- `publish_config_path`: `null`
- Default packet defaults:
- review docs:
  - `claims_packet`
    - `README.md`
  - `reporting_packet`
    - `LOG_REPORTING.md`
    - `PERF_REPORTING.md`
    - `.github/software-evidence-schema.md`
    - `.github/software-investigation-workflow.md`
  - `workflow_packet`
    - `CONTRIBUTING.md`
    - `MAINTAINING.md`
    - `.github/pull_request_template.md`
    - `.github/workflows/release.yml`
  - `forms_batch_packet`
    - `.github/ISSUE_TEMPLATE/release_checklist.yml`
    - `.github/ISSUE_TEMPLATE/bug_report.yml`
    - `.github/ISSUE_TEMPLATE/feature_request.yml`
    - `.github/ISSUE_TEMPLATE/investigation.yml`
- source path globs:
  - `claims_packet`
    - `README.md`
    - `**/PublishConfiguration.xml`
    - `**/Setting.cs`
  - `reporting_packet`
    - `LOG_REPORTING.md`
    - `PERF_REPORTING.md`
    - `.github/software-*.md`
  - `workflow_packet`
    - `CONTRIBUTING.md`
    - `MAINTAINING.md`
    - `.github/pull_request_template.md`
    - `.github/workflows/*.yml`
  - `forms_batch_packet`
    - `.github/ISSUE_TEMPLATE/*.yml`
- Default lint rules:
- `require_readme_settings_table`: true
- `missing_review_docs_are_errors`: false

## Runtime vs Evaluation Metadata

- Keep runtime routing, authority, stop conditions, and adjudication support in `orchestrator.json` and `global_packet.json`.
- Keep packet sizing, byte proxies, and delegation-efficiency metrics in evaluation logs or `packet_metrics.json`, not in the core runtime packets.
- Keep repo-specific file layout and doc ownership in the repo profile instead of hardcoding them into this core contract.
- Keep the repo profile declarative. Scripts may consume its data, but the profile itself should not define executable behavior.

## Notes`r`n`r`n- Optional local helpers remain non-authoritative even when collected.`r`n- Final plan confidence is recomputed locally even when worker confidence signals are present.`r`n- The retained default scaffold keeps repo-specific bindings null and should be specialized by a project-local override when runtime-source coupling matters.





