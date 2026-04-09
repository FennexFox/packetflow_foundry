---
name: gh-create-pr
description: Create a GitHub pull request from an already-pushed branch by collecting repo and PR-template context, drafting a repo-compliant title/body, validating duplicate-PR and stale-snapshot gates, and creating the PR with gh CLI only after the normalized create request passes validation. Use when Codex must open a new PR instead of rewriting an existing one.
---

# Guarded PR Creation

Use this skill to open a new GitHub pull request from a branch already pushed to `origin` with a guarded `collect -> lint -> build -> validate -> apply` workflow.

## Use When

- the branch is already on `origin` and the user wants a new PR
- final title/body drafting, duplicate-PR decisions, and PR creation stay local
- mini workers are used only for narrow packet analysis, not for the mutation step

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/gh-create-pr/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/gh-create-pr/<run-id>.json`

## Entry

1. Run `gh auth status`; stop if authentication is missing.
2. Collect context with `<python-bin> -B <skill-dir>/scripts/collect_pr_create_context.py --repo-root <repo-root> ... --output <context-json>`.
3. Run lint and packet build with `lint_pr_create.py` and `build_pr_create_packets.py`.
4. Initialize the evaluation log, then merge the build result.
5. Read `orchestrator.json` first, then `rules_packet.json`, then `synthesis_packet.json`, then at most one focused packet.
6. Draft the final title/body locally, validate with `validate_pr_create.py`, and run `apply_pr_create.py` only from validator output. Candidate markdown inputs may be UTF-8 with or without BOM; do not add manual BOM-stripping side steps.
7. Record validation/apply phases and finalize the evaluation log after the last result.

## Continue Only If

- `rules_packet.json` stays the hard-rule authority and final drafting stays local
- `packet_worker_map` is the routing authority for delegated packet analysis
- `packet_metrics.json`, worker recommendations, baseline/adjustment metadata, and delegation fallback metadata stay evaluation-only
- validation re-checks auth, base/head state, template selection, changed-file fingerprint, and same-head open PR state before mutation
- apply consumes `normalized_create_request` only

## Stop When

- `gh` auth is missing
- repo inference, base resolution, template selection, or remote head validation failed
- a same-head open PR already exists
- the candidate title/body is invalid or claims more than the evidence supports
- the validated snapshot drifted before create

## Final Response

- say whether the run stopped at lint, validation, or apply
- include the final PR URL when creation succeeds
- if blocked by an existing PR, include that PR URL and hand off to `gh-fix-pr-writeup`

## References

- `references/pr-create-contract.md`
- `references/delegation-playbook.md`
- `references/pr-create-evaluation-contract.md`
- `references/core-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_gh_create_pr.py --repo-root <repo-root>`
