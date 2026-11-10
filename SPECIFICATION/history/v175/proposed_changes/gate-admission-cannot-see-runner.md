---
topic: gate-admission-cannot-see-runner
author: claude:dev-host-test-gate-load
created_at: 2026-11-08T15:38:48Z
---

## Proposal: Gate Job placement follows measured node CPU pressure

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a "Placement by node pressure" bullet to contracts.md §"Delegated pre-push gate". It states that a pressure reconciler steers which gate lane a newly submitted gate Job is admitted on, from measured node CPU readings and with a fail-safe back to the static lane order. Add three scenarios to scenarios.md stating the behaviour. This is design C, which the maintainer chose on 2026-11-08.

### Motivation

Work item livespec-dev-tooling-gvo7fa. gates-cq admits gate Jobs with topology-aware admission, which subtracts only the CPU REQUESTS of pods Kueue does not manage. CI runner pods request no CPU (they request only ci-runner.io/churn-slot), so on every pool node runner load is invisible to gate admission. A node that runners saturate reads as free, and an admitted gate's 5-CPU request then takes CPU from those runners by CFS weight. Measured 2026-11-07 21:09Z: gmktec-xubuntu, tried first, was 0% idle with CI-slice CPU pressure avg60 52, while poweredge-xubuntu was 18.6% idle with pressure 0.06. The same-day stop-the-line change only reordered the static lane list, and a static order does not follow load as it moves. Three designs were offered: A, a static flavor order; B, giving runner pods a CPU request; C, a pressure reconciler steering gate admission from measured readings, modelled on ci-runner/k3s/phase2/factory-pressure-placement/reconcile-factory-pressure-taint.sh. The maintainer ruled on 2026-11-08, verbatim: "3b - go with recommended c" (recorded as a scope event on plan epic livespec-dev-tooling-6vuiwe). B is not chosen: any runner CPU request belongs to the separately adopted temporary factory-vs-CI CPU share (livespec-dev-tooling#3799, plan epic livespec-dev-tooling-me5aqz), which adds only the ci-runner.io/factory-admit node label and a factory nodeSelector entry. This proposal aligns with the in-flight spec/homelab-worker-live-load proposal, which enrolls each joined worker in the gate-job class with no per-host step. The ci_pool coverage clause below is the gate-placement side of that same rule.

### Proposed Changes

In `contracts.md` §"Delegated pre-push gate", insert the following bullet immediately after the **Admission wait.** bullet:

- **Placement by node pressure.** The self-hosted pool MUST run a gate placement reconciler that steers which gate lane of the `gates` ClusterQueue admits a newly submitted gate Job, from measured node CPU readings. On every pass it MUST read, for each node that carries a gate lane, the node's CPU idle share and the CPU pressure (`cpu.pressure` `some` avg60) of the BestEffort slice that holds the CI runner pods (`kubepods.slice/kubepods-besteffort.slice`). It MUST classify a node as saturated when its CPU idle is under 5% and that slice pressure avg60 is above 30, which is the pool's node-saturation rule. The node-level PSI that `ci-runner/k3s/phase2/factory-pressure-placement/publish-node-cpu-pressure.sh` publishes for factory placement is a different reading and MUST NOT stand in for the CI slice's pressure; the reconciler MAY reuse that script's publishing pattern and its never-a-false-zero rule for its own readings. While at least one gate-lane node is saturated and at least one is not, a newly submitted gate Job MUST be admitted on the lane of a node that is not saturated. While every gate-lane node is saturated, a newly submitted gate Job MUST still be admitted on some lane with room, so saturation alone MUST NOT leave the gate queue with no lane. The lever the reconciler moves MAY be the gate flavor order, a gate lane's quota, or a node taint the gate Job template does not tolerate; the implementation chooses. Each change the reconciler makes to gate admission MUST be logged with the node readings that caused it. When the reconciler cannot read a gate-lane node's readings, gate admission MUST fall back to the static lane order, and the reconciler MUST log the node and the reading it could not take; it MUST NOT treat an unread reading as either saturated or free. A node that joins the `ci_pool` inventory group MUST be covered by the reconciler without a per-node edit to the reconciler. The reconciler MUST NOT set a CPU request on CI runner pods, and it MUST NOT read or write the `ci-runner.io/factory-admit` node label, which belongs to the factory-vs-CI CPU share. This placement MUST NOT add a WorkloadPriorityClass: `gate-priority` stays the only class `gates` admits under. This bullet binds every gate Job the gate client submits, so it covers §"Delegated commit-time replay test runs", §"Delegated pre-commit aggregate" and §"Delegated gate-runner runs" as well as this section. It is spec-first: as of its ratification the shipped pool places gate Jobs by a static lane order, and work item livespec-dev-tooling-gvo7fa owns the change.

In `scenarios.md`, add the following three scenarios after `## Scenario: a seat's gate-runner full suite runs as a gate Job by default`:

## Scenario: a gate Job submitted while one gate lane's node is saturated is admitted on an unsaturated lane

Given two nodes that each carry a gate lane of the `gates` ClusterQueue
And the first node's CPU idle is under 5% and its CI pod slice's CPU pressure avg60 is above 30
And the second node's CPU idle is above 5%
When the gate placement reconciler completes a pass and a gate Job is then submitted
Then the gate Job MUST be admitted on the second node's lane
And the reconciler's log MUST name the change it made and the readings of both nodes that caused it

## Scenario: a gate Job submitted while every gate lane's node is saturated is still admitted

Given every node that carries a gate lane reads saturated by the placement rule
And at least one gate lane has room
When the gate placement reconciler completes a pass and a gate Job is then submitted
Then the gate Job MUST be admitted on a lane with room
And the gate Job MUST NOT stay suspended for want of an unsaturated lane

## Scenario: a gate placement reconciler that cannot read a node's readings falls back to the static lane order

Given a node that carries a gate lane whose CPU idle share cannot be read
When the gate placement reconciler completes a pass
Then gate admission MUST use the static lane order
And the reconciler's log MUST name the node and the reading it could not take

