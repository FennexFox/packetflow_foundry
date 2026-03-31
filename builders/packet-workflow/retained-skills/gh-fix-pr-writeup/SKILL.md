---
name: gh-fix-pr-writeup
description: Verify and repair a GitHub pull request title and body when the user gives a PR number or asks to audit, rewrite, or fix PR text. Use when Codex must compare a PR's current writeup against repository PR instructions/templates and the actual code changes, then update it with gh CLI if the title/body are missing, truncated, generic, misleading, or unsupported by the diff.
---

# PR Writeup Repair

Use this skill to check whether a specific PR's title and body match repository PR rules and the real change set, then fix the PR with `gh` only when the replacement is materially better.

This is a packet-heavy orchestrator skill with local final synthesis:
- keep GitHub auth, context collection, final judgment, final title/body drafting, validator gating, and guarded PR mutation local
- keep worker outputs proposal-grade and `generic / flat`
- keep `rules_packet.json` authoritative for hard rules and `synthesis_packet.json` limited to run-specific drafting basis
- keep token-efficiency metrics out of runtime packets; record them in `packet_metrics.json` and the evaluation log instead

Boundary:
- Keep reusable packet-workflow semantics in `references/core-contract.md`.
- Keep default repo bindings and review-doc ownership in `profiles/default/profile.json`.
- Keep vendored repo overrides data-only in `.codex/project/profiles/`.

## Execution Roots

- Resolve `<skill-dir>` as the directory containing this `SKILL.md`.
- Resolve `<python-bin>` as a concrete interpreter path before running any helper script.
- On Windows, prefer a non-`WindowsApps` interpreter from `Get-Command python -All | Where-Object { $_.Source -notlike '*Microsoft\WindowsApps*' } | Select-Object -ExpandProperty Source -First 1`.
- If that probe returns nothing, scan `%LOCALAPPDATA%\Python\pythoncore-*\python.exe` and `%LOCALAPPDATA%\Programs\Python\Python*\python.exe`, then reuse the first concrete path you find.
- If you already resolved a concrete interpreter path outside the sandbox, reuse that exact path inside the sandbox instead of calling `py` or bare `python`.
- Run helper scripts as `<python-bin> -B <skill-dir>/scripts/...`.
- Stop and report the blocker if you cannot resolve a concrete interpreter path.
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/gh-fix-pr-writeup/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `~/.codex/tmp/evaluation_logs/gh-fix-pr-writeup/<run-id>.json` by default. If the sandbox blocks that path, use `<repo-root>/.codex/tmp/evaluation_logs/gh-fix-pr-writeup/<run-id>.json` as an explicit override and keep `.codex/tmp/` gitignored.

## Workflow

1. Verify GitHub access first.
- Run `gh auth status`.
- If authentication fails, stop and tell the user to run `gh auth login`.

2. Collect, lint, and build packets before broad rereads.
- Run `<python-bin> -B <skill-dir>/scripts/collect_pr_context.py <pr-number> --repo-root <repo-root> --output <context-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/lint_pr_writeup.py --context <context-json> --output <lint-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/build_pr_review_packets.py --context <context-json> --lint <lint-json> --output-dir <packet-dir> --result-output <packet-dir>/build-result.json`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <context-json> --orchestrator <packet-dir>/orchestrator.json --lint <lint-json> --output <eval-log-json>`.
- Read `<packet-dir>/orchestrator.json` first.
- Read `<packet-dir>/rules_packet.json` locally before drafting any replacement title/body.
- Keep common-path local drafting on `rules_packet.json + synthesis_packet.json + <= 1 focused packet`.

3. Follow the review mode and packet contract.
- `local-only`
  - use no workers
  - keep drafting on `rules_packet.json`, `synthesis_packet.json`, and one focused packet at most
- `targeted-delegation`
  - use 1-2 narrow workers on focused packets
- `broad-delegation`
  - use 3-4 narrow workers
  - QA is still a rare exception, not the common path
- Treat packet file lists as representative slices, not a complete inventory.
- Raw reread is allowed only for `sample_omission`, `worker_conflict`, `claim_dispute`, or `validator_blocker`.
- `packet_insufficiency` is a failure, not an allowed reread reason.

4. Keep the critical path local.
- `rules_packet.json` is the only authority source for hard rules.
- `synthesis_packet.json` is the run-specific decision packet for this PR; it must not duplicate the full rules prose.
- Draft the final title/body locally even when workers were used.
- Workers may suggest bullets or evidence, but they must not emit embedded edit code or take over the PR mutation step.
- Run `<python-bin> -B <skill-dir>/scripts/validate_pr_writeup_edit.py --context <context-json> --title "<title>" --body-file <body-file> [--qa-result <qa-json>] --output <packet-dir>/validation.json` before any mutation.
- `validate_pr_writeup_edit.py` re-runs `gh auth status`, compares the live PR snapshot and changed-file list against the collected context, computes `qa_required`, and fails closed on stale context, invalid replacement text, unsupported claims, or missing QA clear when QA is required.
- Run `<python-bin> -B <skill-dir>/scripts/apply_pr_writeup.py --validation <packet-dir>/validation.json [--dry-run] [--result-output <packet-dir>/apply-result.json>` for the guarded apply step.
- `apply_pr_writeup.py` consumes validator output only, re-checks the live snapshot against the validated snapshot, and fails closed if `qa_required` is still true without QA clear.

5. Judge the title and body conservatively.
- Use the repository's PR guidance and template order exactly.
- Title the primary shipped behavior or workflow change, not the noisiest file.
- Keep bullets concise and supported by the diff or by commands you actually ran.
- Do not claim tests, defaults, reload/restart requirements, migration impact, or mitigation steps unless you can verify them.

## Packet Contract

- `orchestrator_profile=packet-heavy-orchestrator`
- `decision_ready_packets=false`
- `worker_return_contract=generic`
- `worker_output_shape=flat`
- `shared_local_packet=synthesis_packet.json`
- `common_path_contract=rules + synthesis + <=1 focused`
- `packet_worker_map` is the routing authority for delegated packet analysis.
- `packet_metrics.json` is evaluation-only and must not be used as runtime routing data.

## Delegation Rules

- Never ask workers to rediscover the whole repo rules or raw diff from scratch.
- Pass `global_packet.json`, one focused packet, and only the explicit file slice needed for grounding.
- `rules_packet.json` is local-first. A rules worker is a cross-check, not a replacement for local verification.
- Prefer these roles:
  - `docs_verifier` for the optional `rules_packet.json` cross-check
  - `evidence_summarizer` for `testing_packet.json`
  - `packet_explorer` for `runtime_packet.json` and `process_packet.json`
  - `large_diff_auditor` or explicit `gpt-5.4-mini` for the rare QA pass
- Require every normal worker to return:
  - `primary outcome`
  - `evidence files`
  - `unsupported claims`
  - `suggested PR bullets`
- Require the optional QA worker to return:
  - `keep_or_revise`
  - `rule violations`
  - `coverage gaps`
  - `unsupported claims`
- Read `references/delegation-playbook.md` only when `review_mode` is not `local-only`.

## Scripts

- `scripts/collect_pr_context.py`
  - Collect PR metadata, changed-file groups, diff stat, template headings, rule-file paths, and instruction snippets.
- `scripts/lint_pr_writeup.py`
  - Flag deterministic problems and emit structured drafting basis for the synthesis packet.
- `scripts/build_pr_review_packets.py`
  - Emit lean runtime packets, `synthesis_packet.json`, `packet_metrics.json`, and build-result metadata.
- `scripts/validate_pr_writeup_edit.py`
  - Validate candidate replacements against the collected context, candidate lint checks, QA gate, and the live PR snapshot before apply.
- `scripts/apply_pr_writeup.py`
  - Consume validator output only and apply `gh pr edit` only when the validated snapshot still matches live PR state.
- `scripts/smoke_gh_fix_pr_writeup.py`
  - Run the temp-repo smoke path with stubbed `gh` responses.
- `scripts/write_evaluation_log.py`
  - Record the shared evaluation log for efficiency, quality, and safety tracking.

## Evaluation

- After build, run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase build --result <packet-dir>/build-result.json`.
- After lint, run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase lint --result <lint-json>`.
- After validation, merge `validation.json` with the `validate` phase.
- After guarded apply or dry-run, merge `apply-result.json` with the `apply` phase.
- `packet_metrics.json` and build-result metadata should drive token-efficiency and common-path regression tracking.
- Runtime packets must stay lean and must not embed packet-size or token counters.
- Keep the evaluation log at the contract-default outside-repo path unless you intentionally need the gitignored `.codex/tmp/` fallback.

## Output

- Tell the user whether the PR already matched the rules or what changed.
- Include the final PR URL.
- Mention the validation commands that actually ran.
- If blocked, name the blocker precisely: missing `gh` auth, stale PR snapshot, invalid replacement text, missing QA clear, or insufficient diff support.
