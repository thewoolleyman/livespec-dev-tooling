---
topic: the-fleet-ci-runner-pool
author: claude-sonnet-5-5
created_at: 2026-11-18T08:50:59Z
---

## Proposal: The cohort churn-slot budget is checked per flavor, and a worker flavor never counts toward the fleet's sum

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State that the cohort churn-slot sum rule applies per Kueue flavor: the members listed on the fleet's churn-slot flavor sum to the pool node profiles' declared admission capacity, and each worker flavor's members carry a borrowingLimit of 0 and a quota equal to the enrolled workers' derived churn slots, so a worker-flavor member never counts toward the fleet sum. Add one scenario for the worker-flavor member, and read the existing sum scenario as a statement about the fleet's flavor.

### Motivation

Measured on poweredge-xubuntu at 2026-11-14T07:05:14Z: summed across all flavors the live fleet-ci-runner-pool cohort carried 31 churn slots, not the 30 the derivation record and the budget test describe. The extra 1 is the livespec-dev-tooling-arm64-cq ClusterQueue, committed on its own worker flavor churn-slot-worker-arm64-flavor with borrowingLimit 0. Kueue lends per flavor, so the fleet's 30 is unaffected, but the ratified text says the cohort quota is the total across the cohort and also says a worker's churn slots are a separate flavor, which cannot both hold for a per-cohort total. The budget test reads only the fleet flavor's ClusterQueue manifests, so a worker-flavor member is invisible to it. Work item livespec-dev-tooling-i3w3gt owns the implementation and is held until this topic is ratified.

### Proposed Changes

1. In non-functional-requirements.md, in the paragraph beginning "Admission capacity sums to the cohort quota.", replace the first sentence with: "The cohort churn-slot quota is checked per Kueue flavor. The total `ci-runner.io/churn-slot` nominal quota the Kueue ClusterQueues of the runner pool's cohort admit CI runner pods against on the fleet's churn-slot flavor MUST equal the sum of every pool node profile's declared admission capacity. Each worker flavor's members MUST carry a `borrowingLimit` of 0 and a nominal quota equal to the enrolled workers' derived churn slots, and a worker-flavor member MUST NOT count toward the fleet flavor's sum." Keep the second sentence unchanged.

2. In scenarios.md, under "## Scenario: the cohort churn-slot quota equals the sum of the nodes' declared capacities" (heading text unchanged), change the Then step to: "Then the sum of the churn-slot nominal quota of the ClusterQueue members listed on the fleet's churn-slot flavor MUST equal the sum of every pool node profile's `ADMISSION_CAPACITY_C`".

3. In scenarios.md, add after it: "## Scenario: a worker-flavor ClusterQueue member is checked on its own flavor and never counts toward the fleet's sum" with Given a committed ClusterQueue member of the runner pool's cohort on a worker flavor; When the cohort budget check reads every committed ClusterQueue of the cohort, including those under `kueue/worker/`; Then it MUST group each member's churn-slot nominal quota by flavor, MUST require each worker-flavor member to carry a `borrowingLimit` of 0 and the enrolled workers' derived quota, and MUST NOT add that member to the fleet flavor's sum; And a member moved from a worker flavor onto the fleet's flavor MUST make the fleet flavor's sum check fail, naming the member and both flavor totals.
