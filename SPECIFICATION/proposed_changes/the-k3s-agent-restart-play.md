---
topic: the-k3s-agent-restart-play
author: claude-fable-5-2
created_at: 2026-11-12T11:21:45Z
---

## Proposal: The agent restart play is stated, and its idle check does not count an ARC AutoscalingListener pod as workload

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md, section "Consent-gated pool-node disruption", stating the k3s agent restart play: which hosts it acts on, its single idle check, what that check does not count as workload, and its Ready requirement. It restates what the committed play (ansible/restart-k3s-agent.yml) already does and adds one new exemption: an Actions Runner Controller AutoscalingListener pod in arc-systems no longer refuses a restart. Adds one scenario to scenarios.md.

### Motivation

The specification does not state the agent restart play, although the play exists and is the only sanctioned way to restart a pool agent's k3s unit. Work item livespec-dev-tooling-6yxdxu was classified spec-change/UNSTATED for that reason. On 2026-11-12 at 08:28Z the play refused gamingpc-xubuntu because two AutoscalingListener pods sat on the node, with no runner, gate or factory sandbox pod there. A listener pod is owned by an AutoscalingListener object, so the play's DaemonSet and add-on ReplicaSet exemptions do not match it; a cordon never drains it; and no committed route moves it off a node. A node that carries a listener therefore can never be restarted through the committed route, which left one host-captured clause of livespec-dev-tooling-ew6bot unproved. A kubelet restart only pauses a listener, and GitHub queues jobs meanwhile, the same reasoning the play already records for a cluster add-on's controller replica (bd-ib-y6v7b6). The paragraph states the idle check's exemptions only; it leaves the refuse-rather-than-wait behaviour as the play has it, so livespec-dev-tooling-346ays can later revise that sentence on its own.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Consent-gated pool-node disruption", insert the following paragraph immediately after the paragraph that begins "**It restores and verifies.**" and before the paragraph that begins "**A container-termination drill works only in a throwaway namespace.**". No heading is added, removed or renamed in that file.

**An agent restart acts only on an idle agent node, and its idle check names what is not workload.** A playbook that restarts a pool agent node's k3s agent, so that the node's committed start configuration takes effect, is a disruption this section covers. It MUST act only on a host whose inventory cluster role is `agent`, and it MUST refuse the control-plane node. It MUST read that role from inventory, not from a host name spelled in the play. Unlike a node-loss drill it MUST NOT refuse a Fabro factory host as a group, because the idle check below is what protects a factory run. Immediately before the restart it MUST take one read of the pods on that node. When any of them is workload it MUST restart nothing and MUST fail, naming each pod that held it. It MUST NOT cordon, drain, evict or delete any pod. For that check a pod is not workload in exactly four cases: its phase is `Succeeded` or `Failed`; a DaemonSet owns it; a ReplicaSet owns it in a namespace the play lists as a cluster add-on's; or it is in the `arc-systems` namespace and an Actions Runner Controller `AutoscalingListener` owns it. A kubelet restart only pauses a pod of the last three kinds, and its controller keeps or recreates it; for a listener, GitHub queues jobs until it is back, and a cordon never moves it off the node. Every other pod is workload. A CI runner pod, a gate Job pod and a Fabro factory sandbox pod MUST each refuse the restart, and so MUST a pod no controller owns in any namespace and an `AutoscalingListener`-owned pod outside `arc-systems`. After the restart the play MUST fail unless the node returns Ready.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "a node-loss drill holds one agent node NotReady and restores it without touching its workloads" and before the scenario "a container-termination drill produces a crash-looping and an OOM-killed container in a throwaway namespace and deletes it".

## Scenario: an agent restart is not refused for an ARC listener pod and is refused for workload

Given an agent node whose only pods are DaemonSet pods and one Actions Runner Controller AutoscalingListener pod in the `arc-systems` namespace

When an operator applies the agent restart play with its confirmation naming that node

Then the play MUST restart the node's k3s agent without cordoning, draining, evicting or deleting any pod

And the play MUST fail unless the node returns Ready

Given the same node also runs a CI runner pod, a gate Job pod or a Fabro factory sandbox pod

When an operator applies the agent restart play with its confirmation naming that node

Then the play MUST restart nothing and MUST fail, naming that pod

And its failure message MUST NOT name the AutoscalingListener pod among the pods that held it

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-6yxdxu"`, with the heading-coverage debt register regenerated.
