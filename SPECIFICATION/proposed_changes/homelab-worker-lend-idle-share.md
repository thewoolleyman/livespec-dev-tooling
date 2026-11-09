---
topic: homelab-worker-lend-idle-share
author: claude:homelab-k8s-worker-nodes
created_at: 2026-11-09T15:26:08Z
---

## Proposal: A container worker's CPU is split evenly among the classes it is enrolled in

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Amends non-functional-requirements.md §"Homelab worker nodes", bullet **Derived per-class capacity**, and its scenario. Today the default gives each eligible class one third of the worker's allocatable CPU. The amendment gives each class the worker is ENROLLED in an equal share: one third each for three classes, one half each for two, and all of it for one. A class whose images do not publish the worker's architecture is not enrolled, so its share is lent to the enrolled classes and not left idle. Rounding down, the at-least-one-unit floor and the churn-slot rule for the CI share are unchanged.

### Motivation

Ruling relayed by legacy-coordinator-agent at 2026-11-09 08:38Z on plan epic livespec-dev-tooling-ko26ez: "a workload share with no workload enrolled is lent to CI and gate, never left idle." The maintainer then asked whether macbook-m4-max-homelab-worker takes full cluster load. The coordinator measured it at 15:2xZ: 12 CPU allocatable, 100m requested, no workload pods running. Under the one-third default, the 12-CPU worker gets 4000m per class: 1 churn slot and 1 gate. The factory third (4000m) is unused because the factory class does not yet declare arm64. Under this amendment, while the factory is unenrolled, CI and gate get 6000m each: 2 churn slots (5.46 CPU) and 1 gate (5 CPU / 8 Gi), so 10.46 of 12 CPU is admissible. Once the factory enrolls, the split returns to 4000m each. The cluster has run these lending values since 2026-11-09 09:16Z. They were applied from a branch that was never pushed, so the ratified text and the committed enrollment script must be brought to match them.

### Proposed Changes

In non-functional-requirements.md §"Homelab worker nodes", in the bullet **Derived per-class capacity**, replace the sentence

> Absent a measured split, the default MUST give each eligible class one third of the worker's allocatable CPU, rounded down and at least one unit, with CI capacity expressed in churn slots by that rule.

with

> Absent a measured split, the default MUST divide the worker's allocatable CPU equally among the classes the worker is enrolled in, rounded down and at least one unit for each, with CI capacity expressed in churn slots by that rule: one third each when it is enrolled in all three classes, one half each for two, and all of it for one. A class the worker is not enrolled in, because its images do not publish the worker's architecture, MUST NOT hold a share: its share is lent to the enrolled classes rather than left idle, and when that class later enrolls the shares are re-derived in the same enrollment.

In scenarios.md, replace the body of `## Scenario: a worker's per-class capacity is derived from its allocatable resources` (keeping the heading) with:

```
Given a joined worker whose node reports its allocatable CPU and memory, and no measured split

When enrollment derives its per-class capacity

Then each class the worker is enrolled in MUST receive an equal share of the allocatable CPU, rounded down and at least one unit

And a class the worker is not enrolled in MUST receive no share, its share being divided among the enrolled classes

And the CI share MUST be expressed in churn slots by the fleet's churn-slot sizing rule
```

No H2 heading is added, renamed or removed. The scenario's tests/heading-coverage.json entry is today a TODO owned by livespec-dev-tooling-ko26ez.7. The change that implements this amendment maps it to the stub test in tests/spec/test_homelab_worker_enroll.py that runs the real enroll-workload-classes.sh against mocked node resources with two enrolled classes, and regenerates the debt register.
