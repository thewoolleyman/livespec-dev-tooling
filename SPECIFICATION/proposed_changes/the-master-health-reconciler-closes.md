---
topic: the-master-health-reconciler-closes
author: claude-opus-5-5 (seat red-master-self-healing)
created_at: 2026-11-14T06:20:00Z
---

## Proposal: The master-health reconciler closes as superseded only a revert it opened, and leaves any other revert open

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Narrow the "closed as superseded" rule in contracts.md section "Master-health reconciler" so it applies only to a revert the reconciler itself opened for a red episode it recorded. A revert pull request that the reconciler did not open is left alone on a green `master`. Examples are a server-side revert made by hand or by another seat, including one for a breakage that GitHub CI cannot see. The reconciler does not close, release or merge such a revert, and its step reason names the revert pull request and says why it was left open. This is the behaviour livespec-dev-tooling-7uq5ri implements (plan red-master-self-healing, epic livespec-dev-tooling-zcp5vb).

### Motivation

Observed 2026-11-02 in livespec. #3053 merged as 4172bbc6 and GitHub CI stayed green, because GitHub runners do not set LIVESPEC_GATE_CONTEXT. Every cluster gate Job went red: the post-merge janitor gate failed check-per-file-coverage on four tests that inherit that variable. A seat opened server-side revert #3055, as ci-gate-discipline prescribes. Fifteen seconds after its auto-merge was armed, the reconciler closed it with its close-revert step reason: "a later non-revert commit turned the branch green; this held revert is superseded". The reconciler judges branch health from GitHub CI alone, so a revert of a breakage that only cluster gate Jobs see always reads as superseded and is closed at once. The revert path is therefore dead for exactly the class of breakage the delegated gates introduced.

The ratified clause says "a held revert MUST be closed as superseded". "Held" reads as the reconciler's own revert, which it opens with auto-merge held, but the section never says what happens to a revert it did not open, and the shipped reconciler closes any revert it finds. On 2026-11-14 the dispatcher refused livespec-dev-tooling-7uq5ri at the spec-change tier for this reason: the spec-stated judgement found the behaviour partial and named "## Master-health reconciler" as the heading to generalize. The narrow rule needs no cluster-gate data, and it cannot close a revert for a reason the reconciler never measured. The broader alternative, requiring a green cluster gate Job before declaring any revert superseded, is not proposed here.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Master-health reconciler", paragraph **Culprit and revert.**, replace the sentence:

> Once a later non-revert `master` commit is green, a held revert MUST be closed as superseded, not released.

with:

> Once a later non-revert `master` commit is green, a held revert that the reconciler itself opened for a red episode it recorded MUST be closed as superseded, not released. A revert pull request that the reconciler did not open — for example a server-side revert opened by hand or by another seat, including one for a breakage that GitHub CI does not see — MUST be left open when `master` is green: the reconciler MUST NOT close, release, or merge it, and the step reason of that reconcile run MUST name that revert pull request and state that it was left open because the reconciler did not open it.

In SPECIFICATION/scenarios.md, insert the following two scenarios directly after "## Scenario: an unclaimed revert is released as soon as its own CI is green". Each is a new `## ` heading, so the revise co-edits tests/heading-coverage.json with an entry for each, owned by livespec-dev-tooling-7uq5ri at the unit tier or above, and regenerates tests/heading-coverage-debt.json:

## Scenario: a held revert the reconciler opened is closed as superseded once master turns green

Given a held revert pull request that the master-health reconciler opened for a red episode it recorded

And a later non-revert `master` commit whose GitHub CI is green

When the reconcile run takes its next step

Then it closes that revert pull request as superseded and does not release it

## Scenario: a revert the reconciler did not open is left open on a green master

Given a revert pull request that the master-health reconciler did not open, such as a server-side revert opened by hand for a breakage GitHub CI does not see

And a `master` whose latest GitHub CI verdict is green

When the reconcile run takes its next step

Then it MUST NOT close, release, or merge that revert pull request

And its step reason names that revert pull request and states that it was left open because the reconciler did not open it
