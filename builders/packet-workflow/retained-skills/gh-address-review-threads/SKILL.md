---
name: gh-address-review-threads
description: Inspect unresolved GitHub PR review threads on the open pull request for the current branch, decide whether to accept, reject, defer, or defer outdated threads, post acknowledgement and completion replies with gh CLI, apply accepted fixes, and resolve completed threads. Use when Codex needs to read open PR review threads, summarize the planned direction or rejection, perform the work, then post a completion reply and resolve the finished threads.
---

# Address Review Threads

Use this skill to handle unresolved GitHub PR review threads on the current branch with a manifest-gated `collect -> build -> validate -> apply` workflow.

## Use When

- an open PR for the current branch has unresolved review threads
- final thread decisions, final reply wording, pushes, and resolution stay local
- mini workers are used only for narrow packet analysis or small isolated fixes

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python
- `<runtime-root>`: `<repo-root>/.codex/tmp/packet-workflow/gh-address-review-threads/<run-id>/`
- `<manifest-json>`: `<runtime-root>/manifest.json`
- `<eval-log-json>`: `<repo-root>/.codex/tmp/evaluation_logs/gh-address-review-threads/<run-id>.json`

## Entry

1. Run `gh auth status`; stop if authentication is missing.
2. Collect the pre-push snapshot with `<python-bin> -B <skill-dir>/scripts/collect_review_threads.py --repo <repo-root> --output <pre-context-json>`.
3. Create the run manifest with `<python-bin> -B <skill-dir>/scripts/manage_review_thread_run.py start --repo-root <repo-root> --context <pre-context-json>`.
4. Build pre-push packets with `<python-bin> -B <skill-dir>/scripts/build_review_packets.py --context <manifest.pre.context> --repo-root <repo-root> --output-dir <manifest.pre.packet_dir> --result-output <manifest.pre.build_result>`.
5. Initialize the evaluation log, then merge the build result.
6. Read the active phase `orchestrator.json` first, then `global_packet.json`, then the relevant `thread-batch` or `thread` packet.
7. Draft the raw `ack` plan locally, validate it, and record it with `record-plan --phase ack`.
8. Apply the normalized `ack` plan, write `<manifest.ack.result>`, and record the live apply result with `record-apply --phase ack --result <manifest.ack.result>`.
9. After real validation runs for accepted work, record the commands with `record-validation`.
10. After the accepted work is pushed, run `post-push`, rebuild post-push packets with `--previous-context` and `--reconciliation-input`, seed the complete plan with `reconcile_outdated_threads.py`, validate it, record it with `record-plan --phase complete`, then apply and record `complete`.
11. Merge validate and apply results as each phase completes. After the last apply result, write `<manifest.evaluation.final>` with the local final observations and run `<python-bin> -B <skill-dir>/scripts/write_evaluation_log.py finalize --log <eval-log-json> --final <manifest.evaluation.final>`.

## Continue Only If

- `manage_review_thread_run.py` allows the next transition.
- `ack` is posted and recorded as `ack-applied` before validation recording, post-push staging, or further accepted-thread work.
- `record-apply` sees `apply_succeeded=true`, `fingerprint_match=true`, and a non-dry-run result for live runs.
- `apply_thread_action_plan.py` consumes only normalized validator output.
- `packet_worker_map` is the runtime routing authority.
- `packet_metrics.json` and build-result worker derivation are evaluation-side only.
- same-run outdated auto-resolve has accepted-before-push provenance, current-`HEAD` evidence, and real validation evidence.
- broad or cross-cutting fixes stay local even when delegation is allowed for narrow analysis.

## Stop When

- `gh` auth is missing, there is no open PR, or a reply target is missing
- the manifest gate rejects `record-plan`, `record-apply`, `record-validation`, or `post-push`
- `context_fingerprint` changed and packets need recollection
- ownership, validation path, or outdated recheck is ambiguous
- code-edit delegation guardrails fail; keep the implementation local instead of forcing delegation

## Final Response

- list accepted, rejected, deferred, and `defer-outdated` threads
- state what changed and which validation ran
- include the PR URL
- if blocked, name the blocker precisely

## References

- `references/review-threads-contract.md`
- `references/comment-contract.md`
- `references/thread-action-contract.md`
- `references/delegation-playbook.md`
- `references/gh-address-review-threads-evaluation-contract.md`
- `references/architecture-note.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_gh_address_review_threads.py --repo-root <repo-root>`
- `<python-bin> -B <skill-dir>/scripts/smoke_gh_address_review_threads.py --synthetic`
