---
name: reword-recent-commits
description: Rewrite or reword a recent range of Git commit messages to the active repository's commit-message rules. Use when Codex needs replay-style safety, packet/audit artifacts, or anything broader than a trivial HEAD-only amend path.
---

# Reword Recent Commits

Use this skill to rewrite a recent commit range with a guarded `prepare -> validate -> replay/apply` flow.

## Use When

- the target is more than a trivial `HEAD`-only amend, or replay-style safety is preferred
- commit-rule discovery, packet evidence, validation, and apply artifacts should be retained under repo-local `.codex/tmp/`
- final message drafting and ref mutation must stay local

## Execution Roots

- `<skill-dir>`: directory containing this `SKILL.md`
- `<python-bin>`: concrete interpreter path; on Windows prefer a non-`WindowsApps` Python and reuse that exact interpreter across every helper phase
- `<artifact-root>`: `<repo-root>/.codex/tmp/packet-workflow/reword-recent-commits/<run-id>/`
- `<packet-dir>`: `<artifact-root>/packets`
- `<eval-log-json>`: `<artifact-root>/eval-log.json`

## Entry

1. Prepare packet artifacts and the editable message template.
- Run `<python-bin> -B <skill-dir>/scripts/reword_recent_commits.py --repo <repo-root> --count <n> --prepare-only`.
- Fill `message-template.json` by editing `commits[*].new_message` only.
2. Re-run the same driver with the completed template.
- Run `<python-bin> -B <skill-dir>/scripts/reword_recent_commits.py --repo <repo-root> --count <n> --messages-file <message-template-json>`.
- Add `--apply` only after confirmation. Without `--apply`, the driver validates and runs the apply phase in `--dry-run` mode.
- Use `--temp-root <path>` only when replay needs a specific writable parent for the temporary worktree.
3. Read runtime packets before drafting or delegating.
- Read `orchestrator.json` first, then `global_packet.json`, then `rules_packet.json`, then one commit packet at a time on the common path.
- If `review_mode` is delegated, follow `packet_worker_map` and `references/delegation-playbook.md` per focused packet.
4. Let the driver handle validation, apply, and evaluation-log finalization for the live run.

## Continue Only If

- final commit messages, confirmation, and `git update-ref` stay local
- `packet_worker_map` is the routing authority and worker output stays proposal-grade only
- build-result and evaluation artifacts keep review baselines, adjustments, worker recommendations, and similar observability metadata out of runtime routing unless a later phase actually consumes them
- the same concrete interpreter path is reused for collect, build, validate, apply, and smoke/debug helper phases
- apply consumes validator-normalized output only

## Stop When

- the messages file fingerprint, branch, or head commit no longer matches the prepared context
- the worktree is dirty, another git operation is active, or the branch tip drifted
- a merge commit appears in scope or `base_commit` is null
- replay temp-root setup fails or rewrite safety checks block the run

## Final Response

- say whether the run is `prepared`, `dry-run`, or `ok`
- include the artifact root or new head when relevant
- name the blocker precisely when the run stops
- mention whether a later force-push is likely

## References

- `references/reword-recent-commits-contract.md`
- `references/delegation-playbook.md`
- `references/history-rewrite-safety.md`
- `references/rule-discovery.md`
- `references/core-contract.md`
- `references/reword-recent-commits-evaluation-contract.md`
- `<python-bin> -B <skill-dir>/scripts/smoke_reword_recent_commits.py`
