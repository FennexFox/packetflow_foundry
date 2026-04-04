# Builder Contract

Use this file when drafting `builder-spec.json` for `scripts/init_packet_skill.py`.

Boundary note:
- the thin-entrypoint intent for `.agents/skills/` predates the retained-kernel split
- earlier drift happened because the original generator and tests still emitted bundled skills under `.agents/skills/`
- the current contract is enforced by generation output and tests: retained kernels live under `retained-skills/`, wrappers live under `.agents/skills/`

Authoritative ownership:
- shared contracts, templates, and default semantics live under [`../../core/`](../../core/)
- this builder consumes those assets and is not their authoritative owner
- behavior meaning changes should be defined in `core/` first, then reflected here

This builder separates:
- the generic adjudication contract shared by packet-driven workflows
- reusable worker-family routing hooks
- a default repo-profile scaffold for repo-specific path bindings, packet review docs, and lint toggles
- optional domain overlays that rename or specialize semantics without changing the shared structure

Repo profiles are intentionally data-only. Keep only declarative bindings, globs, doc lists, booleans, notes, and generated compatibility metadata there. Do not treat `profile.json` as a place for executable hooks, prompt fragments, or worker-routing behavior.

## Required Fields

- `builder_versioning`
  - Object copied from `version.json` when the skill is current.
  - Required keys:
    - `builder_family`
    - `builder_semver`
    - `compatibility_epoch`
    - `builder_spec_schema_version`
    - `repo_profile_schema_version`
  - Generation rejects missing or invalid version blocks.
  - Semver-only drift is allowed.
  - Epoch or schema mismatch requires manual migration instead of silent auto-bump.
- `skill_name`
  - Hyphen-case skill folder name and SKILL frontmatter name.
- `description`
  - Full SKILL description sentence that explains what the generated skill does and when to use it.
- `domain_slug`
  - Snake-case token used in script names such as `collect_<domain_slug>_context.py`.
- `workflow_family`
  - Short family label such as `github-review`, `release-copy`, `git-history`, or `repo-audit`.
- `archetype`
  - One of:
    - `audit-only`
    - `audit-and-apply`
    - `plan-validate-apply`
- `primary_goal`
  - One sentence used in the generated SKILL body and UI prompt.
- `trigger_phrases`
  - Array of concrete user-intent phrases the generated skill should respond to.

## Optional Fields

- `task_packet_names`
  - Array of focused packet basenames without `.json`.
  - Default: `["task_packet"]`
- `orchestrator_profile`
  - Enum:
    - `standard`
    - `packet-heavy-orchestrator`
  - Default: `standard`
  - `standard` keeps only the common reference-grade contract layer.
  - `packet-heavy-orchestrator` adds `synthesis_packet.json`, `packet_metrics.json`, `shared_local_packet`, and `common_path_contract`.
- `uses_batch_packets`
  - Boolean.
  - Default: `false`
- `needs_lint`
  - Boolean. Default depends on archetype.
- `needs_validate`
  - Boolean. Default depends on archetype.
- `needs_apply`
  - Boolean. Default depends on archetype.
  - `needs_apply=true` requires `needs_validate=true`.
- `optional_local_helper`
  - Object with:
    - `path`
    - `description`
  - Generated skills must treat this helper as optional and non-authoritative.
- `authority_order`
  - Array of strings describing which inputs outrank others.
- `stop_conditions`
  - Array of strings.
- `review_mode_overrides`
  - Array of strings.
- `decision_ready_packets`
  - Boolean.
  - Default: `false`
  - Enable when focused packets should be directly usable for local adjudication instead of hint-only evidence pointers.
- `worker_return_contract`
  - Enum:
    - `generic`
    - `classification-oriented`
  - Default:
    - `classification-oriented` when `decision_ready_packets=true`
    - otherwise `generic`
  - Guard:
    - `classification-oriented` requires `decision_ready_packets=true`
- `worker_output_shape`
  - Enum:
    - `flat`
    - `hierarchical`
  - Default:
    - `hierarchical` when `decision_ready_packets=true` or `worker_return_contract=classification-oriented`
    - otherwise `flat`
  - `hierarchical` requires `worker_return_contract=classification-oriented`.
- `xhigh_reread_policy`
  - String.
  - Default:
    - packet-first local adjudication with raw rereads allowed only for explicit exception reasons
- `candidate_field_bundles`
  - Ordered array of bundle objects for decision-ready candidate semantics.
  - Each bundle object supports:
    - `name`
    - `description`
    - `required`
    - `fields`
  - Guard:
    - explicit `candidate_field_bundles` require `worker_return_contract=classification-oriented`
- `worker_footer_fields`
  - Ordered array of footer field names for hierarchical worker output.
  - Guard:
    - explicit `worker_footer_fields` require `decision_ready_packets=true`
    - explicit `worker_footer_fields` require `worker_output_shape=hierarchical`
- `reread_reason_values`
  - Ordered array of allowed reread reasons.
- `required_candidate_fields`
  - Legacy shorthand.
  - Still accepted for backward compatibility.
  - When `candidate_field_bundles` is omitted, the builder normalizes this list into a single required bundle rather than rejecting older specs.
- `preferred_worker_families`
  - Optional worker-family registry for generated docs and packet metadata.
  - Supported keys:
    - `context_findings`
    - `candidate_producers`
    - `verifiers`
  - Default:
    - `context_findings`: `["repo_mapper", "packet_explorer", "docs_verifier"]`
    - `candidate_producers`: `["evidence_summarizer", "large_diff_auditor", "log_triager"]`
    - `verifiers`: `["docs_verifier"]`
  - Family-internal order is preserved.
  - Duplicate agent types inside one family list are invalid.
  - Cross-family overlap is allowed.
- `packet_worker_map`
  - Optional concrete routing map for generated `recommended_workers`.
  - Shape:
    - packet basename -> ordered agent type list
  - Allowed keys:
    - declared `task_packet_names`
    - `batch-packet-01` only when `uses_batch_packets=true`
  - Values must use only known worker agent types.
  - Duplicate agent types inside one packet list are invalid.
  - The same agent type may appear on multiple packet assignments.
- `domain_overlay`
  - Optional nested domain-semantics container.
  - Supported keys:
    - `proposal_enum_values`
    - `candidate_field_aliases`
    - `reference_only_candidate_values`
    - `output_inclusion_rules`
    - `bundle_overrides`
- `repo_profile`
  - Optional default repo-profile scaffold for generated skills.
  - Generated at `profiles/<name>/profile.json`.
  - Keep it data-only end to end.
  - `metadata.versioning` is generated automatically and is not authored through this field.
  - Supported keys:
    - `name`
    - `summary`
    - `repo_match`
      - `root_markers`
      - `remote_patterns`
    - `bindings`
      - `primary_readme_path`
      - `settings_source_path`
      - `publish_config_path`
    - `packet_defaults`
      - `review_docs`
      - `source_path_globs`
    - `lint_rules`
      - `require_readme_settings_table`
      - `missing_review_docs_are_errors`
    - `extra`
      - arbitrary data-only JSON for skill-specific profile fields that do not
        fit the baseline bindings/packet-defaults/lint-rules scaffold
      - values must remain declarative data only
      - do not use this for executable hooks, prompt fragments, routing
        authority, or validator/apply behavior
      - example:
        - keep repo-specific weekly-update conventions in
          `repo_profile.extra.weekly_update`
    - `notes`
  - Default intent:
    - keep repo-specific file layout and packet ownership out of the generic core
    - keep repo-specific configuration declarative so the generated scripts own executable behavior
    - let future repo ports add or replace profile folders without rewriting the core contract or templates

## Builder Versioning

Canonical current builder metadata lives in `version.json`.

Compatibility expectations:
- `compatibility_epoch` must match for generation to proceed
- `builder_spec_schema_version` must match for generation to proceed
- `repo_profile_schema_version` must match for generation to proceed
- `builder_semver` may trail current builder semver when the skill is still structurally compatible

Generated runtime metadata:
- `builder_versioning` is copied into generated `SPEC_METADATA`
- `profiles/<name>/profile.json` gets `metadata.versioning`
- runtime collectors should record builder compatibility and warn when the active skill or profile is not current

## Output Layout

`scripts/init_packet_skill.py --output-dir <repo-root>` generates two coordinated trees:
- authoritative retained kernel:
  - `builders/packet-workflow/retained-skills/<skill-name>/`
- thin discovery wrapper:
  - `.agents/skills/<skill-name>/`

Generated skills must also reserve `<repo-root>/.codex/tmp/` as the only repo-local scratch tree for temporary, helper, runtime-artifact, and ad hoc operator-input files that are not meant to be tracked:
- keep packet runtime artifacts under `.codex/tmp/packet-workflow/<skill-name>/`
- keep repo-local fallbacks such as evaluation logs or helper inputs under `.codex/tmp/`
- do not place repo-local temp files at the repo root or inside tracked source directories

Wrapper rules:
- wrapper subtree may contain only `SKILL.md` and `agents/openai.yaml`
- wrapper must point operators at the retained kernel
- wrapper must not carry `builder-spec.json`, profiles, references, scripts, tests, or migration worksheets

Generated operator-doc rules:
- generated retained `SKILL.md` files must define the execution contract in terms of `<python-bin>` and `<skill-dir>`
- generated helper invocations must use `<python-bin> -B <skill-dir>/scripts/...`
- generated docs must not prescribe launcher-specific shims such as bare `python` or `py`

Bump rules:
- bump `compatibility_epoch` when generated skills or profiles require manual migration
- do not bump the epoch for docs-only, tests-only, or additive backward-compatible changes
- use `versioning-policy.md` for the authoritative bump and migration-record rules

## Known Worker Agent Types

The authoritative allowlist lives in the builder generator, not in the global agents directory scan.

- Source of truth:
  - `KNOWN_WORKER_AGENT_TYPES` constant in `scripts/init_packet_skill.py`
- Current managed set:
  - `repo_mapper`
  - `packet_explorer`
  - `docs_verifier`
  - `evidence_summarizer`
  - `large_diff_auditor`
  - `log_triager`
- `packet_worker_map` validation uses this constant only.
- Managed-agent registry lookup order:
  - explicit `--managed-agents-dir` or function override
  - environment override via `CODEX_MANAGED_AGENTS_DIR`
  - environment-derived default via `CODEX_HOME/agents`
  - standard install default derived from the builder location
  - bundled `tests/fixtures/agents` fallback for portable tests
- The registry scan is a subset consistency check only.
- Required behavior:
  - every managed worker above must exist as a real TOML agent
  - unrelated extra global agents are allowed
  - missing managed worker agents are hard failure

## Generic Adjudication Contract

Use the generic adjudication contract when the local orchestrator must classify, rank, or gate work across structured packets without reopening most raw artifacts.

Recommended pairing:
- `decision_ready_packets=true`
- `worker_return_contract=classification-oriented`
- `worker_output_shape=hierarchical`

Retained weekly-update-like pattern:
- use this same pairing for retained hierarchical adjudication workflows
- keep repo-specific review markers, release-title conventions, and similar
  data-only overrides in `repo_profile.extra.weekly_update`
- do not create a new builder family when the workflow still fits this shape

Forbidden retained-shape combinations:
- `candidate_field_bundles` with `worker_return_contract=generic`
- `worker_footer_fields` without `decision_ready_packets=true`
- `worker_footer_fields` with `worker_output_shape=flat`
- `domain_overlay` with `worker_return_contract=generic`

Shared structure:
- `candidates[]`
  - fixed container for candidate-level worker output
  - candidate-level factual summaries stay inside candidates
- `footer`
  - fixed worker-level batch summary container
  - `footer.primary_outcome` is worker batch summary only
  - `footer.overall_confidence` is worker batch confidence only

Default generic candidate semantics:
- `fact_summary`
- `proposal_classification`
- `classification_rationale`
- `supporting_references`
- `ambiguity`
- `confidence`
- `reread_control`

Default generic footer semantics:
- `packet_ids`
- `candidate_ids`
- `primary_outcome`
- `overall_confidence`
- `coverage_gaps`
- `overall_risk`

Confidence layering:
- worker confidence stays worker-local
- final plan confidence is recomputed locally during synthesis
- generated skills should not copy worker/footer confidence through unchanged into the final plan

Reread control:
- raw rereads stay off by default after packet generation
- rereads are allowed only when candidate-level reread control points to an allowed reason

## Worker-Family Routing Contract

Use worker families to keep named specialist workers reusable without hardcoding one downstream skill contract into the builder.

Family intent:
- `context_findings`
  - mapping, packet-scoped code analysis, touched-surface, packet-membership, and authority findings
- `candidate_producers`
  - decision-ready candidate production for local adjudication-heavy workflows
- `verifiers`
  - narrow claim verification or version-sensitive checks

`optional_workers` derivation:
1. choose active family order
2. concatenate family lists in that order
3. apply first-occurrence stable dedupe
4. remove agent types already present in `recommended_workers`

Active family order:
- `generic`
  - `context_findings`
  - `verifiers`
- `classification-oriented`
  - `context_findings`
  - `candidate_producers`
  - `verifiers`

Implications:
- a worker may belong to multiple families
- surfaced `optional_workers` is still a deduped list
- when `packet_worker_map` is configured, generated delegation docs should surface the delegated-mode `optional_workers` view after subtracting explicitly mapped recommended worker types
- generated docs should describe both:
  - family membership
  - surfaced deduped optional worker list

`recommended_workers` derivation:
- concrete routing exists only when `packet_worker_map` is configured
- without `packet_worker_map`, generated `recommended_workers` stays empty
- `worker_selection_guidance` remains explanatory only
- `packet_worker_map` is the routing authority when present

Budget trim rules:
- trim by `packet_order`, not by family
- ignore `global_packet.json`
- if `uses_batch_packets=true`, `batch-packet-01` is considered before singleton packets
- within a packet, preserve the declared `packet_worker_map` order
- dedupe only exact `(agent_type, packet)` pairs
- the same agent type may still appear on multiple packets

## Domain Overlay Contract

Use `domain_overlay` only for domain semantics. Do not use it to change shared structural keys such as `candidates` or `footer`.

Overlay precedence:
1. Generic structural keys are fixed and never overridden by overlays.
2. Generic `candidate_field_bundles` establish the semantic slots required by the workflow.
3. Overlay `bundle_overrides` adjust bundle composition or requiredness.
4. Overlay `candidate_field_aliases` apply last, mapping resolved semantic slots to domain field names.
5. If no alias is provided for a resolved semantic slot, keep the generic slot name.

Interpretation rules:
- `candidate_field_aliases` rename semantics only. They do not remove required slots.
- `bundle_overrides` may narrow, expand, or regroup candidate semantics for the domain, but they must still resolve back to the shared generic structure.
- `proposal_enum_values` defines domain proposal states without hardcoding them into the base builder.
- `reference_only_candidate_values` marks proposal values that are reference-only by default.
- `output_inclusion_rules` groups proposal values into:
  - standalone output items
  - reference-only support items
  - excluded-by-default items

## Archetype Defaults

- `audit-only`
  - `needs_lint=false`
  - `needs_validate=false`
  - `needs_apply=false`
- `audit-and-apply`
  - `needs_lint=true`
  - `needs_validate=true`
  - `needs_apply=true`
- `plan-validate-apply`
  - `needs_lint=false`
  - `needs_validate=true`
  - `needs_apply=true`

## Mutation Baseline

Generated mutating scaffolds should inherit these defaults:
- validator and apply stay separate
- apply accepts validator output, not raw plan input
- apply must consume validator-normalized output only
- `--dry-run` must use the same validator-normalized input path as real apply
- stale-context, apply-gate, and fingerprint checks belong in validator/apply before domain mutations are added

## Generated Files

Every generated retained kernel includes:
- `SKILL.md`
- `agents/openai.yaml`
- `references/core-contract.md`
- `references/delegation-playbook.md`
- `references/<domain>-contract.md`
- `references/evaluation-log-contract.md`
- `references/<domain>-evaluation-contract.md`
- `profiles/<profile-name>/profile.json`
- `scripts/collect_<domain_slug>_context.py`
- `scripts/build_<domain_slug>_packets.py`
- `scripts/write_evaluation_log.py`

Optional generated files:
- `scripts/lint_<domain_slug>.py`
- `scripts/validate_<domain_slug>.py`
- `scripts/apply_<domain_slug>.py`

Every generated wrapper includes:
- `SKILL.md`
- `agents/openai.yaml`

## Generated Packet Conventions

Every scaffold uses:
- `orchestrator.json`
- `global_packet.json`
- the focused packet files named by `task_packet_names`
- a generated repo-profile scaffold at `profiles/<profile-name>/profile.json`

If `uses_batch_packets=true`, the scaffold also reserves `batch-packet-01.json` for grouped work items.

If `orchestrator_profile=packet-heavy-orchestrator`, the scaffold also emits:
- runtime:
  - `synthesis_packet.json`
- evaluation/regression:
  - `packet_metrics.json`

Runtime contract metadata and evaluation/regression metadata stay separate:
- keep routing, authority, stop conditions, and common-path runtime signals in `orchestrator.json` / `global_packet.json`
- keep packet sizing, byte proxies, and token-efficiency estimates in `packet_metrics.json` and evaluation logs; only derived review-mode adjustments such as `delegation_savings_floor` may flow back into runtime metadata
- keep repo-specific path bindings and packet-review defaults in the repo profile instead of hardcoding them into the generic core contract

Generated `orchestrator.json` and `global_packet.json` keep:
- final review-mode provenance via `review_mode`, `review_mode_baseline`, and `review_mode_adjustments`
- worker return contract
- worker output shape
- decision-ready packet metadata
- candidate/footer/reread contract metadata
- preferred worker families
- packet worker map when configured
- worker selection guidance

When `orchestrator_profile=packet-heavy-orchestrator`, generated `orchestrator.json` also keeps:
- `shared_local_packet`
- `common_path_contract`
- no packet-size or token-efficiency counters

When `worker_output_shape=hierarchical`, generated focused packet stubs also reserve:
- `candidates`
- `footer`
- `candidate_template`
- `worker_footer_fields`
- `reread_reason_values`
- `domain_overlay`

## Notes

- The generated scripts are skeletons, not finished domain implementations.
- Older builder specs remain valid; the richer adjudication and worker-family fields are optional.
- The generator does not create shared runtime modules.
- The generator does not infer packet-to-agent routing from packet names alone.
- The generated core/profile split is structural. Domain-specific scripts still need to decide how strongly the repo profile should influence deterministic collection and lint logic.
