# Git Split And Commit Core Contract

This file captures the reusable packet-workflow core for the generated `git-split-and-commit` scaffold.
Keep repo-specific paths, review-doc lists, and lint toggles in `profiles/default/profile.json`.
Repo profiles are data-only inputs. Do not place executable hooks, prompt text, or worker-routing behavior in them.

## Core Metadata

- `workflow_family`: `git-history`
- `archetype`: `plan-validate-apply`
- `orchestrator_profile`: `standard`
- `decision_ready_packets`: `true`
- `worker_return_contract`: `classification-oriented`
- `worker_output_shape`: `hierarchical`

## Shared Runtime Surface

- Required packet outputs:
- `orchestrator.json`
- `global_packet.json`
- `rules.json`
- `worktree.json`
- `candidate-batch.json`
- `split-file.json`
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

- This scaffold uses the `classification-oriented` worker return contract.
- XHigh reread policy: Do not reopen raw evidence by default after packet generation. Only reopen raw evidence when reread control points to an allowed reason such as conflicting signals, missing required evidence, schema mismatch, or insufficient excerpt quality.
- Final plan confidence is recomputed locally during synthesis. Do not copy worker confidence through unchanged.
- Worker output shape: `hierarchical`
- Proposal classifications are worker proposal only. The main agent may override them during local adjudication.
- Hierarchical worker output uses fixed top-level keys:
  - `candidates[]`
  - `footer`
- Candidate field bundles:
- `fact_and_evidence`
  - required: yes
  - Candidate-level factual summary and supporting references.
  - fields:
    - candidate-level factual summary (`fact_summary`)
    - supporting references (`supporting_references`)
- `proposal_assessment`
  - required: yes
  - Worker proposal, rationale, ambiguity, and confidence signals.
  - fields:
    - worker proposal classification (`proposal_classification`)
    - classification rationale for the worker proposal (`classification_rationale`)
    - open ambiguity affecting adjudication (`ambiguity`)
    - worker confidence for the candidate (`confidence`)
- `reread_control`
  - required: yes
  - Exception-only raw reread control.
  - fields:
    - allowed reread reason or null (`reread_control`)
- Worker footer fields:
- `packet_ids`: packets or packet slices the worker actually used
- `candidate_ids`: candidate ids in the same stable order as `candidates[]`
- `primary_outcome`: worker-level batch summary only
- `overall_confidence`: worker batch confidence only; final plan confidence is recomputed locally
- `coverage_gaps`: unread or insufficiently verified scope
- `overall_risk`: remaining worker batch risk
- Allowed reread reasons:
- `conflicting_signals`
- `missing_required_evidence`
- `schema_mismatch`
- `insufficient_excerpt_quality`

## Worker Families

- The builder keeps worker-family structure generic and reusable across packet-driven workflows.
- Preferred worker families for this scaffold:
- `context_findings`: mapping, packet-scoped code analysis, touched-surface, and packet-membership findings
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
- `candidate_producers`: decision-ready candidate records for local adjudication-heavy workflows
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `verifiers`: narrow claim or version-sensitive verification
  - `docs_verifier`

- Surfaced optional worker pool for generated docs stays deduped even when a worker belongs to multiple families:
- `repo_mapper`
- `packet_explorer`
- `docs_verifier`
- `evidence_summarizer`
- `large_diff_auditor`
- `log_triager`

- Packet routing hook:
- `packet_worker_map` is the routing authority when configured.
- The same agent type may appear on multiple packets when those assignments are intentional.
- `rules`
  - `docs_verifier`
- `worktree`
  - `repo_mapper`
- `candidate-batch`
  - `evidence_summarizer`
- `split-file`
  - `large_diff_auditor`

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
- Summary: Default reusable profile scaffold for worktree commit planning. Replace with project-local commit-guidance docs, ownership hints, and repo-specific path globs when vendored.
- Default bindings:
- `primary_readme_path`: `README.md`
- `settings_source_path`: `null`
- `publish_config_path`: `null`
- Default packet defaults:
- review docs:
  - `rules`
    - `CONTRIBUTING.md`
    - `README.md`
  - `worktree`
    - `README.md`
  - `candidate-batch`
    - `README.md`
    - `CONTRIBUTING.md`
  - `split-file`
    - `README.md`
    - `CONTRIBUTING.md`
- source path globs:
  - `rules`
    - `.github/**`
    - `*.md`
  - `worktree`
    - `**/*`
  - `candidate-batch`
    - `**/*`
  - `split-file`
    - `**/*`
- Default lint rules:
- `require_readme_settings_table`: false
- `missing_review_docs_are_errors`: false

## Runtime vs Evaluation Metadata

- Keep runtime routing, authority, stop conditions, and adjudication support in `orchestrator.json` and `global_packet.json`.
- Keep packet sizing, byte proxies, and delegation-efficiency metrics in evaluation logs or `packet_metrics.json`, not in the core runtime packets.
- Keep any repo-local temporary, helper, scratch, or ad hoc operator-input file under `.codex/tmp/`, not at repo root or in tracked source directories.
- Keep repo-specific file layout and doc ownership in the repo profile instead of hardcoding them into this core contract.
- Keep the repo profile declarative. Scripts may consume its data, but the profile itself should not define executable behavior.

## Notes

- Optional local helpers remain non-authoritative even when collected.
- Final plan confidence is recomputed locally even when `footer.overall_confidence` is present.
