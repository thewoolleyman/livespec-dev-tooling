---
topic: homelab-worker-ci-overflows-to
author: claude:homelab-k8s-worker-nodes
created_at: 2026-11-10T03:32:24Z
---

## Proposal: A container worker's CI capacity is an overflow flavor tried after the fleet's own, never a pinned lane

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Amends non-functional-requirements.md §"Homelab worker nodes", bullet **Live production load**, to say HOW a container worker takes CI load from the existing queues. Each eligible repository's CI ClusterQueue lists a worker churn-slot flavor for the worker's architecture AFTER the fleet's own churn-slot flavor, so a runner pod is admitted onto the worker only when the fleet flavor cannot fit it, including by borrowing from the cohort. The queues keep flavor fungibility that stops at a flavor the workload can borrow on, and preemption Never, so a workload never preempts or prefers the worker. No repository's CI lane is pinned to a worker by a repository variable or a dedicated runner label. The worker flavor's quota is the enrolled workers' derived churn slots, sized from the worker's measured CI job throughput with its gate and factory load counted. A new scenario states the overflow.

### Motivation

From 07:43Z to 21:23Z on 2026-11-09, livespec-dev-tooling's Python and coverage CI was pinned to the M4 worker's host-unique arm64 scale set through repository variables. When v168 brought the factory class into the worker's split, its CI share fell to one churn slot, and that lane queued 16 deep while the 18-slot amd64 set sat idle. legacy-coordinator-agent moved the variables back to amd64, and since then the worker takes no CI at all, so the plan's live-load window cannot start. Measured on the live cluster on 2026-11-10: the fleet CI ClusterQueues carry flavorFungibility {whenCanBorrow: MayStopSearch, whenCanPreempt: TryNextFlavor} and preemption Never, so a second flavor is reached only when the first cannot fit even by borrowing. That is overflow, the intended semantics. The ratified text says the worker takes CI from the existing queues but not the flavor order, the overflow-only admission, the fungibility setting or the throughput sizing. legacy-coordinator-agent's tier record (2026-11-10 03:28Z, work item livespec-dev-tooling-eorpen) holds that those are behaviour and need ratification before the change lands.

### Proposed Changes

In non-functional-requirements.md §"Homelab worker nodes", append to the bullet **Live production load**, after its existing two sentences:

> For CI, a worker's churn slots MUST be offered as a churn-slot flavor for the worker's architecture that each eligible repository's CI ClusterQueue lists AFTER the fleet's own churn-slot flavor, and the fleet's flavor MUST NOT match a container worker. An eligible repository is one whose every CI job image publishes the worker's architecture. A runner pod MUST be admitted onto the worker only when the fleet's flavor cannot fit it, by its own quota or by borrowing within its cohort. To that end the queues' flavor fungibility MUST stop at a flavor the workload can borrow on, and their preemption MUST be Never, so that no workload preempts another to reach the worker or prefers the worker over fleet capacity. No repository's CI lane MAY be pinned to a worker through a repository variable or a dedicated runner label. The worker flavor's quota MUST be the enrolled workers' derived churn slots, sized from the worker's measured CI job throughput with its gate and factory load counted, and recorded as decided.

In scenarios.md, add:

```
## Scenario: CI overflows onto a container worker only when fleet capacity is full

Given an enrolled arm64 container worker with derived churn slots

And a repository whose every CI job image publishes arm64

When that repository's runner pod is admitted while its fleet churn-slot capacity, including what it can borrow, is free

Then the pod MUST be placed on a fleet node and not on the worker

And when the fleet's churn-slot capacity is full, the next such pod MUST be admitted onto the worker's flavor without preempting any workload

And a pod of a repository with an amd64-only CI image MUST NOT be admitted onto the worker
```

The new scenario adds an H2 heading, so the revise commit adds its tests/heading-coverage.json entry. It is a spec-first TODO naming livespec-dev-tooling-eorpen, at the integration tier, registered in the debt register.
