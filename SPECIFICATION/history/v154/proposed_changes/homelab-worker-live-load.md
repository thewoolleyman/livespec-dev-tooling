---
topic: homelab-worker-live-load
author: claude-opus-5-5
created_at: 2026-11-07T19:53:11Z
---

## Proposal: Container workers enroll automatically in every workload class their architecture can run, and carry live production load

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

A container worker that joins through the production join path is enrolled, with no per-host file or hand step, in each workload class (CI runner capacity, gate jobs, factory sandboxes) whose images publish its architecture; every class selects nodes by architecture from one declared list; the worker's per-class capacity is derived from its measured resources by the fleet's existing sizing rule; it takes work from the same queues as the existing nodes; and work placed on it survives its leaving without warning, after which it rejoins with no operator step.

### Motivation

Maintainer direction relayed by legacy-coordinator-agent on epic livespec-dev-tooling-ko26ez at 2026-11-07T19:22Z: the worker and every later container node must be automatically enrolled in the factory, gate and CI with the default taints, routing and load, and the plan's finish line is live production cluster load, not proof workflows. Measured the same day: macbook-m4-max-homelab-worker was Ready with its hold lifted and idle (46m CPU of 12) while gmktec-xubuntu read 99%; no class enrolls a new node automatically, because CI churn-slot capacity is set per bare-metal profile (ADMISSION_CAPACITY_C) and the k3s-role=arc-runner-host label is a provision-time flag, gate flavors pin kubernetes.io/hostname, factory providers exist only in one host's inventory, and the worker join script sets none of them. Every scale set, the gate job template and the factory provider also lack any architecture selection, while the fleet CI and gate image python-v1.183.0 and the factory python-agent layer are amd64-only and the worker is arm64. A laptop host sleeps and leaves without warning, and the worker's networking agents restarted 11 to 17 times in 38 hours. Relationship to in-flight work: this modifies the pending spec/homelab-factory-sandbox proposal (livespec-dev-tooling-a3brdf) to accommodate automatic enrollment, keeping its native arm64 python-agent layer but replacing its one-instance-per-worker, host-label selection with a provider that admits any enrolled worker of a published architecture, so the next worker needs no new instance; it aligns with the in-flight runner-placement proposal (livespec-dev-tooling#3718), whose churn-slot placement rule a worker's derived churn-slot capacity feeds unchanged.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md section "Homelab worker nodes", append these bullets after **Reviewed cluster changes.**:

- **Automatic enrollment by workload class.** The production join path MUST enroll each joined worker in every workload class the fleet runs (CI runner capacity, gate jobs and factory sandboxes) whose workload images publish the worker's architecture, through the same node labels, extended resources and queue admission the fleet's existing nodes carry for that class, with no per-host values file, profile, inventory entry or operator step beyond the join itself. Enrollment MUST take effect only once the admission hold is lifted. A class whose images do not publish the worker's architecture MUST NOT be scheduled on the worker, and the join MUST name each such class and the image it lacks in its output. The permanent worker class taint MAY stay; each class a worker is enrolled in MUST tolerate it.
- **Architecture by workload class.** Every CI runner scale set, the gate job template and every factory sandbox provider MUST select nodes by a `kubernetes.io/arch` value that its workload images publish, read from one declared per-class architecture list rather than from any per-host value. No workload MUST be scheduled onto a node whose architecture its image does not publish. The list MUST name which classes run on arm64 and, for each class that does not, the image it lacks.
- **Derived per-class capacity.** A worker's capacity in each enrolled class MUST be derived from its measured allocatable CPU and memory by one source of truth that reuses the fleet's churn-slot sizing rule. Absent a measured split, the default MUST give each eligible class one third of the worker's allocatable CPU, rounded down and at least one unit, with CI capacity expressed in churn slots by that rule. Tests MUST NOT pin a committed capacity value; they MUST assert the derivation rule against mocked node resources.
- **Live production load.** An enrolled worker MUST take work for each enrolled class from the same queues the fleet's existing nodes serve. A workflow addressed to the worker by name is a proof, not its load.
- **Departure and rejoin.** Work placed on a worker that leaves the cluster without warning MUST NOT be lost: its CI and gate jobs MUST be retried or re-queued onto another node, and a factory run on it MUST resume or be re-dispatched with its work preserved. When its host returns, the worker MUST rejoin and re-enroll with no operator step, and its host collector MUST NOT depend on a per-session unlock of a host credential store.

In the same section, the pending **Factory sandboxes on a worker** bullet proposed by spec/homelab-factory-sandbox, if revised, MUST select workers by the worker class label and architecture rather than by one host's label, so one provider per architecture admits every enrolled worker; its native arm64 `python-agent` layer requirements stand unchanged.

In SPECIFICATION/scenarios.md, add these scenarios after `## Scenario: the worker's node IP is its declared home-LAN address`:

## Scenario: a joined worker is enrolled in every workload class its architecture can run

Given an arm64 container worker joined through the production join path, a CI class whose job image publishes arm64, and a factory class whose sandbox image publishes only amd64

When the join completes and the admission hold is lifted

Then the worker MUST carry the CI class's node label and churn-slot capacity derived from its allocatable CPU, and the CI class's scale sets MUST tolerate the worker class taint

And the factory class MUST NOT be able to schedule onto the worker, and the join output MUST name the factory class and the arm64 image it lacks

And no per-host values file, profile or inventory entry MUST have changed

## Scenario: a workload is never scheduled onto a node whose architecture its image does not publish

Given a cluster with amd64 nodes and an arm64 worker enrolled in every class whose images publish arm64

When a CI job, a gate job and a factory sandbox whose images publish only amd64 are each admitted

Then each MUST be placed on an amd64 node

And none MUST be placed on the arm64 worker

## Scenario: a worker's per-class capacity is derived from its allocatable resources

Given a joined worker whose node reports its allocatable CPU and memory, and no measured split

When enrollment derives its per-class capacity

Then each eligible class MUST receive one third of the allocatable CPU, rounded down and at least one unit

And the CI share MUST be expressed in churn slots by the fleet's churn-slot sizing rule

## Scenario: a worker that leaves mid-run loses no work and rejoins on its own

Given an enrolled worker running a CI job, a gate job and a factory run

When the worker leaves the cluster without warning and its host later returns

Then the CI job and the gate job MUST be retried or re-queued onto another node, and the factory run MUST resume or be re-dispatched with its work preserved

And the worker MUST rejoin and re-enroll in the same classes with no operator step

In tests/heading-coverage.json, add one entry per new scenario heading with `test` set to `TODO`, a reason naming the integration tier or above as the tier the owed test runs at, and `work_item` set to livespec-dev-tooling-ko26ez.7 for the enrollment and capacity scenarios, livespec-dev-tooling-ko26ez.6 for the architecture scenario and livespec-dev-tooling-ko26ez.8 for the departure scenario; regenerate the heading-coverage debt register. No `## ` heading is removed.
