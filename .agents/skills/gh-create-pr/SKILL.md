---
name: gh-create-pr
description: Create a GitHub pull request from an already-pushed branch by collecting repo and PR-template context, drafting a repo-compliant title/body, validating duplicate-PR and stale-snapshot gates, and creating the PR with gh CLI only after the normalized create request passes validation. Use when Codex must open a new PR instead of rewriting an existing one.
---

# Guarded PR Creation

Use this skill to open a new GitHub pull request from a branch that already exists on `origin`.

This skill keeps the mutation path narrow:
- keep final title/body drafting local
- keep repo profiles data-only
- keep duplicate-PR, template, and stale-snapshot gates local
- use packet-heavy local synthesis on `rules + synthesis + <=1 focused packet`
- never rely on `gh pr create --dry-run`; dry-run stays side-effect-free

## Workflow

1. Collect context first.
- Run `python scripts/collect_pr_create_context.py --repo-root <repo-root> [--repo <owner/name>] [--base <branch>] [--head <branch>] [--reviewer <login>] [--assignee <login>] [--label <name>] [--milestone <title>] [--draft] [--no-maintainer-edit] --output <context-json>`.
- Collector keeps raw repeated options as entered. Normalization happens later in the validator.
- Base resolution order is: `--base`, `branch.<current>.gh-merge-base`, remote default branch.

2. Build drafting packets.
- Run `python scripts/lint_pr_create.py --context <context-json> --output <lint-json>`.
- Run `python scripts/build_pr_create_packets.py --context <context-json> --lint <lint-json> --output-dir <packet-dir> [--result-output <build-result-json>]`.
- Read `orchestrator.json` first.
- Keep the common path on `rules_packet.json`, `synthesis_packet.json`, and at most one focused packet.

3. Draft locally.
- Use the selected template sections exactly.
- Treat issue refs, positive testing claims, rollout/restart/migration/compatibility claims, and `no behavior change` as gated claims, not prose flourishes.
- If the repo already has a same-head open PR, do not create another one. Hand off to `gh-fix-pr-writeup`.

4. Validate before mutation.
- Run `python scripts/validate_pr_create.py --context <context-json> --title "<title>" --body-file <body.md> --output <validation-json>`.
- Validator normalizes reviewers, assignees, labels, milestone, and maintainer-edit settings.
- Validator re-checks auth, head/base state, template selection, changed-files fingerprint, and same-head open PR state.
- Apply must consume `normalized_create_request` only.

5. Apply or dry-run.
- Run `python scripts/apply_pr_create.py --validation <validation-json> [--dry-run] [--result-output <apply-json>]`.
- `--dry-run` does not call `gh pr create`.
- Real apply re-checks the validated snapshot again immediately before creation.
- Real apply re-fetches the created PR and confirms title/body/base/head/draft/options match the normalized request.

## Stop Conditions

- `missing_auth`
- `repo_inference_failed`
- `base_resolution_failed`
- `template_not_found`
- `template_ambiguous`
- `remote_head_missing`
- `head_oid_mismatch`
- `existing_open_pr`
- `invalid_title`
- `invalid_body`
- `unsupported_claim`
- `stale_snapshot`
- `fingerprint_mismatch`
- `apply_verification_failed`

## Output

- Tell the user whether the run stopped at lint, validation, or apply.
- Include the final PR URL when creation succeeds.
- If blocked by an existing PR, include the existing PR URL and point the user to `gh-fix-pr-writeup`.
