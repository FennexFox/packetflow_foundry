# Comment Contract

Keep replies short, factual, and thread-local. Do not repeat the whole thread history.
When updating an existing reply, preserve any still-accurate text and edit only what is required to satisfy the marker, decision, implementation, or validation requirements.

## Acknowledgement Reply

Start with the exact `ack` marker on line 1.

Then include:
- one short sentence summarizing what the reviewer is asking
- one short sentence with `accept`, `reject`, `defer`, or `defer-outdated`
- if accepted, one short sentence describing the implementation direction or immediate validation plan
- if rejected or deferred, one short sentence with the reason or blocker

## Completion Reply

Start with the exact `complete` marker on line 1.

Then include:
- one short sentence describing what changed
- one short sentence listing the validation that actually ran
- one short sentence for any remaining caveat only if it matters to the reviewer

Use completion replies only for accepted threads that reached implementation, validation, and a push of the relevant change to the PR branch.

## Claims To Avoid

- Do not claim tests ran unless they actually ran.
- Do not claim behavior changed unless the code change supports it.
- Do not claim a fix landed until the relevant change is pushed to the PR branch.
- Do not claim rollout, migration, or compatibility impact unless verified.
- Do not claim the thread is fully addressed if remaining caveats still block resolution.
