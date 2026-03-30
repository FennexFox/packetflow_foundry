# History Rewrite Safety

Use this note when you are about to apply the rewritten messages.

## Preconditions

- Rewrite only recent linear commits unless the user explicitly wants a more
  complex history edit.
- Stop if a merge commit is in scope.
- Stop if the worktree is dirty.
- Stop if `.git/rebase-merge`, `.git/rebase-apply`, `.git/CHERRY_PICK_HEAD`,
  `.git/MERGE_HEAD`, or `.git/BISECT_LOG` indicates another git operation is in
  progress.
- Stop if `base_commit` is null. Root-commit rewrites are not supported by this
  workflow.
- Confirm immediately before changing refs.

## Plan File Expectations

`scripts/collect_recent_commits.py` writes a JSON plan. Before applying:

- keep `commits` in oldest-to-newest order
- leave `hash` values unchanged
- fill every `new_message` with the full replacement commit message
- keep the plan tied to the same branch tip; if `HEAD` moved, regenerate
- pass only the validated envelope to `apply_reword_plan.py`
- keep `context_fingerprint` stable from collect through apply

## Apply Strategy

`scripts/apply_reword_plan.py` uses a temporary worktree:

1. Start from the commit before the oldest targeted commit.
2. Cherry-pick each targeted commit in order.
3. Commit the same content with the replacement message.
4. Update the branch ref only if the current tip still matches the plan.

This avoids editing the main worktree during replay.

## Failure And Cleanup Contract

- If cherry-pick replay fails, the branch ref must remain unchanged.
- Temporary worktree removal and temp-directory cleanup must always be attempted.
- Cleanup outcome must be reported separately from the primary stop category.
- Primary replay failure stays `replay_failed` even when cleanup also leaves leftovers.

## After Rewriting

- Check `git log -n <n> --format=fuller`.
- Check `git status --short --branch`.
- If the branch already exists on a remote, tell the user that a force-push
  such as `git push --force-with-lease` will be required.
