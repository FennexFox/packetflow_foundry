---
name: gh-fix-pr-writeup
description: Verify and repair a GitHub pull request title and body when the user gives a PR number or asks to audit, rewrite, or fix PR text. Use when Codex must compare a PR's current writeup against repository PR instructions/templates and the actual code changes, then update it with gh CLI if the title/body are missing, truncated, generic, misleading, or unsupported by the diff.
---

# PR Writeup Repair

Use this skill to repair one PR title/body with a guarded `collect -> lint -> build -> validate -> apply` workflow.

## Use When

- the user names a PR or asks to audit, rewrite, or fix PR text
- final title/body drafting, validator decisions, and GitHub mutation stay local
- mini workers are used only for narrow packet analysis or an optional QA cross-check

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/gh-fix-pr-writeup/<run-id>/`
- `<packet-dir>`: `<runtime-root>/packets`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/gh-fix-pr-writeup/<run-id>.json`

## Entry

1. Run `gh auth status`; stop if authentication is missing.
2. Collect context with `<python-bin> -B <skill-dir>/scripts/collect_pr_context.py <pr-number> --repo-root <repo-root> --output <context-json>`.
3. Run lint and packet build with `lint_pr_writeup.py` and `build_pr_review_packets.py`.
4. Initialize the evaluation log, then merge the build result.
5. Read `orchestrator.json` first, then `rules_packet.json`, then `synthesis_packet.json`, then at most one focused packet.
6. Draft the final title/body locally, validate with `validate_pr_writeup_edit.py [--qa-result <qa-json>]`, and run `apply_pr_writeup.py` only from validator output. Candidate markdown inputs may be UTF-8 with or without BOM; do not add manual BOM-stripping side steps.
7. Record validation/apply phases and finalize the evaluation log after the last result.

## Continue Only If

- `rules_packet.json` stays the hard-rule authority and final drafting stays local
- `packet_worker_map` is the routing authority for delegated packet analysis
- `packet_sizing.json`, `build-result.json` `spawn_plan_preview`, baseline/adjustment metadata, and delegation fallback metadata stay out of runtime packets
- raw reread is exceptional and limited to the allowed reason set
- validation re-checks GitHub auth, the live PR snapshot, changed files, and QA gating before any mutation
- apply consumes validator-normalized output only

## Stop When

- `gh` auth is missing
- the live PR snapshot or changed-file fingerprint drifted after collection
- the candidate title/body is invalid or claims more than the diff supports
- QA clear is required but missing or rejected
- packet insufficiency, routing ambiguity, or diff support is too weak to make a safe local decision

## Final Response

- say whether the PR already matched the rules or what changed
- include the final PR URL
- mention the validation commands that actually ran
- if blocked, name the blocker precisely

## References

- `references/pr-writeup-contract.md`
- `references/delegation-playbook.md`
- `references/gh-fix-pr-writeup-evaluation-contract.md`
- `references/core-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_gh_fix_pr_writeup.py --repo-root <repo-root>`
