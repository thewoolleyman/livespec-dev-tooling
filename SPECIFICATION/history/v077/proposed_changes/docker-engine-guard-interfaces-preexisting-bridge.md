---
topic: docker-engine-guard-interfaces-preexisting-bridge
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-18T03:12:00Z
---

## Proposal: the guard's interfaces probe ignores veths that join a bridge the snapshot recorded

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Amend the observer's Interfaces probe in §"Docker engine install guard" so that a new veth whose master is a bridge recorded in the run's interface snapshot does not fail a sample. On a k3s node that admits CI pods, every pod that starts adds a veth on k3s's `cni0` bridge, so the ratified rule fails the first sample of every window on a live CI node and the install can never commit. Docker's own veths join `docker0`, which is never in the snapshot, so they still fail the sample exactly as now.

### Motivation

Measured 2026-10-18 on the first attended converge of the guarded Docker install on gmktec-xubuntu, a k3s agent in the CI pool (12 churn slots), against livespec-dev-tooling master 6a81f29b (release v1.113.1 guard modules). Gate 20261018T030444Z-3778031, run r2026101803080120e0. Every probe passed at sample 1 except `interfaces`, which failed with `these interfaces appeared since the snapshot: ('veth13671da9', 'veth1c9e020c', ... 18 names)`, failed again on its immediate re-run, and so the observer refused. The guard rolled the run back cleanly: phase rolled-back, committed False, no unit left running, FORWARD ACCEPT before and after. Every veth on the node has master `cni0` (`ip -o link show type veth`, 2026-10-18 ~03:20Z), and the node went from 1 pod at the 03:04Z pre-read to 8 pods during the window: CI pods scheduled while the window ran. The disposable acceptance VMs run a k3s stub with no pod churn, which is why FAULTS never exercised this. The same section already exempts k3s's own churn from the firewall comparison ("It skips the contents of `KUBE-*` and `FLANNEL-*` chains"); the interfaces rule lacks the equivalent, so the guard cannot install Docker on any CI node. Plan petri-factory-on-gmktec, epic bd-ib-fyozyd in livespec-orchestrator-beads-fabro; work-item livespec-dev-tooling-xxfqqr.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Docker engine install guard", in the list of observer probes, replace the bullet

> - **Interfaces.** A sample fails when any interface other than `docker0` and the canary's one veth pair has appeared since the snapshot.

with:

> - **Interfaces.** A sample fails when any interface other than `docker0`, the canary's one veth pair, and a veth whose master is a bridge recorded in the snapshot has appeared since the snapshot. A veth whose master is `docker0` or any other interface absent from the snapshot fails the sample unless it is the canary's.

Every other probe and sentence stays as it is.

## Proposal: a scenario for an observation window on a node whose pods start during it

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario stating that pod veths joining a bridge that existed at the snapshot do not fail a sample, while a non-canary veth on `docker0` still does.

### Motivation

The first proposal changes a probe's failure condition, which is load-bearing behaviour, so per the authoring discipline it needs a Given/When/Then scenario. Measured 2026-10-18 on gmktec-xubuntu, gate 20261018T030444Z-3778031, run r2026101803080120e0: 18 new veths with master `cni0` failed the interfaces probe at sample 1 and the run rolled back. Placed after §"Scenario: a Docker engine install guard publish resumed after a kill during an intended package's unpack re-unpacks it from its audited archive". The revise that accepts it owes the matching `tests/heading-coverage.json` entry in the same change.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, immediately after §"Scenario: a Docker engine install guard publish resumed after a kill during an intended package's unpack re-unpacks it from its audited archive", add:

```
## Scenario: a Docker engine install guard observation sample ignores pod veths on a bridge the snapshot recorded

Given a run whose interface snapshot records the bridge `cni0`

And during the observation window a new veth appears whose master is `cni0`

When the observer takes a sample

Then the interfaces probe MUST pass for that veth

Given the same run, and a new veth appears whose master is `docker0` and that is not the canary's

When the observer takes a sample

Then the interfaces probe MUST fail naming that veth
```
