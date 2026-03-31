# Commit Plan Contract

Draft `commit-plan.json` as a single JSON object.

## Packet Interface

- The focused packets are decision-ready and feed local adjudication.
- Workers read `global_packet.json` first, then one focused packet such as `rules_packet.json`, `worktree_packet.json`, `candidate-batch-XX.json`, or `split-file-XX.json`.
- Workers return proposal-grade candidate records only; the final plan stays local.
- Keep `commit-plan.json` consistent with the packet routing and stop conditions emitted by `orchestrator.json`.
- Common-path local adjudication should finish with `rules_packet.json + worktree_packet.json + one focused packet at a time`.
- Raw diff rereads are allowed only for explicit exception reasons:
  - `conflicting_signals`
  - `missing_required_evidence`
  - `schema_mismatch`
  - `insufficient_excerpt_quality`
  - `stale_worktree_fingerprint`
  - `ambiguous_hunk_match`
- On canonical common-path fixtures, `insufficient_excerpt_quality` is a packet-contract failure rather than a normal fallback.

## Required Top-Level Fields

- `repo_root`
- `base_head`
- `worktree_fingerprint`
- `input_scope`
- `overall_confidence`
- `validation_commands`
- `omitted_paths`
- `stop_reasons`
- `commits`

## Phase Field Tables

### Draft Plan

Top-level fields:
- required
  - `repo_root`
  - `base_head`
  - `worktree_fingerprint`
  - `input_scope`
  - `overall_confidence`
  - `validation_commands`
  - `omitted_paths`
  - `stop_reasons`
  - `commits`
- allowed
  - none
- ignored
  - none

Commit-entry fields:
- required
  - `commit_index`
  - `intent_summary`
  - `type`
  - `scope`
  - `subject`
  - `body`
  - `whole_file_paths`
  - `untracked_paths`
  - `split_paths`
  - `selected_hunk_ids`
  - `supporting_paths` (assume file/path-oriented evidence first unless the contract is explicitly widened)
  - `targeted_checks`
  - `confidence`
- allowed
  - none
- ignored
  - none

### Validator Output

`validate_commit_plan.py` must emit:

- `valid`
- `can_apply`
- `errors`
- `warnings`
- `error_details`
- `warning_details`
- `stop_reasons`
- `stop_categories`
- `deduped_validation_commands`
- `normalized_plan`
- `normalized_plan_fingerprint`
- `expected_worktree_fingerprint`
- `current_worktree_fingerprint`
- `apply_gate_status`

`normalized_plan` must contain only normalized required fields. Unknown extra fields from the draft plan are removed and surfaced through fixed warning codes.
`apply_gate_status` must include `current_stop_categories` and `local_hard_stop_categories`.

### Apply Input

- `apply_commit_plan.py` consumes validator output, not raw `commit-plan.json`.
- `--dry-run` follows the same rule and must read `normalized_plan` from the validator output.
- Apply must fail closed when:
  - validator output is invalid
  - the normalized-plan fingerprint does not match
  - the current worktree fingerprint has changed since validation
  - applicable stop categories remain uncovered or unresolved
- Apply must emit structured JSON for both success and hard-stop outcomes.
- Hard-stop payloads must name the `apply_status.stop_category` when known.
- If apply fails after creating one or more commits, it must roll back those created commits to the original HEAD with a non-destructive reset that preserves the user's working-tree changes.

## Commit Entry Fields

Each item in `commits` must include:

- `commit_index`
- `intent_summary`
- `type`
- `scope`
- `subject`
- `body`
- `whole_file_paths`
- `untracked_paths`
- `split_paths`
- `selected_hunk_ids`
- `supporting_paths` (assume file/path-oriented evidence first unless the contract is explicitly widened)
- `targeted_checks`
- `confidence`

## Validation Expectations

- Every changed path must appear exactly once across:
  - one commit entry, or
  - `omitted_paths`
- `untracked_paths` must contain only untracked files.
- `split_paths` must contain only tracked modified text files marked split-eligible in `worktree.json`.
- Every `selected_hunk_id` must belong to one file in `split_paths`.
- If a file is split, all of its current hunks must be assigned exactly once across the plan.
- `validation_commands` should be the deduped union of all `targeted_checks`.
- Keep `stop_reasons` empty when the plan is safe to apply.
- Validation must fail closed on active git operations, ambiguous split rematch risk, unsupported partial splits, and infeasible targeted checks.

## Fixed Codes

Validator warning codes:

- `W_PLAN_UNKNOWN_TOP_LEVEL_FIELD`
- `W_PLAN_UNKNOWN_COMMIT_FIELD`
- `W_PLAN_BODY_STRING_NORMALIZED`
- `W_PLAN_COMMIT_INDEX_NON_SEQUENTIAL`
- `W_PLAN_EMPTY_SCOPE`
- `W_PLAN_NON_BULLET_BODY`
- `W_PLAN_TARGETED_CHECK_MISSING_FROM_PLAN`

Validator error codes:

- `E_PLAN_MISSING_FIELD`
- `E_PLAN_EMPTY_COMMITS`
- `E_PLAN_HEAD_CHANGED`
- `E_PLAN_FINGERPRINT_CHANGED`
- `E_PLAN_REPO_ROOT_MISMATCH`
- `E_PLAN_BASE_HEAD_MISMATCH`
- `E_PLAN_WORKTREE_FINGERPRINT_MISMATCH`
- `E_PLAN_ACTIVE_GIT_OPERATION`
- `E_PLAN_DUPLICATE_VALIDATION_COMMAND`
- `E_PLAN_UNKNOWN_PATH`
- `E_PLAN_INVALID_UNTRACKED_PATH`
- `E_PLAN_INVALID_SPLIT_PATH`
- `E_PLAN_PARTIAL_SPLIT_UNSUPPORTED`
- `E_PLAN_UNKNOWN_HUNK`
- `E_PLAN_PATH_ASSIGNMENT_MISMATCH`
- `E_PLAN_HUNK_ASSIGNMENT_MISMATCH`
- `E_PLAN_AMBIGUOUS_SPLIT_REMATCH`
- `E_PLAN_ADJACENT_SPLIT_HUNKS`
- `E_PLAN_TARGETED_CHECK_UNAVAILABLE`

## Local Hard Stops

Apply and local validation must preserve explicit hard-stop categories for operator-facing reporting:

- `active_git_operation`
- `ambiguous_split_rematch`
- `partial_split_unsupported`
- `targeted_check_unavailable`
- `targeted_check_failed`
- `commit_creation_failed`
- `rollback_failed`

## Message Construction

- Compose the final subject as `<type>(<scope>): <subject>` unless the collected rules explicitly say otherwise.
- Keep `subject` to the human-readable summary fragment only, not the full Conventional Commit line.
- Keep `body` as a list of bullet lines or an empty list.

Example shape:

```json
{
  "repo_root": "C:/repo",
  "base_head": "abc123",
  "worktree_fingerprint": "sha256:...",
  "input_scope": "all-local-changes",
  "overall_confidence": "high",
  "validation_commands": [
    "python -m unittest discover -s .github/scripts/tests -p \"test_perf_telemetry_automation.py\""
  ],
  "omitted_paths": [],
  "stop_reasons": [],
  "commits": [
    {
      "commit_index": 1,
      "intent_summary": "Allow direct telemetry comparisons when exactly one fix toggle differs.",
      "type": "fix",
      "scope": "infra",
      "subject": "allow single fix-toggle comparisons",
      "body": [
        "- update telemetry automation to accept one known fix-toggle delta",
        "- add tests and reporting guidance for the new comparison rule"
      ],
      "whole_file_paths": [
        ".github/scripts/perf_telemetry_automation.py",
        ".github/scripts/tests/test_perf_telemetry_automation.py",
        ".github/ISSUE_TEMPLATE/performance_telemetry_report.yml",
        "MAINTAINING.md",
        "PERF_REPORTING.md"
      ],
      "untracked_paths": [],
      "split_paths": [],
      "selected_hunk_ids": [],
      "supporting_paths": [],
      "targeted_checks": [
        "python -m unittest discover -s .github/scripts/tests -p \"test_perf_telemetry_automation.py\""
      ],
      "confidence": "high"
    }
  ]
}
```
