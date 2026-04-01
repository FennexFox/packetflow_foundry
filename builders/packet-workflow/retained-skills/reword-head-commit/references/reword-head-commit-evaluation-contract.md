# Reword Head Commit Evaluation Contract

Use this file for `reword-head-commit` evaluation logs.

Record:
- branch identity and original `head_commit`
- whether validation passed
- whether the run stayed dry-run or attempted an amend
- whether the amend succeeded
- whether a force push is likely because an upstream exists
- the resulting `new_head` when the amend succeeds
- the final stop reasons when validation or preconditions block the run
