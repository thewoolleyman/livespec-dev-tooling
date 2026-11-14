---
topic: homelab-worker-leaving-rejoining-and-pod-span-endpoint
author: claude-fable-5-2 (homelab-k8s-worker-nodes seat)
created_at: 2026-11-14T07:24:52Z
---

## Proposal: A worker whose Node is not Ready offers no quota, and a gate lost to node failure is retried

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Adds a bullet to the Homelab worker nodes section: while an enrolled worker's Node is not Ready its lanes leave admission automatically and return when it is Ready again, by one code path every worker lane shares; a gate Job whose pod is lost to node failure is retried and is not the gate's failure.

### Motivation

The ratified Departure and rejoin bullet says work on a departed worker MUST NOT be lost and that gate jobs MUST be retried or re-queued, but it does not say that the departed worker stops being offered to NEW work, nor how a gate's loss to a node failure is told from the gate's own failure. Measured in the departure drill of 2026-11-13T20:07:19Z on macbook-m4-max-homelab-worker: gate Job gate-livespec-dev-tooling-tv6wb was admitted on the unreachable worker's flavor 28 seconds after the departure, failed, and its push was refused. Work item livespec-dev-tooling-u45iv6 implements the rule; the dispatch spec-change-tier screen of 2026-11-14T07:21:26Z judged its behaviour only partly stated by this section and held it as unratified.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Homelab worker nodes", insert the following bullet directly after the bullet "**Departure and rejoin.**". It adds no heading.

- **A departed worker leaves admission.** While an enrolled worker's Node is not Ready (its Ready condition reads False or Unknown, or the Node carries the `node.kubernetes.io/unreachable` taint), the quota that worker's enrollment contributes MUST NOT be offered in any class: its churn slots MUST NOT count in the worker churn-slot flavor's quota, its gate share MUST NOT count in the gate queue's worker flavor, and no factory run MAY be placed on it. A workload created after the departure MUST NOT be admitted on that worker's flavor, and a workload that flavor would have taken MUST be admitted on another flavor when one fits it. When the Node is Ready again, the worker's derived quota MUST be offered again. Both changes MUST happen with no operator step, through the one code path every worker lane (gate, CI runner and factory) shares, and that path MUST name no host, address or worker name. The record of each change MUST name the worker and whether it read Ready. A gate Job whose pod is lost to a node failure (the pod terminated with the `DisruptionTarget` condition) MUST be retried, and that loss MUST NOT count as the gate's failure: the gate MUST reach its verdict on another node or after the worker returns, and its client MUST NOT be refused for the node loss.

## Proposal: Leaving a workload class removes everything its enrollment wrote, and placement depends on enrollment

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Adds a bullet to the Homelab worker nodes section: when a worker's enrollment in a class ends, every label, extended resource and queue quota that enrollment wrote is removed in the same operation, the factory admission label included, and no pod of a class is placed on a worker that is not enrolled in that class.

### Motivation

The ratified Automatic enrollment by workload class bullet states what a join writes and the Derived per-class capacity bullet says that removing a worker reconciles the cohort quota, but neither says what un-enrolling a worker from a class must undo. Measured on macbook-m4-max-homelab-worker: (1) 2026-11-13, an un-enroll at 21:51:07Z removed `ci-runner.io/factory` and left `ci-runner.io/factory-admit=true`, and the factory budget reconciler visits only nodes that carry `ci-runner.io/factory=true`, so the label stayed stale until the re-enroll at 22:10:21Z; (2) 2026-11-14, an un-enroll at 05:32:52Z removed `k3s-role` and the gate share label and took the worker flavor out of the gate queue, but left the node's `ci-runner.io/churn-slot` capacity at 1 and the quota of livespec-dev-tooling-arm64-cq's worker flavor at 1 (the converge printed "1 churn slots from enrolled arm64 workers"); (3) while the node was un-enrolled (from 05:51:43Z) runner pod livespec-orchestrator-k3s-zjtfd-runner-jhlzq was scheduled on it at 06:15Z, because that runner set's pods select only the worker class label and the architecture. Work item livespec-dev-tooling-ondpf6 implements the factory admission label part; the dispatch screen of 2026-11-14T07:21:26Z judged its behaviour unstated by this section. The churn-slot capacity, the queue quota and the placement rule have no owning work item yet. Three work items own the rule: livespec-dev-tooling-ondpf6 owns the stale `ci-runner.io/factory-admit` label; livespec-dev-tooling-xgic4t owns removing the worker's `ci-runner.io/churn-slot` capacity and its queue quota when it leaves the CI class; and livespec-dev-tooling-qb3esy owns placement that depends on enrollment, which is fleet scope because it covers every runner scale set's pod template and so every fleet repository's CI lane.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Homelab worker nodes", insert the following bullet directly after the bullet "**Automatic enrollment by workload class.**". It adds no heading.

- **Leaving a workload class.** When a worker's enrollment in a class ends, whether the worker is un-enrolled from that class or removed from the fleet, everything that class's enrollment wrote MUST be removed in the same operation: the class's node labels, the class's extended resource on the Node (for CI, its `ci-runner.io/churn-slot` capacity), and the worker's contribution to every queue quota of that class (for CI, the worker churn-slot flavor's quota; for gates, the gate queue's worker flavor). A label another component derives from the enrollment is part of it: a node that is not enrolled in the factory class MUST NOT carry `ci-runner.io/factory-admit` with the value `true` when the un-enrollment returns, and the factory budget reconciler MUST, on each pass, set that label to `false` on every node that carries it as `true` without the factory enrollment label, logging one line that names the node. A pod of a class MUST NOT be placed on a worker that is not enrolled in that class: a class's placement on a worker MUST depend on that class's enrollment itself, and tolerating the worker class taint and matching the worker's architecture MUST NOT be enough.

## Proposal: A removed worker's pods are gone before its Node name registers again, and a join proves its pod subnet

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Adds a bullet to the Homelab worker nodes section: removing a worker waits, for a bound of at least 15 minutes, until no pod is bound to its Node name and fails naming the pods left; a join refuses while such pods exist with no Node of that name; and after the Node registers the join verifies that the worker's pod-network subnet equals the Node's pod CIDR or fails naming both.

### Motivation

The ratified section governs the first join and a return from a departure, and says nothing of removing a worker and joining it again under the same Node name. Measured 2026-11-14 on macbook-m4-max-homelab-worker: `remove-worker.sh` deleted the Node at 05:48:43Z and `join-worker.sh` registered a Node of the same name at 05:49:03Z, 20 seconds later, with pod CIDR 10.42.8.0/24 (the removed Node had 10.42.7.0/24). The removed Node's pods were never collected: the three networking agent pods were the same 34-hour-old pods, the pod-network agent never restarted and kept subnet 10.42.7.1/24, and the join exited 0. A runner pod scheduled on the node at 05:49:48Z got 10.42.7.159, an address the cluster no longer routed to that node, and could not reach GitHub. In the repair, after the Node was deleted at 06:16:51Z, reads every 15 seconds showed three pods naming the node until 06:17:31Z, one pod until 06:26:48Z and none at 06:27:13Z, so collection took about 10 minutes; the join that followed got new networking pods and a matching subnet. On 2026-11-12 a 70-second gap happened to be enough. Work item livespec-dev-tooling-fvxlzc implements the rule; the dispatch screen of 2026-11-14T07:21:58Z judged its behaviour unstated by this section.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Homelab worker nodes", insert the following bullet directly after the bullet "**Standard bootstrap under an admission hold.**". It adds no heading.

- **Removal and rejoin under the same name.** A worker removed from the fleet and joined again registers under the same Node name, so the removed Node's pods MUST be gone before that name registers again. The removal path MUST, after it deletes the Node, wait until a read of the cluster shows no pod bound to that Node name, for a bound of at least 15 minutes, and MUST exit zero only once such a read shows none; when the bound passes with a pod still bound to the name it MUST exit non-zero and name each remaining pod. The join path MUST refuse, before it issues a bootstrap credential, while a pod bound to the worker's Node name exists and no Node of that name does, and MUST name each such pod. After the Node registers, the join MUST read the Node's pod CIDR and the subnet the worker's pod-network agent holds, and MUST exit non-zero naming both values when they still differ after a bounded wait. These reads MUST run in the code path every declared host shares, with the Node name taken from the host's derived worker name.

## Proposal: The pod-span endpoint follows the Node's pod subnet, never the bridge's address at join time

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Adds a bullet to the Homelab worker nodes section: the endpoint a worker's pods send spans to is the first usable address of the worker's current pod subnet, derived from that subnet and never from a bridge interface's address at the time of a join, and it follows the subnet at a join, a rejoin and a return from a departure with no operator step.

### Motivation

The ratified section requires that a returning worker rejoin with no operator step and names the host collector's credential, but it does not say where the worker's pod-span collector listens or what keeps that address right. Measured 2026-11-14 on macbook-m4-max-homelab-worker with release v1.208.0, which carries livespec-dev-tooling-qotekb's fix (the join copies the address of the bridge `cni0`): (1) JOIN, 06:27:28Z to 06:28:07Z: the Node registered with pod CIDR 10.42.9.0/24 and the pod-network agent rewrote its subnet to 10.42.9.1/24 at 06:27:43Z, while `cni0` still read 10.42.8.1; the join printed "pod-span endpoint now uses cni0 at 10.42.8.1:4319" and exited 0 with the recorded endpoint and the listener on 10.42.8.1. The bridge is re-addressed only when the first pod sandbox is created: with the first workload pod on the node (10.42.9.3), `cni0` read 10.42.9.1 at 06:30:12Z while the recorded endpoint and the listener still said 10.42.8.1, until an operator ran the start task at 06:30:26Z. (2) RETURN: after a power-loss departure at 06:04:47Z and the return at 06:15:07Z the pod-network agent adopted a new subnet and `cni0` became 10.42.8.1, but the recorded endpoint still said 10.42.7.1:4319 and nothing listened there. In both cases pods send spans to their node gateway on port 4319 and nothing answers. Work item livespec-dev-tooling-f2rft5 implements the rule.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Homelab worker nodes", insert the following bullet directly after the new bullet "**A departed worker leaves admission.**" (that is, after "**Departure and rejoin.**" and the bullet the first proposal of this file adds). It adds no heading.

- **Pod-span endpoint.** The endpoint a worker's pods send their spans to (the address and port the worker's pod-span collector listens on, as the worker's telemetry state records it) MUST be the first usable address of the worker's current pod subnet, on the collector's port. It MUST be derived from that subnet, the Node's pod CIDR as the worker's pod-network agent holds it, and MUST NOT be read from the address a bridge interface carries at the time of a join, because the bridge is re-addressed only when the first pod sandbox is created on the worker. A join on a worker that has a pod subnet and no bridge yet MUST record the endpoint from the subnet and name it in its output. Whenever the worker's pod subnet changes (at a join, at a rejoin that receives a different pod CIDR, and on a return from a departure) the recorded endpoint MUST come to name the new subnet's first usable address, and the collector MUST listen there once the bridge carries that address, both with no operator step. The endpoint MUST be derived by the code path every declared host shares, with no host name, pod CIDR or address written into the worker's scripts.
