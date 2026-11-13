---
topic: arc-listener-pods-run-only
author: claude-fable-5-2:homelab-k8s-worker-nodes
created_at: 2026-11-13T00:25:00Z
---

## Proposal: State that ARC listener pods run only on always-on nodes, a posture each node's profile declares

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md §"Runner-pool node rebuild recipe", after the paragraph "**Factory posture from the profile, surviving registration.**", and adds the always-on posture to the list of node-specific values in "**One profile per node.**". The new paragraph states that a pool node's always-on posture is read from its committed profile, is carried by one node label that survives a control-plane boot, and is the only thing an Actions Runner Controller (ARC) listener pod is placed by, for every runner scale set. It also requires a committed read-back of listener placement. Adds two scenarios to scenarios.md. Work item livespec-dev-tooling-crvvxt owns the implementation.

### Motivation

Measured 2026-11-12 (work items livespec-dev-tooling-acgcwp and livespec-dev-tooling-crvvxt). gamingpc-xubuntu was powered off from 21:23:26Z to 22:13:24Z for a RAM upgrade. Eight ARC AutoscalingListener pods were on it. They sat Terminating with no replacement from about 21:28Z to 22:13:30Z. A scale set with no listener takes no jobs, and its idle runners kept holding Kueue cohort quota, so every queue in the cohort lost slots. livespec-overseer's master run waited 88 minutes.

Nothing committed kept a listener off that node. Only one values file carried a `listenerTemplate`, and it selected by CPU architecture alone. At 2026-11-12 23:35Z every listener was on hp-xubuntu by the scheduler's choice, not by a rule.

The companion proposal `k3s-window-drain-committed-evacuate` states the plays that move a listener off a node before a planned power-off and clear one after a loss. Those repair an exposure. This proposal removes it: a listener is never placed on a node that is powered down at will, so a planned power-off of such a node strands none.

Ruling and ordering. legacy-coordinator-agent ruled on 2026-11-12 at about 23:50Z that this holds for every runner scale set, and at about 23:58Z that the implementation is hand-landed because it changes values files the CI-stack converge applies. The implementation is on branch `fix/crvvxt-listeners-on-always-on-nodes`. This proposal is the specification that follows; it states the behaviour the item's Definition of Done asserts. The dispatcher's launch screen classified the item as a specification change with this topic (its record of 2026-11-12T23:53Z on the item).

Why the profile. "**One profile per node.**" already requires every node-specific value to be read from the node's committed profile, and "**Factory posture from the profile, surviving registration.**" already states one posture label that way. Whether a node is always on is a fact about the node of the same kind, so it takes the same shape: a profile value, one label, and the same survival rule.

Why the default is not-always-on. A node whose profile says nothing must never be chosen for a listener. A homelab container worker has no profile at all, so the default is also what keeps a listener off it.

Not established: whether the ARC chart version in use re-creates a running listener pod when its `listenerTemplate` changes, and how long a listener takes to appear on another node after one is deleted. Neither has been measured.

In-flight survey, 2026-11-13. The pending proposal `k3s-window-drain-committed-evacuate` changes §"Consent-gated pool-node disruption" and not this section; it is compatible, and the two do not touch the same paragraph. No other pending proposal changes "**One profile per node.**" or the factory-posture paragraph.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Runner-pool node rebuild recipe", paragraph "**One profile per node.**", replace the words "the node's admission capacity, and its factory posture" with "the node's admission capacity, its factory posture, and its always-on posture". No other word of that paragraph is changed.

In the same section, insert the following paragraph immediately after the paragraph that begins "**Factory posture from the profile, surviving registration.**". No heading is added, removed or renamed in that file.

**Always-on posture from the profile, and listener placement by it.** A pool node's profile MUST declare whether the node is always on in its `ALWAYS_ON_NODE` key, as `true` or `false`. The profile parser MUST refuse any other value, naming the key, and a profile that does not carry the key MUST be read as `false`, so that a node nobody has declared is never treated as always on. A node whose profile declares `ALWAYS_ON_NODE=true` MUST carry the node label `ci-runner.io/always-on=true`. Every other node MUST NOT carry it: that covers a node whose profile declares `false` and a node that has no profile (a homelab container worker). The label MUST NOT be set or removed by hand. It MUST be re-established at node registration or by a mechanism that runs unattended at control-plane boot, with no playbook applied and no command run on any host, exactly as the factory label is; a reconcile that runs only when a playbook is applied MAY also correct it but MUST NOT be the only mechanism that sets it. Every runner scale set's values MUST place its Actions Runner Controller listener pod only on nodes that carry that label, by a node selector or a required node affinity on the listener's pod template, and the repository's check suite MUST refuse a scale set values file that lacks that placement, naming the file. The procedure that installs the scale sets at control-plane boot MUST establish the label before it installs them, and MUST stop without installing them, saying why, when no node carries the label or when it cannot read which nodes do: a scale set installed then would have a listener that can be placed nowhere, and it would take no jobs. The repository MUST carry a committed, read-only read-back that lists each scale set's listener pod with the node it runs on. It MUST exit non-zero when a scale set has no listener pod, when a listener pod is not Running, or when one runs on a node that does not carry the label, and it MUST exit non-zero, distinguishably, when a read of the cluster fails. A failed read MUST NOT be reported as a correct placement.

In `SPECIFICATION/scenarios.md`, insert the following two scenarios immediately after the scenario "a factory node keeps its factory label across a control-plane reboot".

## Scenario: every scale set's listener pod runs on an always-on node

Given every pool node's committed profile declares `ALWAYS_ON_NODE`

And each node whose profile declares `ALWAYS_ON_NODE=true` carries the `ci-runner.io/always-on=true` label, and no other node carries it

When the runner scale sets are converged from their committed values

Then each scale set's listener pod MUST be Running on a node that carries `ci-runner.io/always-on=true`

And a listener pod MUST NOT run on a node whose profile declares `ALWAYS_ON_NODE=false` or on a homelab container worker

And the committed read-back MUST list each scale set's listener pod with its node and MUST exit zero

## Scenario: the listener read-back fails when a listener is on a node that is not always on

Given a scale set's listener pod runs on a node that does not carry `ci-runner.io/always-on=true`

When an operator runs the committed listener read-back

Then the read-back MUST name that scale set, its listener pod and the node

And the read-back MUST exit non-zero

**Co-edit owed at revise.** This proposal adds two `## ` headings to `scenarios.md` and none to `non-functional-requirements.md`. The revise that accepts it MUST add one `tests/heading-coverage.json` entry per new scenario heading in the same commit. A spec-first `"test": "TODO"` row MUST carry a `reason` that names the tier the owed test runs at and the owning work item, and a `work_item` key naming that open item (livespec-dev-tooling-crvvxt while it is open); the revise MUST then run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`.
