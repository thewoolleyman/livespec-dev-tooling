---
topic: livespec-orchestrator-k3s-and-livespec
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T13:44:17Z
---

## Proposal: A repository ceiling that departs from the pool rule is a recorded exception the pool's ceiling check reads from the derivation

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

In non-functional-requirements.md section "Adaptive JIT runner admission budget", appends to the paragraph that bounds each repository's logical ceiling to a small multiple of its fair share. A ceiling that departs from the recorded multiple and floor MUST be an exception row in the pool's admission derivation, naming the repository, its ceiling, the reason, the acceptance check that shows the exception still earns its place, and the kill switch that returns it to the rule. An exception's ceiling MUST stay above the repository's guaranteed share. The pool's ceiling check MUST read the exception set from the derivation, never from a copy, and MUST fail on a departure no row records. Adds one scenario to scenarios.md.

### Motivation

Work item livespec-dev-tooling-2aelab (plan ci-runtime-and-cost) raises livespec-orchestrator-k3s to maxRunners 24 and livespec-runtime-k3s to maxRunners 10. Their jobs stopped queueing at the rule ceiling while cohort slots sat free. It records the two values as exceptions in the pool's DERIVATION.md, and makes the test suite read that exception set instead of a hard-coded copy. On 2026-11-12 at 13:26Z the dispatcher refused it at spec-change tier on this topic (hold reason unratified-topic, spec v204, generalization target "## Adaptive JIT runner admission budget"). The judgement found that the section bounds each ceiling to a small multiple of fair share and puts the multiple and any floor in the pool's admission derivation. It found unstated that a departure from that rule is a recorded exception row with an acceptance check and a kill switch, and that the check reads the exception set from the derivation rather than pinning capacity values. It did not count the specific values 24 and 10, which are configuration. This proposal states that rule and leaves the values in the derivation, as the section already does for the multiple and floor.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Adaptive JIT runner admission budget", insert the following sentences immediately after "Maintainer-directed 2026-09-06." (the sentence that follows "are pool facts recorded with the pool's admission derivation, never here."), so the new rule does not inherit that dated maintainer attribution:

A repository whose logical ceiling departs from that multiple and floor MUST be listed as an exception row in the pool's admission derivation, naming the repository, its ceiling, the reason, the acceptance check that shows the exception still earns its place, and the kill switch that returns the repository to the rule. An exception's ceiling MUST stay above that repository's guaranteed share, and it remains subject to the bound this section places on every logical ceiling and to the physical host-wide cap. The pool's ceiling check MUST read the exception set from that derivation, never from a copy of its values, and MUST fail, naming the repository and its ceiling, when a repository departs from the rule without an exception row, when an exception row's ceiling is not above that repository's guaranteed share, or when an exception row names no acceptance check or no kill switch.

In SPECIFICATION/scenarios.md, insert the following scenario immediately after the scenario "## Scenario: JIT fleet capacity borrows fairly without exceeding 482 runners":

## Scenario: a runner ceiling that departs from the pool rule without a recorded exception fails the pool's ceiling check

Given the pool's admission derivation records the rule's multiple and floor and an exceptions table

And a repository's scale set whose maxRunners departs from that rule

And no exception row names that repository

When the pool's ceiling check runs

Then it MUST fail naming that repository and its maxRunners

And it MUST pass once an exception row names that repository with a ceiling above its guaranteed share, an acceptance check and a kill switch
