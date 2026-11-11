---
topic: the-recovery-principal-does-not
author: claude-opus-5-5
created_at: 2026-11-11T02:02:50Z
---

## Proposal: A prepared recovery publication resumes by itself after the controller restarts

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to contracts.md §"Expedited incident execution" and a new scenario. They require the independently hosted released controller to complete, without an operator request, a recovery publication that a restart interrupted. On each start of its service, and on each later due sweep pass, the controller resumes every pending action for which the principal's receipt lookup reports an unresolved publication attempt. The resume is the same exactly-once publication the operator's explicit retry already reaches. It settles from forge facts first, so a commit that already landed is only recorded. Otherwise it sends only the one recorded commit through the expected-head compare-and-swap, and a moved head recomputes or records a conflict as the existing rules require. It honours the action's persisted back-off and terminal state and counts toward its retry bounds. It makes its principal calls outside the controller's repository fence, so it never delays another action's first-failure recovery.

### Motivation

Plan expedited-incident-hardening (epic livespec-dev-tooling-dh3hub), follow-up (b), work item livespec-dev-tooling-52die6. Evidence from thhgeg cycle B, recorded on livespec-dev-tooling-thhgeg at 2026-11-10T21:19:32Z: the scratch observer unit was SIGKILLed at 21:07:29Z after its principal's publication ledger recorded one attempt at status `prepared` (commit 3b2fd89d) and before the ref update; systemd restarted it at 21:07:31Z. At 21:08:05Z the action still read `pending`, the ledger still read `prepared` and the scratch head had not moved. `POST /reconcile` with `retry_publish: false` answered pending ("exact recovery receipt remains unavailable"), and only `retry_publish: true` completed the publication, re-sending the one recorded commit. docs/incident-inverse.md and docs/incident-observer-service.md describe that path: a timeout or unknown outcome stays pending, and only an operator's explicit reconcile takes it further. The ratified §"Expedited incident execution" requires immutable intent and post-timeout receipt recovery, but not completion on restart, so an incident whose recovery is interrupted by a restart waits on a human while master stays red. The filing classification recorded spec-change (verdict partial) for this reason, and the plan session kept that tier: the item's Definition of Done asserts completion with no operator call, which the ratified text does not require. Independent pre-filing review (2026-11-11) walked the draft through the live code. The principal is not a service: it is a subprocess the observer runs per call, and it owns the publication journal. The process systemd restarts is the observer, whose conflict sweep already runs at start and settles pending actions with retry off. The explicit retry path (`recover_incident_inverse(resume_unresolved=True)` → `Publisher.resume`) already re-sends the recorded commit, so the observer can see only what the principal's lookup reports. Live code holds the observer's repository lock across the whole retried recovery, which can take minutes of principal calls. A per-start resume bound would both permit a crash loop and park a transient forge outage on a human. It would also bypass the back-off, terminal-state handling and the global attempts bound that livespec-dev-tooling-fx32ej is adding, so the resume follows those instead.

### Proposed Changes

In `contracts.md` §"Expedited incident execution", insert the following paragraph directly after the paragraph that begins "The complete landed incident patch, all commits/trees and exact PR identity MUST define rollback.":

> A recovery publication interrupted by a restart MUST complete without an operator request. An unresolved publication attempt is a revert commit the recovery principal recorded durably before asking the target branch to move, for which no effect receipt is yet recorded. On each start of the independently hosted released controller's service, and on each later due sweep pass, the controller MUST resume every pending recovery action of its configured repository and target branch for which the principal's receipt lookup reports an unresolved publication attempt. The resume MUST be the same exactly-once publication an operator's explicit publish retry reaches, under the same immutable action identity. It MUST first settle the attempt from forge facts, and when those facts show the recorded commit landed, it MUST record that receipt and publish nothing. Otherwise it MUST publish only the one recorded commit, through the expected-head compare-and-swap on the configured target branch. When the target branch head has moved and the recorded commit did not land, the resume MUST NOT publish the recorded commit and MUST proceed as the preceding paragraph requires on head movement. The resume MUST honour any retry back-off and terminal state the controller has persisted for the action, and each resume MUST count as one attempt toward every retry bound that applies to the action. A resume that cannot complete MUST leave the action pending, so that a later due pass or the operator's explicit reconcile can still complete it. An operator reconcile of an action the resume completed MUST answer the retained receipt and MUST NOT publish again. The resume MUST hold the controller's repository fence only for short reads and writes of the action record, and MUST make its principal calls outside that fence, so that it never delays first-failure recovery of another action.

In `scenarios.md`, add the following scenario directly after `## Scenario: an incident revert preserves later changes without waiting for CI`:

~~~markdown
## Scenario: a prepared incident recovery publication completes after the controller restarts

```gherkin
Given a pending incident recovery action with no effect receipt, whose recovery principal recorded an unresolved publication attempt before the target branch ref moved
When the controller's service restarts
Then the controller completes that publication on its next due sweep pass, with no operator reconcile, sending only the one recorded commit
And a recorded commit that forge facts show already landed is recorded as the receipt and not published again
And a moved target branch head whose recorded commit did not land causes inverse recomputation or an owned rollback-conflict instead of publication
And a resume that cannot complete leaves the action pending, completable by a later due pass or the operator's explicit reconcile
And the resume honours the action's persisted back-off and terminal state and counts toward its retry bounds
```
~~~

The revise commit MUST add a `tests/heading-coverage.json` row for the new heading, a spec-first `"test": "TODO"` whose reason names the integration tier or above and whose `work_item` is `livespec-dev-tooling-52die6`, and MUST regenerate `tests/heading-coverage-debt.json`. Work item livespec-dev-tooling-52die6's Definition of Done `References:` line MUST then name the new heading.
