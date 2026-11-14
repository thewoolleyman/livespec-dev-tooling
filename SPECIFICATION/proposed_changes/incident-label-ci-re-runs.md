---
topic: incident-label-ci-re-runs
author: claude-opus-5-5 (expedited-incident-response-flag)
created_at: 2026-11-14T19:45:00Z
---

## Proposal: The replay gate's incident admission reads the current pull-request body and names a missing incident block

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" for the `red_green_replay` range gate's incident admission. The incident block the gate reads to locate an attempt MUST be the pull request's current body. Either the gate reads the body live through the authenticated forge read, or the incident label workflow starts a fresh run whose event carries the current body; a re-run of a run whose event payload predates the block does neither. When no block is found, the gate MUST name that and the source it read, instead of returning silently. Add the matching steps to the provenance scenario.

### Motivation

Work item livespec-dev-tooling-eqtyyr, found by the plan seat's xdt4ue fork while diagnosing livespec-dev-tooling#4533's CI attempt 2. The incident label workflow (`incident-label-ci.yml`) re-runs the pull request's existing CI run when the expedited-incident-response label is added. A GitHub re-run replays the ORIGINAL event payload. `livespec_dev_tooling/checks/_red_green_replay_incident.py` reads the pull request from `GITHUB_EVENT_PATH`, so a run whose `pull_request` event was delivered before the author added the `livespec-incident-ci` block never sees that block, and the expedited commit can never be admitted on that re-run, however the chain records it. The function then returns `False` with no line saying why, so the refusal output reports only the commit's missing TDD trailers. The workaround (close and reopen the pull request) needs a merge-quiet window because of livespec-dev-tooling-3u5rzz. The ratified section covers the incident CI selection step's pull-request body read and the entrance's refusal on a failed read, but not where the replay gate's admission reads its block from, or what it says when the block is absent. So the pre-dispatch screen holds the item at spec-change tier, verdict unstated (spec v221).

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Expedited incident execution", at the end of the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment", append:

"The `red_green_replay` range gate locates the attempt it asks the chain about from the pull request's `livespec-incident-ci` block, and that block MUST be read from the pull request's body as it stands when the gate runs. Either the gate reads the body through the authenticated forge read, under the forge-call rule this section states, or the incident label workflow, when it adds the expedited-incident-response label, starts a fresh run whose event carries the current body rather than re-running a run whose event payload predates it. A re-run whose event payload predates the block MUST NOT be how the label takes effect. When the gate finds no block, it MUST print one line naming that and the source it read (for example `incident admission skipped: no livespec-incident-ci block in <source>`), and the commit stays convicted on its missing evidence."

In `SPECIFICATION/scenarios.md`, §"Scenario: incident commit provenance remains verifiable on normal master", after its last step, "And a workflow incident requires its scoped host authorization receipt through the credential boundary while the factory retains its existing workflow credential scope.", append:

```gherkin
And when the expedited-incident-response label is added to a pull request whose in-flight CI run's event predates its livespec-incident-ci block, the run that then executes the replay gate MUST read the current block and admit the expedited commit the chain records.
And when the pull request carries no block, the replay gate MUST print a line naming the missing block and the source it read, and keep the commit convicted.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.
