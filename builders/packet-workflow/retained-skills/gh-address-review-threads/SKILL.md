---
name: gh-address-review-threads
description: Inspect unresolved GitHub PR review threads on the open pull request for the current branch, decide whether to accept, reject, defer, or defer outdated threads, post acknowledgement and completion replies with gh CLI, apply accepted fixes, and resolve completed threads. Use when Codex needs to read open PR review threads, summarize the planned direction or rejection, perform the work, then post a completion reply and resolve the finished threads.
---

# Address Review Threads

Use this skill to handle unresolved GitHub PR review threads on the current branch, then post the matching acknowledgement and completion replies and resolve the accepted threads.

This is a packet-driven repo workflow skill:
- keep GitHub auth, context collection, per-thread adjudication, final reply wording, GitHub mutations, and broad fixes local
- use deterministic scripts to compress thread history into `global`, `thread-batch`, and `thread` packets
- use `gpt-5.4-mini` workers only for narrow packet analysis and only for small fixes that satisfy the delegation guardrails
- stop on low confidence, stale snapshots, or ambiguous ownership instead of guessing

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
- Resolve `<runtime-root>` to `<repo-root>/.codex/tmp/packet-workflow/gh-address-review-threads/<run-id>/` and keep `.codex/tmp/` gitignored.
- Set `<packet-dir>` to `<runtime-root>/packets`.
- Set `<eval-log-json>` to `~/.codex/tmp/evaluation_logs/gh-address-review-threads/<run-id>.json` by default. If the sandbox blocks that path, use `<repo-root>/.codex/tmp/evaluation_logs/gh-address-review-threads/<run-id>.json` as an explicit override and keep `.codex/tmp/` gitignored.

## Workflow

1. Collect structured context.
- Run `gh auth status`.
- If authentication fails, stop and tell the user to run `gh auth login`.
- Before pushing accepted work, collect the pre-push snapshot with `<python-bin> -B <skill-dir>/scripts/collect_review_threads.py --repo <repo-root> --output <context-json>`.
- Build the initial packets with `<python-bin> -B <skill-dir>/scripts/build_review_packets.py --context <context-json> --repo-root <repo-root> --output-dir <packet-dir> --result-output <packet-dir>/build-result.json`.
- Draft a raw thread-actions plan locally.
- Run `<python-bin> -B <skill-dir>/scripts/validate_thread_action_plan.py --context <context-json> --plan <raw-plan-json> --phase <ack|complete> --output <validated-plan-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py init --context <context-json> --orchestrator <packet-dir>/orchestrator.json --output <eval-log-json>`.
- Run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase build --result <packet-dir>/build-result.json`.
- After accepted work is pushed, recollect a post-push snapshot, rebuild packets with `--previous-context <pre-push-context-json>` and `--reconciliation-input <reconciliation-json>`, then use `<python-bin> -B <skill-dir>/scripts/reconcile_outdated_threads.py --context <post-push-context-json> --packet-dir <packet-dir> --output <raw-complete-plan-json>` to seed the complete-phase plan.
- Read `<packet-dir>/orchestrator.json` first.
- Keep `<packet-dir>/global_packet.json` in view before reading any thread packet.
- Before deciding a thread, read that packet's `discussion`, `existing_self_reply`, `reply_candidates`, `validation_candidates`, and `ownership_summary` or `shared_fix_surface`.

2. Follow the review mode.
- `local-only`: keep thread analysis and code changes local.
- `targeted-delegation`: use 1-2 `gpt-5.4-mini` workers on thread-batch or singleton packets.
- `broad-delegation`: use 3-4 `gpt-5.4-mini` workers and add QA only when findings conflict or the fix surface is broad.
- Respect `review_mode_overrides` when churn, cross-group core files, or meaningful generated-file slices warrant widening the mode.
- Treat `packet_worker_map` as the routing authority for delegated thread packets.
- Treat `preferred_worker_families` as registry metadata only.
- Treat `recommended_workers` and `optional_workers` as derived convenience fields only.
- Read `references/review-threads-contract.md` before broad delegation or reply planning on a noisy PR.

3. Keep adjudication local.
- Decide `accept`, `reject`, `defer`, or `defer-outdated` per unresolved thread locally.
- Default outdated threads to `defer-outdated`.
- Same-run outdated transitions may auto-resolve only when the thread was non-outdated before this run's push, became outdated after the push, and current `HEAD` plus real validation evidence prove the accepted fix already covers the request.
- If a transitioned outdated thread still applies against current `HEAD`, return it to the normal unresolved queue for another implementation pass in the same run.
- If the same-run recheck is ambiguous, keep the thread `defer-outdated` and unresolved.
- Draft acknowledgement replies locally, then post the normalized `ack` reply for every `accept`, `reject`, `defer`, or `defer-outdated` thread before starting implementation, validation, commits, or pushes for that thread.
- Do not begin code edits for an accepted thread until its `ack` reply is posted unless GitHub mutation is temporarily blocked; if mutation is blocked, stop and report that blocker instead of silently proceeding.
- After the `ack` reply is posted, apply accepted fixes, validate them, then draft completion replies.
- Commit and push accepted work before posting a completion reply or resolving the thread.
- If collected review feedback includes actionable review-body or top-level PR comments that do not have a replyable review thread, call out that they are non-thread findings and use a top-level PR comment only when needed to preserve the same ack-before-work / complete-after-push workflow.

4. Respect reply and resolution rules.
- Start acknowledgement replies with the exact ack marker on line 1.
- Start completion replies with the exact complete marker on line 1.
- Apply actions only from the normalized validator output; do not feed raw `thread_actions` JSON into `apply_thread_action_plan.py`.
- Resolve only accepted threads after the pushed fix and validation are complete.
- Preserve still-accurate text when updating an existing reply.
- During `ack`, you may adopt one recent unmarked self-authored reply after the latest reviewer comment.
- During `complete`, never adopt an unmarked reply.
- Do not treat a thread as handled if the code change landed but the `ack` reply was skipped; missing `ack` is a workflow failure that must be corrected explicitly.

## Packet Contract

- `orchestrator_profile=standard`
- `decision_ready_packets=false`
- `worker_return_contract=generic`
- `worker_output_shape=flat`
- `xhigh_reread_policy=packet-first local adjudication with raw rereads only for explicit exception reasons`
- `packet_worker_map` routes delegated `thread-batch-*` and eligible singleton `thread-*` packets to `packet_explorer`.
- `common_path_contract` means the default local path is `global_packet.json + one thread-batch packet` or `global_packet.json + one thread packet`.
- `quality_escape_hints` is advisory only; explicit reread or escape decisions must still use the allowed reason enum or an explicit stop.
- `large_diff_auditor` remains an explicit optional QA worker, not a routed packet default.
- `context_fingerprint` must stay stable across collect, build, validate, and apply for one workflow run.

## Delegation Rules

- Never ask workers to rediscover the whole PR or raw review history from scratch.
- Pass `global_packet.json` plus one `thread-batch-*.json` or one `thread-*.json` packet.
- Require this output contract from each analysis worker:
  - `thread ids`
  - `problem summary`
  - `fix direction`
  - `risk`
  - `files to edit`
  - `tests to run`
- Delegate actual code edits only when all of these are true:
  - one batch or one thread
  - two files or fewer
  - one subsystem
  - no schema, public interface, config, or workflow changes
  - validation path is clear
- Otherwise keep the code change local and use workers only for analysis.
- Read `references/delegation-playbook.md` when `review_mode` is not `local-only`.
- Read `references/comment-contract.md` before drafting acknowledgement or completion replies.
- Read `references/review-threads-contract.md` for packet and routing rules.
- Read `references/thread-action-contract.md` before validating or applying `thread_actions`.
- Read `references/architecture-note.md` before changing the packet shape or reconsidering a hierarchical worker/result model.

## Scripts

- `scripts/collect_review_threads.py`
  - Collect PR metadata, changed files, diff stat, top-level comments, review submissions, unresolved and outdated review threads, and reply-update candidates.
- `scripts/build_review_packets.py`
  - Split the collected context into `orchestrator.json`, `global_packet.json`, per-thread packets, clustered batch packets, `packet_metrics.json`, and an eval-side build result.
  - When given `--previous-context` and `--reconciliation-input`, mark same-run non-outdated -> outdated transitions and attach conservative `outdated_recheck` evidence.
- `scripts/reconcile_outdated_threads.py`
  - Build a conservative complete-phase raw plan from post-push packets.
  - Auto-upgrade only same-run outdated transitions with `resolution_verdict=auto-accept`; leave ambiguous transitions unresolved.
- `scripts/validate_thread_action_plan.py`
  - Validate raw `thread_actions`, normalize them into deterministic order, enforce fallback and marker-conflict rules, and emit the canonical apply envelope.
- `scripts/apply_thread_action_plan.py`
  - Consume only the normalized validator output, add or update acknowledgement and completion replies, and resolve accepted threads after completion.
- `scripts/write_evaluation_log.py`
  - Record the shared evaluation log for efficiency, quality, and safety tracking.
- `scripts/review_thread_packet_contract.py`
  - Shared contract for packet naming, routing authority, reread reasons, common-path sufficiency, and eval-side packet metrics.
- `scripts/smoke_gh_address_review_threads.py`
  - Operator-facing dry-run smoke path that emits a short `status/reason/thread_counts/next_action` summary.
  - Default mode targets the current-branch PR and blocks cleanly on missing auth, missing `gh`, no open PR, or no unresolved threads.
  - `--synthetic` runs a self-contained temp-fixture smoke so maintainers can verify the full packet/build/reconcile/validate/apply dry-run path without a live PR.
- `scripts/thread_action_contract.py`
  - Shared contract for `reply_candidates`, `marker_conflicts`, `thread_actions`, context fingerprints, and validator/apply normalization rules.

## Evaluation

- Use the packet directory for machine-readable action results such as `<packet-dir>/ack-result.json` and `<packet-dir>/complete-result.json`.
- Treat `<packet-dir>/packet_metrics.json` as evaluation-only. Do not use token-efficiency counters as runtime routing input.
- After drafting a raw phase plan, prefer `<python-bin> -B <skill-dir>/scripts/validate_thread_action_plan.py ... --output <packet-dir>/ack-validated.json` or `... --output <packet-dir>/complete-validated.json`, then merge with `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase validate --result <validated-json>`.
- After `ack` or `complete`, prefer `<python-bin> -B <skill-dir>/scripts/apply_thread_action_plan.py ... --plan <validated-json> --result-output <packet-dir>/ack-result.json` or `... --plan <validated-json> --result-output <packet-dir>/complete-result.json`, then merge each result with `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py phase --log <eval-log-json> --phase apply --result <result-json>`.
- After the overall run, write `<packet-dir>/final-eval.json` with worker usage, token data when available, final usability, outputs, and notes, then run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py finalize --log <eval-log-json> --final <packet-dir>/final-eval.json`.
- Prefer the contract-default `<eval-log-json>` outside the repo. Keep packets and helper temp files under the fixed gitignored runtime root from `## Execution Roots`.
- Read `references/evaluation-log-contract.md` for the shared envelope and `references/gh-address-review-threads-evaluation-contract.md` for thread-specific fields.
- Read `references/architecture-note.md` for the rationale behind the current flat/generic contract and the criteria for revisiting hierarchy.
- Use `<python-bin> -B <skill-dir>/scripts/smoke_gh_address_review_threads.py --repo-root <repo-root>` for an operator-facing dry-run smoke on the current branch PR.
- Use `<python-bin> -B <skill-dir>/scripts/smoke_gh_address_review_threads.py --synthetic` for a self-contained reference smoke that does not require a live PR or `gh` auth.

## Output

- Tell the user which threads were accepted, rejected, deferred, or left outdated.
- Mention what code changed and which validations you ran.
- Include the PR URL.
- If blocked, name the blocker precisely: missing `gh` auth, no open PR for the branch, missing reply target, or unresolved implementation risk.
