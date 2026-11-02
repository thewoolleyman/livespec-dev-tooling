---
topic: radar-readiness-reader-blockers-from
author: claude-opus-5-5
created_at: 2026-11-02T19:58:15Z
---

## Proposal: Radar readiness states and blocker naming

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State the shape of a readiness result in ## Maintainer radar. Each target is exactly one of DONE, READY or NOT READY, and a NOT READY result names every open blocker as `<tenant>:<id>`. Add one scenario that exercises both rules.

### Motivation

Work item livespec-dev-tooling-m2x5pt (plan radar-and-deterministic-admission, assertion 4) was refused at factory dispatch on 2026-11-02T19:54Z. It is held as spec-change tier with reason unratified-topic and linked topic radar-readiness-reader-blockers-from. The spec-stated judgement at v115 found ## Maintainer radar silent on two behaviours the item's Definition of Done asserts. First, readiness names each blocker with its tenant and id. Second, a closed target is reported as done rather than as ready or blocked. The section already says a closed entry is DONE and that blockers are `blocks` edges plus `blocked_by` references. It does not say what a readiness result carries, so a reader could report a closed target as READY, or report NOT READY without naming its blockers. Both shapes would leave the coordinator printout and the admission function unable to say why a target waits. The plan owner decided to close the gap at the spec rather than weaken the item's Definition of Done (coordinator ack, 2026-11-02).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Maintainer radar", append this sentence group at the end of the final paragraph (after "Readers MUST read an absent `dependencies` key as no edges."):

> Readiness MUST report each radar target as exactly one of three states: DONE when the target is closed, READY when it is open and none of its blockers is open, and NOT READY when it is open and at least one blocker is not closed. A DONE target MUST NOT be reported as READY or NOT READY. A NOT READY result MUST name every blocker that is not closed as a `<tenant>:<id>` reference, and MUST NOT name a closed target or a target linked only by a non-blocking edge.

In `SPECIFICATION/scenarios.md`, add this scenario immediately after "## Scenario: a closed radar entry is reported as done and does not stall its consumers":

## Scenario: a blocked radar target names each open blocker by tenant and id

Given item `livespec-dev-tooling-i1` has a `blocks` edge to the open item `livespec-dev-tooling-j1` and a `blocks` edge to the closed item `livespec-dev-tooling-j2`

And `livespec-dev-tooling-i1` is listed on the radar with `blocked_by` `livespec:livespec-k1`, which is open, and a `relates-to` edge to the open item `livespec-dev-tooling-j3`

And `livespec-dev-tooling-c1` is listed on the radar and is closed

When readiness is computed for `livespec-dev-tooling-i1` and for `livespec-dev-tooling-c1`

Then `livespec-dev-tooling-i1` MUST be NOT READY

And its blockers MUST be exactly `livespec-dev-tooling:livespec-dev-tooling-j1` and `livespec:livespec-k1`

And `livespec-dev-tooling-c1` MUST be DONE, and MUST NOT be reported as READY or NOT READY

The new H2 heading needs a `tests/heading-coverage.json` row in the revise commit. It is a spec-first `TODO` row, registered in the debt register, whose reason names the unit tier and work item livespec-dev-tooling-m2x5pt as the owner of the owed test.
