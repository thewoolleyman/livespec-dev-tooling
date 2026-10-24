---
topic: runner-pool-workload-and-control-plane-telemetry
author: claude-opus-5-5 (seat kubernetes-node-observability)
created_at: 2026-10-24T16:19:32Z
spec_commitments:
  impl_followups:
    - id_hint: k3s-workload-health-telemetry
      description: |
        Extend the CI-host collector (thewoolleyman/otel-collector config.ci-runner-host.yaml, converged by ansible/ci-pool.yml) so every container's last termination reason reaches the metrics dataset, and so every Kubernetes Warning event in the cluster reaches the livespec environment as an event carrying its namespace, involved object, reason, message and node. Widen the read-only ClusterRole to list and watch events. Proven host-captured against the live cluster: an OOM-killed or crash-looping container and an unschedulable pod are each readable by namespace.
    - id_hint: k3s-control-plane-telemetry
      description: |
        Emit the API server's readiness (each named /readyz check, its pass or fail, and the probe latency) at least once a minute using the read-only cluster identity; expose the embedded etcd's metrics through the k3s server configuration converged by ansible/ci-pool.yml and emit database size against its quota, leader presence and WAL fsync latency; emit each Kueue ClusterQueue's per-resource usage beside its nominal quota. Proven host-captured: every series reads back from the livespec metrics dataset.
    - id_hint: k3s-workload-control-plane-board-triggers
      description: |
        Add the workload and control-plane panels and the six triggers this section names (OOM kill or crash loop in a factory namespace, factory pod pending past 10 minutes, factory ResourceQuota at or above 90 percent, API server unready, etcd unhealthy or near its quota, cluster-state emitter silent) under ci-runner/observability/boards and ci-runner/observability/triggers, converged by their apply scripts.
---

## Proposal: Runner-pool workload and control-plane telemetry

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a sibling section to `## Runner-pool node telemetry` in non-functional-requirements.md, `## Runner-pool workload and control-plane telemetry`, plus two scenarios in scenarios.md. Node telemetry answers how loaded each node is. It cannot answer whether the workloads on the cluster are healthy, or whether the cluster itself (API server, embedded etcd datastore, Kueue admission, namespace quotas) is healthy. The new section requires per-namespace pod phase counts, container restarts and termination reasons, the reason a pod is pending or unschedulable (from the cluster's Warning event stream), namespace ResourceQuota used against hard, API server readiness by named check, embedded etcd health and size against its quota, and each Kueue ClusterQueue's pending, admitted and per-resource usage against nominal quota. It also requires a board and six triggers, including a dead-man on the cluster-state emitter, under the same converged, read-only and never-in-a-CI-pod contract as node telemetry.

### Motivation

Maintainer direction, relayed by the coordinator of plan gitops-fleet-capacity-monitoring (epic livespec-dev-tooling-dfixhe) at about 16:2xZ on 2026-10-24, verbatim: "make the observability part of your plan ... observe everything about Kubernetes that is necessary and follows best practices to manage it." The v090 section `## Runner-pool node telemetry` governs nodes, pod resource usage, a board and node triggers only. Two of dfixhe's plan assertions have no governing heading: (9) per namespace, factory and factory-mi-homelab included, pod phase counts, container restarts, OOM-killed terminations, and pods unschedulable or pending past admission; (10) API server availability, embedded etcd health, factory and factory-mi-homelab namespace ResourceQuota used/hard (factory-runs, factory-mi-homelab-runs), and Kueue ClusterQueue admitted/pending/quota for the CI runner and gate queues. Its assertion 11 also needs triggers for OOM kills or crash-looping containers in a factory namespace, and for factory pods pending past a threshold. Measured on 2026-10-24 before drafting. The k3s datastore is embedded etcd (`/readyz?verbose` reports `etcd ok` and `etcd-readiness ok`). Kueue v0.19.1 runs 12 ClusterQueues serving the arc-runners and gates namespaces. factory-runs and factory-mi-homelab-runs are namespace ResourceQuotas, not ClusterQueues. Already arriving in livespec/metrics: k8s.pod.phase, k8s.container.restarts, k8s.container.ready, k8s.resource_quota.used/hard_limit, k8s.job.*, k8s.deployment.*, livespec.ci_pool.queue_pending/admitted/quota per queue, livespec.ci_kueue.webhook_ready_endpoints. Absent: any container termination reason, any Kubernetes event stream (so no FailedScheduling or OOMKilling reason anywhere), any API server or etcd series, and ClusterQueue usage, as opposed to nominal quota. Without them an OOM-killed factory pod, a pod the scheduler cannot place, an etcd database approaching its quota, or an unready API server is invisible until a run fails.

### Proposed Changes

Insert the following new H2 section into `SPECIFICATION/non-functional-requirements.md`, directly after `## Runner-pool node telemetry` and before `## Runner-pool node rebuild recipe`:

```markdown
## Runner-pool workload and control-plane telemetry

**Scope.** This section governs the health telemetry of the WORKLOADS on the self-hosted CI runner pool's k3s cluster and of the cluster's CONTROL PLANE: the API server, its embedded etcd datastore, Kueue admission and namespace resource quotas. It is the companion of §"Runner-pool node telemetry", which governs how loaded each node is; this section governs whether what runs on the nodes, and the cluster that schedules it, is healthy. It emits to the same fleet observability surface, and every requirement of that section's **Converged, never hand-installed** and **Failure contract** paragraphs applies to every emitter this section requires.

**Workload state per namespace.** For every namespace — the factory namespaces `factory` and `factory-mi-homelab` included — the fleet observability surface MUST carry each pod's phase (Pending, Running, Succeeded, Failed, Unknown) and each container's readiness and restart count, attributed by `k8s.namespace.name`, `k8s.pod.name` and, once scheduled, `k8s.node.name`, so pod phase counts and restarts are readable per namespace. Every container's most recent termination reason (for example `OOMKilled`, `Error`, `Completed`) MUST reach that surface with the same attribution, so an OOM-killed container is distinguishable from one that exited on its own.

**Cluster events.** Every Kubernetes event of type `Warning` in the cluster — among them `FailedScheduling`, `OOMKilling`, `BackOff`, `Evicted`, `FailedMount` and `FailedCreatePodSandBox` — MUST reach the fleet observability surface as an event carrying its namespace, the kind and name of the object it is about, its reason, its message, its count, and the node it names when it names one. A pod that is pending MUST therefore be readable together with the scheduler's stated reason it is not placed. The event stream MUST be read by watching the API server with the read-only cluster identity, never by scraping a node's log files.

**Namespace quotas.** Every namespace ResourceQuota — `factory-runs` and `factory-mi-homelab-runs` included — MUST have its used and hard values for every resource it constrains (pods, requests and limits of CPU and memory) reported per namespace, so a factory namespace's headroom is readable without a cluster credential.

**API server availability.** The API server's readiness MUST be probed at least once a minute from outside any CI job pod, using the read-only cluster identity, and every named readiness check the server reports (`etcd`, `etcd-readiness` and the rest of `/readyz?verbose`) MUST be emitted as a pass-or-fail series together with the probe's latency, so an unready API server and the check that made it unready are both readable.

**Datastore health.** Because the cluster's datastore is embedded etcd, its metrics MUST be exposed by the k3s server configuration converged by `ansible/ci-pool.yml`, and the database size against its configured quota, the presence of a leader, and the WAL fsync latency MUST reach the fleet observability surface. A datastore growing toward its quota MUST be visible before it reaches it, because an etcd database at its quota refuses every write.

**Kueue admission.** Every Kueue ClusterQueue MUST have its pending workloads, its admitted workloads, and, per resource and flavor, its usage beside its nominal quota reported per queue, so a saturated queue and a starved one are each readable. The Kueue controller's admission webhook availability MUST also be reported, because no workload is admitted while it is down.

**Board and triggers.** The fleet MUST carry, as code under `ci-runner/observability/boards/` and `ci-runner/observability/triggers/` converged by their `apply-*.sh`, panels showing pod phase counts, restarts and termination reasons per namespace, recent Warning events by reason and namespace, ResourceQuota used against hard per namespace, API server readiness by check, datastore size against quota and leader presence, and ClusterQueue pending, admitted and usage against quota; and triggers that fire when:

- a container in a factory namespace terminates with reason `OOMKilled`, or restarts three or more times within 15 minutes;
- a pod in a factory namespace stays in phase Pending for more than 10 minutes;
- a factory namespace's ResourceQuota usage of pods, CPU or memory stays at or above 90 percent of its hard value for 15 minutes;
- the API server readiness probe fails, or any named readiness check reports failure, for 3 consecutive minutes;
- the datastore reports no leader, a failing etcd readiness check, or a database size at or above 80 percent of its quota;
- the cluster-state emitter stops reporting pod phase rows, as an ungrouped dead-man, because every other trigger in this section goes silent with it.

Every trigger description MUST name the emitter path, the receiver path, the owning work item and a runbook, as the pool's existing triggers do.

**Failure contract.** The identity that watches events, probes readiness and reads Kueue and quota objects MUST be read-only: it MAY be granted `get`, `list` and `watch` on the objects it reads and `get` on the readiness endpoints, and it MUST NOT be granted any write verb or the admin kubeconfig. No emitter this section requires MAY run inside a CI job pod or hand a credential to one.
```

Append the following two scenarios to `SPECIFICATION/scenarios.md`, directly after `## Scenario: every k3s pool node's load is visible and a silent node fires its dead-man`:

```markdown
## Scenario: an OOM-killed or unschedulable factory pod is visible with its reason and fires its trigger

Given the k3s cluster's collectors were converged by `ansible/ci-pool.yml`

When a container in the `factory` namespace is terminated with reason `OOMKilled` and another factory pod stays Pending because the scheduler cannot place it

Then the fleet observability surface MUST show the terminated container's reason `OOMKilled` attributed by `k8s.namespace.name`, `k8s.pod.name` and `k8s.node.name`

And the Pending pod MUST be readable together with the scheduler's `FailedScheduling` event and its stated reason

And the factory OOM-or-crash-loop trigger MUST fire, and the factory pending-pod trigger MUST fire once the pod has been Pending for more than 10 minutes

## Scenario: an unready API server or an unhealthy datastore fires its trigger while the state emitter stays watched

Given the API server readiness probe and the datastore metrics were converged by `ansible/ci-pool.yml`

When the API server's `etcd` readiness check fails for 3 consecutive minutes

Then the fleet observability surface MUST show the failing check by name with the probe's latency

And the API-server-unready trigger and the datastore trigger MUST fire

And if the cluster-state emitter stops reporting pod phase rows, its dead-man trigger MUST fire
```

The revise that accepts this proposal MUST add `tests/heading-coverage.json` entries for `## Runner-pool workload and control-plane telemetry` and for both new scenario headings, in the same change.
