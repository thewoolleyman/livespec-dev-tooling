---
topic: runner-placement-follows-churn-slot-capacity
author: claude-opus-5-5 (session kubernetes-sandbox-backend)
created_at: 2026-11-04T07:14:58Z
---

## Proposal: Runner placement follows each node's free churn slots

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a **Runner placement follows admission capacity** clause to §"Runner-pool node rebuild recipe", with a matching scenario. A CI runner pod MUST be placed by the fraction of each node's declared `ci-runner.io/churn-slot` capacity in use, not by the CPU and memory requests of non-CI pods on the node. The placement rule MUST apply to runner pods only.

### Motivation

Measured 2026-11-04 (livespec-dev-tooling-mtvxde): gmktec-xubuntu declares 12 churn slots, carries no taint, and was 54-58% idle, yet received zero ARC runner pods all morning. The default kube-scheduler scores a node by its requested CPU and memory fraction. Runner pods request only a churn slot, and gmktec's requests were 94% held by factory sandboxes and a gate whose actual use is far lower. So gmktec ranked last for every runner and got one only after poweredge-xubuntu's and hp-xubuntu's slots filled, while poweredge ran at PSI60 55. Today the specification fixes how much capacity each node declares (**CI-facilities posture**, **Admission capacity sums to the cohort quota**) but says nothing about how runners are spread across that capacity. A node's declared slots can therefore go unused by construction, which defeats the per-node derivation those clauses require.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe", insert after the **Admission capacity sums to the cohort quota.** paragraph:

**Runner placement follows admission capacity.** A CI runner pod MUST be placed on a node by the fraction of that node's declared `ci-runner.io/churn-slot` capacity already in use, preferring the node with the lowest fraction, among the nodes that have a free churn slot. The CPU and memory requests of pods that are not CI runner pods (factory sandboxes, gate jobs, cache singletons) MUST NOT decide which of those nodes a runner pod is placed on. This rule MUST be realized by a scheduler profile that the runner pods select by name, committed in this tree and applied by the CI stack converge. The cluster's default scheduler profile MUST stay unchanged, so every other pod is placed exactly as before. A node's declared churn-slot capacity MUST stay the only per-node limit on how many runner pods it holds.

In `SPECIFICATION/scenarios.md`, add (and add its `tests/heading-coverage.json` entry with `test: "TODO"` and `work_item: "livespec-dev-tooling-mtvxde"`):

## Scenario: a runner pod is placed on the node with the lowest churn-slot use, whatever its CPU requests

Given two pool nodes that both carry the runner-host label and no CI-closing taint
And node A has a lower fraction of its declared churn-slot capacity in use than node B, and at least one free churn slot
And node A's requested CPU fraction from non-runner pods is higher than node B's

When a new CI runner pod is admitted

Then it MUST be placed on node A
And a pod that is not a CI runner pod MUST still be placed by the default scheduler profile
