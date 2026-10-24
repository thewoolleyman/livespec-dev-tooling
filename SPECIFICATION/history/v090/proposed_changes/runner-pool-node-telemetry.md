---
topic: runner-pool-node-telemetry
author: claude-opus-5-5
created_at: 2026-10-24T01:53:12Z
---

## Proposal: Govern runner-pool node load and utilization telemetry

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds §"Runner-pool node telemetry": every k3s pool node's kubelet usage, conditions and allocatable; pod and request/limit attribution by node and namespace; host metrics on every node; GitOps convergence through ansible/ci-pool.yml; a board, saturation and memory triggers, and a per-node dead-man; plus one governing scenario.

### Motivation

The maintainer asked (2026-10-24) whether Honeycomb had proper observability of all Kubernetes usage — the load and utilization of every worker node — and directed that, unless the answer was a complete yes, a plan put it in place as the priority "so we can have visibility into the Kubernetes load and not fly blind". It was not: only poweredge-xubuntu's kubelet was scraped, pod rows carried no node, gmktec-xubuntu had no collector and hp-xubuntu's host metrics went to another environment. No section of the ratified spec states the node-level obligation, so the plan's board and trigger work item (livespec-dev-tooling-uftb4o) was held at intake for having no governing heading. §"Runner-pool cache telemetry" governs cache tiers only.

### Proposed Changes

Add a new H2 to `SPECIFICATION/non-functional-requirements.md`, placed immediately after `## Runner-pool cache telemetry`, with exactly this text:

## Runner-pool node telemetry

**Scope.** This section governs the load and utilization telemetry of every node of the self-hosted CI runner pool's k3s cluster — the server, every CI agent, and every factory-only agent — whatever its `cluster_role` or factory posture. It is the node-level companion of §"Runner-pool cache telemetry", and it emits to the same fleet observability surface.

**Kubelet usage for every node.** Every node the cluster's API server lists MUST have its kubelet's node-level CPU usage, memory working set and available memory, filesystem usage and capacity, and network traffic emitted to the fleet observability surface, attributed by `k8s.node.name`. Every node MUST also report its Ready, MemoryPressure, DiskPressure and PIDPressure condition gauges and its allocatable CPU and memory. The set of nodes scraped MUST be discovered from the API server, so a node that joins the cluster is reported with no per-node configuration edit; a configuration that names one node's kubelet MUST NOT be the mechanism.

**Pod attribution.** Every pod's CPU and memory usage MUST carry the node it runs on and its namespace, the factory namespace included, and every container's CPU and memory requests and limits MUST carry the node it is scheduled on, so that requests and limits are readable against that node's allocatable. On a row describing a node, a pod or a container, `host.name` MUST name the node the row is about, never the host of the collector that read it.

**Host metrics on every node.** Every pool node MUST run a host collector that emits CPU utilization by state, load average, memory usage, per-mount filesystem usage, and disk and network I/O, stamped with `host.name` equal to the node's name. CPU saturation MUST be read from the idle share of CPU utilization, never from load average alone.

**Converged, never hand-installed.** Every pool node's collector — its configuration (read from the merged branch of `thewoolleyman/otel-collector`), its unit, its pinned binary and its ingest-key environment entry — MUST be converged by `ansible/ci-pool.yml`, so the node-provisioning stage of §"Runner-pool node rebuild recipe" returns a rebuilt node reporting, and the drift report `just ansible-drift ansible/ci-pool.yml` MUST report a node whose collector differs from the merged configuration. A hand-run installer MUST NOT be the deployment path.

**Board and triggers.** The fleet MUST carry, as code under `ci-runner/observability/boards/` and `ci-runner/observability/triggers/` converged by their `apply-*.sh`, one board showing per node the CPU, memory, filesystem and network usage, the four condition gauges, requests and limits against allocatable, and pod usage by node and namespace; and value triggers for a node whose CPU idle share stays at or below 10% for 15 minutes, a node reporting MemoryPressure, and a node whose memory working set exceeds 90% of its capacity. Each node MUST also carry a dead-man trigger, ungrouped and filtered to that one node, that fires when its kubelet usage stops arriving, because a grouped query cannot fire on a silent subject. Every trigger description MUST name the emitter path, the receiver path, the owning work item and a runbook, as the pool's existing triggers do.

**Failure contract.** No node-telemetry emitter MAY run inside a CI job pod or hand a credential to one. The collector reading every kubelet MUST hold only a read-only cluster identity, never the admin kubeconfig.

Add a new scenario to `SPECIFICATION/scenarios.md`, placed immediately after `## Scenario: a stale warm-cache generation fires the trigger`, with exactly this text:

## Scenario: every k3s pool node's load is visible and a silent node fires its dead-man

Given the k3s cluster lists three nodes and each node's collector was converged by `ansible/ci-pool.yml`

When a pod in the factory namespace runs on one of them and another node's kubelet stops answering

Then the fleet observability surface MUST show every node's kubelet CPU and memory usage attributed by `k8s.node.name`

And the factory pod's usage rows MUST carry the node the API server scheduled it on and its namespace

And the silent node's dead-man trigger MUST fire while the other nodes' dead-man triggers stay quiet

Co-edit `tests/heading-coverage.json` atomically: add an entry for `non-functional-requirements.md` heading `## Runner-pool node telemetry` and for `scenarios.md` heading `## Scenario: every k3s pool node's load is visible and a silent node fires its dead-man`, each with `test` `"TODO"` and a `reason` naming plan kubernetes-node-observability (epic livespec-dev-tooling-dfdiil), whose children livespec-dev-tooling-a2aiza, -b7wwgy, -ool6ws and -uftb4o realize the obligations; a host-run verification under that plan's Proof of Done SHOULD replace the TODO.
