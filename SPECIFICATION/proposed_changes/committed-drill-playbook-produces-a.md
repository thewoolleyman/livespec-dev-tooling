---
topic: committed-drill-playbook-produces-a
author: claude-opus-5-5
created_at: 2026-10-30T18:56:47Z
---

## Proposal: A committed container-termination drill is a consent-gated disruption

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Widen the scope of §"Consent-gated pool-node disruption" from disrupting a node to also deliberately terminating containers on the cluster, and add a paragraph stating what a container-termination drill must do: refuse the factory namespaces and any namespace that already exists before any cluster write, produce one CrashLoopBackOff container and one OOMKilled container in a throwaway namespace it creates, report its UTC window and namespace name, and delete that namespace even when a step fails.

### Motivation

The k3s cluster has had zero container restarts, so the termination-reason telemetry (k8s.container.status.last_terminated_reason), the board's termination-reasons panel and the factory OOM-or-crash-loop trigger have never seen a row. A positive control is needed to prove them on the host (work item livespec-dev-tooling-t6om4l, plan kubernetes-node-observability). fleet_host_guard refuses a by-hand kubectl create, so the control must be a committed playbook — but the ratified section governs only node disruption, so a container-termination drill (livespec-dev-tooling-2zii7l) currently has no ratified rule fencing it away from the factory namespaces or obliging it to clean up.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Consent-gated pool-node disruption":

1. Replace the first sentence of the **Scope.** paragraph with: "This section covers deliberately disrupting a runner-pool node, such as rebooting the control-plane node or taking an agent node's k3s agent down to exercise node loss, and deliberately terminating containers on the cluster to exercise termination telemetry." The rest of the paragraph is unchanged. The **Committed and consent-gated.** paragraph therefore governs a container-termination drill too: it MUST be a committed playbook applied from `vps` with `just ansible-apply`, it MUST act only on the single host named by its confirmation variable, and it MUST change nothing when that confirmation is absent or names another host.

2. Append, after the **It restores and verifies.** paragraph, a new paragraph:

**A container-termination drill works only in a throwaway namespace.** A playbook that terminates containers to exercise termination telemetry MUST create its own namespace and MUST exit non-zero before any cluster write when its configured namespace is `factory`, `factory-mi-homelab`, or any namespace that already exists. In that namespace it MUST produce one container the API server reports waiting with reason `CrashLoopBackOff` after at least 3 restarts, and one container whose last terminated state carries reason `OOMKilled`. It MUST print its start and end UTC times and the namespace's name. It MUST delete that namespace in an `always` block, so the namespace is deleted when a wait step fails or times out, and the API server MUST no longer list the namespace once the drill exits. It MUST NOT create, modify or delete any object outside that namespace.

## Proposal: Scenario for the container-termination drill

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a Gherkin scenario stating the container-termination drill's observable behaviour, placed directly after the node-loss drill scenario.

### Motivation

Behaviour introduced by a normative clause MUST also be stated as a scenario (spec.md §"Self-application"); the drill's work item references this scenario for its host-captured assertions.

### Proposed Changes

In SPECIFICATION/scenarios.md, insert after `## Scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads` and its steps:

## Scenario: a container-termination drill produces a crash-looping and an OOM-killed container in a throwaway namespace and deletes it

Given the k3s cluster reached from the control node `vps` and a drill namespace name that the API server does not list

When an operator applies the container-termination drill with its confirmation naming the target host

Then the API server MUST report one container in that namespace waiting with reason `CrashLoopBackOff` after at least 3 restarts and another whose last terminated state carries reason `OOMKilled`

And the drill MUST print its start and end UTC times and the namespace's name

And once the drill exits the API server MUST NOT list that namespace, and no object outside it MUST have been created, modified or deleted

And applying the drill without its confirmation, or with `factory`, `factory-mi-homelab` or an existing namespace configured, MUST exit before any cluster write
