---
topic: factory-budget-admission-counts-memory
author: claude-opus-5-5
created_at: 2026-11-12T08:21:21Z
---

## Proposal: Factory budget admission labels a node factory-admit only when it can place a factory sandbox pod

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

State the factory budget admission rule as a spec clause. On every node labelled ci-runner.io/factory=true, ci-runner.io/factory-admit=true means a factory sandbox pod can be placed there: the node's factory pod count is below its budget (the CPU share) AND its unrequested allocatable memory is at least the factory sandbox pod's memory request. Each memory closing is logged, and the existing overflow, kill-switch and fail-safe behaviour is kept. The interim control stays temporary under the 2026-11-08 maintainer ruling. Three scenarios and the heading-coverage entries ship in the same change. When every factory node is closed by memory, the overflow node is logged as OVERFLOW-NO-MEMORY, and the fleet launch cap (derive-the-dispatcher-s-fleet) is named as what prevents dispatch into it.

### Motivation

Today the spec names ci-runner.io/factory-admit only in passing, as the label that "belongs to the factory-vs-CI CPU share" (contracts.md §"Delegated pre-push gate"), and the shipped reconciler admits on pod count alone. So admit=true can name a node with no room for the pod. Measured 2026-11-12: bd-ib-ax6bxj (run 01M776D67XCM, pod petri-01m776d67xcmxx8zcckdgge6t3-l0, about 06:17-06:27Z) failed sandbox start at the driver's 600 s pod-schedule bound with FailedScheduling "0/5 nodes are available: 1 Insufficient memory, ...", while the reconcile-factory-budget-admit journal read gmktec-xubuntu count=6 budget=7 admit=true. A pod the gate admits but the scheduler cannot place waits out the start timeout and fails as an infrastructure failure. legacy-coordinator-agent (session c8c6cc4b) ruled the clause must come first: it will not approve the implementation items bd-ib-crleeu (orchestrator anchor, plan bd-ib-nmuyjc) and livespec-dev-tooling-uvxmn7 (execution mirror) against a clause that does not state the behaviour. The fix is also the coordinator's end condition (a) for any fleet-cap raise above 19. This proposal aligns with the pending derive-the-dispatcher-s-fleet proposal, which bounds the sum of the run caps by the sum of the factory pod budgets. It does not conflict, because that proposal sizes the caps while this one makes each admitted slot real.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, insert this new section directly before `## Docker engine install guard` (so it follows §"Fabro factory registry"):

## Factory budget admission

**Scope.** The factory budget admission reconciler, `ci-runner/k3s/phase2/factory-budget-admission/reconcile-factory-budget-admit.sh`, is installed by the `factory_budget_reconciler` role and runs on the k3s server about every 30 seconds. It sets the node label `ci-runner.io/factory-admit`, which the sandbox driver's node selector includes, so a NEW factory sandbox pod is placed only on a node labelled `true`. It gates first placement only; a sandbox's later pods follow the node it already uses. It is an interim control. The maintainer adopted the fixed factory-vs-CI CPU share on 2026-11-08 as "a temporary workaround to a better solution", and this section stays temporary under that ruling: the better solution remains a maintainer design item, and when it lands this section, the reconciler and its role are removed together.

**Admitted means placeable.** On each pass, for every node labelled `ci-runner.io/factory=true`, the reconciler MUST set `ci-runner.io/factory-admit=true` only when both of the following hold, and MUST set it `false` otherwise:

1. The node's factory sandbox pod count is below its factory pod budget, which is the CPU share. The count is every pod labelled `app.kubernetes.io/managed-by=sandbox-driver-kubernetes` bound to the node, in any namespace, excluding the driver's cleanup pods and pods in phase `Succeeded` or `Failed`. A terminating pod still counts.
2. The node's unrequested memory is at least the factory sandbox pod memory request. A node's *unrequested memory* is its allocatable memory minus the memory requests of every pod bound to it that has not ended, in any namespace.

The *factory sandbox pod memory request* MUST be one committed value that the role renders for the reconciler. The role's `HOST_VARS.md` MUST document it beside `factory_pod_budget`, and it MUST equal the memory request the factory workflow declares for its sandbox pod. The reconciler MUST cover every factory node without a per-node edit to the reconciler.

**Each memory closing is logged.** When memory closes a node whose count is below its budget, the pass MUST log one line that names the node, its unrequested memory, and the pod memory request it was compared against.

**Overflow, the kill switch and a failed read keep their meaning.** When every factory node is closed by count or by memory, the reconciler MUST keep exactly one factory node admitted and MUST log a line beginning `OVERFLOW`, so that a first-placement pod always has an admitted node. That node MUST be chosen in this order: a node whose unrequested memory covers the pod memory request comes first, then the largest budget minus count, then the most unrequested memory, then the node name. When no factory node's unrequested memory covers the pod memory request, the node kept admitted cannot place a new factory sandbox pod, and a first-placement pod sent there waits out the sandbox driver's start timeout. In that case the line MUST begin `OVERFLOW-NO-MEMORY` and MUST name the admitted node, its unrequested memory and the pod memory request, so that the state is distinguishable from an overflow that still has a memory-fitting node. This reconciler does not prevent dispatch into that state. The fleet's launch cap does, and that bound is stated in §"Fabro factory registry", which the pending derive-the-dispatcher-s-fleet proposal amends to bound the committed run caps by the factory pod budgets. With `FACTORY_BUDGET_GATE=off`, a pass MUST set `ci-runner.io/factory-admit=true` on every factory node whatever its count or memory. When the budget file cannot be read, or a node or pod read fails, the pass MUST change no label and MUST exit non-zero.

This section is spec-first. As of its ratification the shipped reconciler admits on pod count alone, and work item livespec-dev-tooling-uvxmn7 owns the change.

In `SPECIFICATION/scenarios.md`, insert these three scenarios directly after `## Scenario: a factory node keeps its factory label across a control-plane reboot` (before `## Scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads`):

## Scenario: a factory node under its pod budget without memory for one more sandbox pod is not admitted

Given factory node `gmktec-xubuntu` has `factory_pod_budget` 7 and 6 factory sandbox pods bound, and its unrequested memory is below the factory sandbox pod memory request

And factory node `poweredge-xubuntu` has `factory_pod_budget` 11 and 10 factory sandbox pods bound, and its unrequested memory is at least the factory sandbox pod memory request

When the factory budget admission reconciler runs one pass

Then `gmktec-xubuntu` reads `ci-runner.io/factory-admit=false`

And the pass logs one line naming `gmktec-xubuntu`, its unrequested memory and the factory sandbox pod memory request

And `poweredge-xubuntu` reads `ci-runner.io/factory-admit=true`

## Scenario: every factory node closed by count or by memory keeps one node admitted and logs OVERFLOW

Given every factory node is either at its `factory_pod_budget` or has unrequested memory below the factory sandbox pod memory request

And exactly one of them, `poweredge-xubuntu`, has unrequested memory at least the factory sandbox pod memory request

When the factory budget admission reconciler runs one pass

Then `poweredge-xubuntu` reads `ci-runner.io/factory-admit=true`

And every other factory node reads `ci-runner.io/factory-admit=false`

And the pass logs a line beginning `OVERFLOW`

## Scenario: every factory node closed by memory keeps one node admitted and logs OVERFLOW-NO-MEMORY

Given every factory node has unrequested memory below the factory sandbox pod memory request

When the factory budget admission reconciler runs one pass

Then exactly one factory node reads `ci-runner.io/factory-admit=true`

And the pass logs a line beginning `OVERFLOW-NO-MEMORY` naming that node, its unrequested memory and the factory sandbox pod memory request

In `SPECIFICATION/contracts.md` §"Delegated pre-push gate", in the bullet that begins "- **Placement by node pressure.**", replace "which belongs to the factory-vs-CI CPU share" with "which belongs to factory budget admission (`non-functional-requirements.md` §"Factory budget admission")". The gate reconciler's prohibition on reading or writing the label is unchanged.

In `tests/heading-coverage.json`, add four entries in the same revise, each with `"test": "TODO"`, `"work_item": "livespec-dev-tooling-uvxmn7"` and a non-empty `reason` saying the clause is spec-first and livespec-dev-tooling-uvxmn7 owns the test: `non-functional-requirements.md` `## Factory budget admission`, and `scenarios.md` for each of the three new scenario headings.
