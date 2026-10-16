---
topic: consent-gated-pool-node-disruption
author: claude-opus-5-5:factory-worker-nodes-gitops
created_at: 2026-10-16T18:09:55Z
---

## Proposal: consent-gated pool-node disruption

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a section stating how this repository deliberately disrupts a runner-pool node. Every such disruption is a committed playbook that acts only on the one host its explicit confirmation names, and never a command run by hand. A node-loss drill also refuses the control-plane node and the factory hosts, waits only on CI runner and gate pods, never evicts other pods, and restores the node and verifies it.

### Motivation

The kubernetes-sandbox-backend plan's lifecycle proof (livespec-orchestrator-beads-fabro bd-ib-ad6dby) needs one agent node held NotReady while a factory sandbox runs on it. Stopping k3s-agent by hand is forbidden by the GitOps discipline, and no committed path existed, so work-item livespec-dev-tooling-raynnh builds ansible/node-loss-drill.yml. No heading in this specification states how a pool node may be deliberately disrupted, not even the existing ansible/reboot-ci-server.yml, so raynnh has no governing clause.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, insert a new section immediately before `## Fabro factory host provisioning`:

## Consent-gated pool-node disruption

**Scope.** This section covers deliberately disrupting a runner-pool node, such as rebooting the control-plane node or taking an agent node's k3s agent down to exercise node loss. That is a host action, and this section states how this repository performs it.

**Committed and consent-gated.** Every deliberate disruption of a pool node MUST be performed by a committed playbook applied from the control node `vps` with `just ansible-apply`, and MUST NOT be performed by a command run by hand on any host. Such a playbook MUST act only on the single host named by an explicit confirmation variable equal to that host's inventory name. It MUST change nothing when the confirmation is absent or names another host.

**A node-loss drill refuses the hosts it must not disturb.** A playbook that takes a node's k3s agent down to exercise node loss MUST refuse the control-plane node and every host that runs a Fabro server or the factory sandbox plugin. It MUST read those hosts from inventory groups, not from host names spelled in the play.

**It waits for CI, never for its subject.** Before it takes the agent down, a node-loss drill MUST wait until the node carries no CI runner pod and no gate Job pod, or until the runner pool reads idle. It MUST NOT cordon, drain, evict or delete any other pod, because a workload left on the node is what the drill exists to observe.

**It restores and verifies.** A node-loss drill MUST restore the node after its configured hold. It MUST fail unless the node returns Ready with its taints, its factory label and its admission capacity unchanged, and it MUST report the UTC times at which the API first showed the node NotReady and Ready again.

## Proposal: scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario stating the node-loss drill's behaviour end to end, so the clause is carried by a scenario as the authoring discipline requires.

### Motivation

Load-bearing behaviour is stated as a BCP14 clause and as a scenario. The drill can go wrong exactly where the clause binds: waiting on the wrong pods, evicting the workload it exists to observe, or leaving the node changed.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after `## Scenario: a factory node keeps its factory label across a control-plane reboot`:

## Scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads

Given an agent node that is not the control-plane node and runs no Fabro server and no factory sandbox plugin

And a factory sandbox pod runs on that node

When an operator applies the node-loss drill with its confirmation naming that node

Then the drill MUST wait until the node carries no CI runner pod and no gate Job pod before it takes the node's k3s agent down

And the API MUST report the node NotReady for the configured hold, after which the drill MUST restore the node to Ready

And the drill MUST NOT have cordoned, drained, evicted or deleted the factory sandbox pod

And the drill MUST report the times the node went NotReady and became Ready again, and MUST fail unless the node's taints, factory label and admission capacity are unchanged
