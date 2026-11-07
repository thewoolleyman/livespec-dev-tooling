---
topic: runner-placement-covers-churn-slot-sets-and-fails-open
author: claude-opus-5-5
created_at: 2026-11-07T17:33:07Z
---

## Proposal: Runner placement covers churn-slot runner pods and fails open while its scheduler is down

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Limit **Runner placement follows admission capacity** to runner pods that request a churn slot, and require a runner pod stranded by a down runner scheduler to be handed to the default scheduler.

### Motivation

The clause says every CI runner pod, but two of the 14 live scale sets cannot follow it, and it says nothing about a down scheduler. livespec-dev-tooling-mtvxde is finishing the rollout, so code and spec would otherwise disagree.

Scope, measured 2026-11-07 ~17:24Z with `kubectl get autoscalingrunnersets -A` and read from the committed values files: `poweredge-xubuntu-k3s` (a phase-1 proof set, with no Kueue label and no churn-slot request) and `macbook-m4-max-homelab-worker-k3s` (its file records that a worker does not advertise churn slots). Neither requests a churn slot, so a slot-fraction scorer has nothing to rank for them. Bringing them under the rule would change how they are admitted, which is a separate decision. legacy-coordinator-agent asked for the clause to state this rather than leave it in code comments.

Fail-open: a pod that names a scheduler with no ready replica is never bound, so an outage of the scheduler this clause requires would stall CI. The fail-open decision is already recorded on livespec-dev-tooling-mtvxde and its Definition of Done, but the ratified clause as written forbids any placement that ignores slot use. Recreating the pod is required because a pod's schedulerName is immutable. ARC 0.14.2 recreates a missing runner pod from its EphemeralRunner's spec, so the rescue touches only stranded pods, whereas editing the scale set's template would recreate its listener and EphemeralRunnerSet at the start and end of each outage (the controller runs --update-strategy=immediate, read live). The 60 s grace rides out both replicas restarting at once. The 30 s is the reconciler's timer. Together they fit the 120 s unscheduled-runner trip threshold the canary watch used (worst observed 8 s over 144 samples, 2026-11-04).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, "## Runner-pool node rebuild recipe", paragraph **Runner placement follows admission capacity**:

First sentence, before: A CI runner pod MUST be placed on a node by the fraction of that node's declared `ci-runner.io/churn-slot` capacity already in use, preferring the node with the lowest fraction, among the nodes that have a free churn slot.

First sentence, after: A CI runner pod that requests a `ci-runner.io/churn-slot` MUST be placed on a node by the fraction of that node's declared `ci-runner.io/churn-slot` capacity already in use, preferring the node with the lowest fraction, among the nodes that have a free churn slot.

Add at the end of the same paragraph: A runner pod that requests no churn slot is outside this rule and is placed by the default scheduler, because it has no slot use to rank and is not admitted against any node's churn-slot capacity. While the scheduler that realizes this rule has had no ready replica for 60 seconds, a runner pod that names it and is Pending with no node and no scheduling gate MUST be recreated naming the default scheduler within the next 30 seconds, so a scheduler outage never stalls CI. A runner pod placed this way ignores churn-slot use, and each node's declared churn-slot capacity still limits it through the default scheduler's fit filter. The zero-ready state MUST raise an alert. A failed read of the scheduler's state MUST NOT recreate any pod.

In `SPECIFICATION/scenarios.md`, immediately after "## Scenario: a node takes runner pods up to its declared churn-slot capacity and no fewer", add:

## Scenario: a runner pod that requests no churn slot is placed by the default scheduler

Given a runner scale set whose runner pods request no `ci-runner.io/churn-slot`

When one of its runner pods is created

Then the pod MUST name the default scheduler
And no node's churn-slot use MUST change

## Scenario: a runner pod stranded by a down runner scheduler is handed to the default scheduler

Given the runner scheduler has had no ready replica for 60 seconds
And a runner pod that names it is Pending with no node and no scheduling gate

When the fail-open reconciler next runs

Then the pod MUST be recreated under the same runner name, naming the default scheduler
And it MUST be placed on a node with a free churn slot
And the scale set's own template MUST stay unchanged

## Scenario: a runner pod still gated by Kueue is left alone during a scheduler outage

Given the runner scheduler has had no ready replica for 60 seconds
And a runner pod that names it still carries a scheduling gate

When the fail-open reconciler runs

Then that pod MUST NOT be recreated

## Scenario: a failed read of the runner scheduler changes nothing

Given the runner scheduler's Deployment cannot be read because the API call failed

When the fail-open reconciler runs

Then no runner and no runner pod MUST change
And the run MUST exit non-zero

