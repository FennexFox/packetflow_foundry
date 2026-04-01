# Amend Safety

The express path is only for simple `HEAD` message rewrites.

Preconditions:
- `HEAD` must be the current branch tip
- the worktree must be clean
- no rebase, merge, cherry-pick, or bisect operation may be in progress
- `HEAD` must not be detached
- `HEAD` must not be a merge commit
- `HEAD` must not be the root commit
- commit-message rules must be explicit, not only derived from history

Apply strategy:
1. collect rules and the current `HEAD` context
2. validate the replacement message against the shared reword contract
3. re-check branch-tip safety immediately before mutation
4. amend `HEAD` directly with `git commit --amend -F <message-file>`
5. report whether an upstream makes `--force-with-lease` likely

Why this stays narrow:
- direct amend is faster than replay, but it is intentionally not the generic
  answer for broader history rewrites
- use `reword-recent-commits` when replay-style safety or packet evidence is
  needed
