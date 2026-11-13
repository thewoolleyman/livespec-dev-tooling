---
topic: runner-placement-post-add-tie
author: claude-opus-5-5
created_at: 2026-11-13T07:11:46Z
---

## Proposal: Runner placement is ordered by the post-placement churn-slot score, and equal integer scores may go to either node

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

MODIFY the ratified paragraph "Runner placement follows admission capacity" (non-functional-requirements.md, ## Runner-pool node rebuild recipe) so the placement preference is stated exactly as the committed scheduler profile computes it. The profile is NodeResourcesFit LeastAllocated over `ci-runner.io/churn-slot` only, and it scores each candidate node AFTER counting the incoming pod on it, as the integer floor((cap - used - 1) * 100 / cap). The higher score MUST win, and EQUAL integer scores MAY receive the pod in either order. MODIFY the body of the scenario "a runner pod is placed on the node with the lowest churn-slot use, whatever its CPU and memory requests" to the same post-placement score, keeping its heading and its CPU/memory point. ADD one scenario for the observed tie between two nodes that are each on their last free churn slot.

### Motivation

The ratified text says a runner pod MUST be placed "preferring the node with the lowest fraction, among the nodes that have a free churn slot", and its scenario says "Then it MUST be placed on node A" whenever node A's fraction in use is lower. The committed profile does not compute that pre-placement fraction.

kube-scheduler's LeastAllocated strategy scores a node as ((capacity - requested) * 100) / capacity in integer arithmetic, where requested already includes the incoming pod's request. With churn-slot as the only scored resource, a node's score is floor((cap - used - 1) * 100 / cap). Two consequences follow:
(1) Every node on its last free slot scores 0, so such nodes tie whatever their fractions in use.
(2) Nodes of different capacity can rank in the opposite order to their pre-placement fractions. gmktec-xubuntu at 7 of 8 scores 0, while poweredge-xubuntu at 15 of 17 scores 5, so poweredge is chosen although gmktec's fraction in use (0.875) is lower than poweredge's (0.882).

The independent replay of livespec-dev-tooling-mtvxde on 2026-11-13 (codex session 01a1d3ab, build v1.204.0, 600 s of read-only pod and PVC watches) observed the tie. 15 of 16 qualifying placements chose gmktec-xubuntu. The one exception went to poweredge-xubuntu while gmktec-xubuntu was at 7 of 8 and poweredge-xubuntu at 16 of 17, both scoring 0. The scheduler behaved exactly as configured. The ratified wording promises a strict lowest-fraction preference the realization cannot give.

legacy-coordinator-agent ruled (2026-11-13) that a custom score plugin to honour the strict wording is not worth its weight, and directed that the clause state the rule exactly as the profile computes it. The other enabled default score plugins (TaintToleration, NodeAffinity, PodTopologySpread, InterPodAffinity) do not tell pool nodes apart for a runner pod today: runner pods carry no preferred affinity and no spread constraint, and they tolerate the only PreferNoSchedule taint the pool uses. Every graded decision in the replay was consistent with the churn-slot score alone.

Revise-time co-edit owed: tests/heading-coverage.json needs a new row for the added scenario heading. It is a spec-first "test": "TODO" whose reason names a real test owed at the integration tier (a host-captured placement run on the k3s pool), with "work_item": "livespec-dev-tooling-mtvxde", followed by `just generate-heading-coverage-debt-register` with tests/heading-coverage-debt.json staged. The modified scenario keeps its heading text exactly, so its existing row (already a TODO owned by livespec-dev-tooling-mtvxde) is unchanged, and no H2 heading is removed. mtvxde's Definition of Done bullet about gmktec placement is re-captured against the ratified text after the revise.

### Proposed Changes

### SPECIFICATION/non-functional-requirements.md, ## Runner-pool node rebuild recipe

In the paragraph that begins "**Runner placement follows admission capacity.**", replace its first sentence:

> A CI runner pod that requests a `ci-runner.io/churn-slot` MUST be placed on a node by the fraction of that node's declared `ci-runner.io/churn-slot` capacity already in use, preferring the node with the lowest fraction, among the nodes that have a free churn slot.

with:

> A CI runner pod that requests a `ci-runner.io/churn-slot` MUST be placed on one of the nodes that have a free churn slot, chosen by each such node's post-placement churn-slot score: the integer floor((cap - used - 1) * 100 / cap), where cap is the node's declared `ci-runner.io/churn-slot` capacity, used is the number of its churn slots already in use before this pod is placed, and the "- 1" is the incoming pod's request, which holds because a CI runner pod requests exactly one churn slot. The node with the higher score MUST be chosen. Nodes whose integer scores are equal MAY receive the pod in either order. Because the score counts the incoming pod and is rounded down, every node on its last free churn slot scores 0 and those nodes tie, and a node whose fraction in use is lower MAY rank below a node of different capacity whose fraction in use is higher (8 slots with 7 in use scores 0; 17 slots with 15 in use scores 5).

Every other sentence of the paragraph MUST stay as it is, from "The CPU and memory requests of pods that are not CI runner pods ..." to its end.

### SPECIFICATION/scenarios.md

Keep the heading "## Scenario: a runner pod is placed on the node with the lowest churn-slot use, whatever its CPU and memory requests" byte-for-byte, and replace its body with:

```gherkin
Given two pool nodes that both carry the `k3s-role=arc-runner-host` label and no CI-closing taint, and each has at least one free churn slot
And node A's post-placement churn-slot score, floor((cap - used - 1) * 100 / cap), is higher than node B's
And node A's requested CPU and memory fractions from non-runner pods are both higher than node B's

When a new CI runner pod is admitted

Then it MUST be placed on node A
```

Add this scenario immediately after it:

```gherkin
## Scenario: a runner pod may go to either node when their post-placement churn-slot scores are equal

Given two pool nodes that both carry the `k3s-role=arc-runner-host` label and no CI-closing taint
And node A declares 8 churn slots with 7 in use, and node B declares 17 churn slots with 16 in use, so each has exactly one free churn slot
And each node's post-placement churn-slot score, floor((cap - used - 1) * 100 / cap), is 0

When a new CI runner pod is admitted

Then it MUST be placed on node A or on node B
And its placement MUST NOT be judged against the two nodes' pre-placement fractions in use
```

The gherkin fences above are presentation only. Both scenarios MUST be written unfenced in scenarios.md, in the same plain Given/When/Then line style as the scenarios around them.
