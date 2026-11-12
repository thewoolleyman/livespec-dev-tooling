---
topic: gate-placement-and-kueue-admission
author: claude-opus-5-5
created_at: 2026-11-12T10:49:45Z
---

## Proposal: Gate placement and Kueue admission stay readable after the Workload object is gone

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a "Gate placement and admission history" paragraph to §"Runner-pool workload and control-plane telemetry". It requires one observability record per gate Workload admission (Workload, ClusterQueue, flavor per pod set, time) and one per gate pod scheduling (pod, namespace, node, bind time), readable for at least 7 days whether or not the cluster still holds the objects, read with the read-only identity by watching the API server. The mechanism is left to the implementation, and the Warning-event requirement is unchanged. One scenario and one heading-coverage entry ship in the same change.

### Motivation

Measured 2026-11-12, answering legacy-coordinator-agent's ruling 3b: whether gmktec's gate lane (gates-cq/gates-flavor) was full at 06:17-06:27Z, when bd-ib-ax6bxj's factory pod missed with "Insufficient memory", could not be answered. The cluster retained Kueue Workload objects for only about 2 hours (oldest 08:29Z at 10:2xZ). The k8sobjects watch exports only Warning events, as §"Cluster events" requires, so no Scheduled or admission record reached the surface. The Warning events that did arrive (kueue-admission Pending at 06:12:35, 06:14:37, 06:15:29 and 06:28:29Z) name no node or flavor. Grading every factory_pod_budget against its node's pinned gate lanes (rule K) needs exactly this history. §"Kueue admission" requires only current per-queue counts and usage, which cannot answer which lane held which gate at a past instant. Work item livespec-dev-tooling-2mp63s (plan kubernetes-observability, epic livespec-dev-tooling-s2aqob) carries the implementation, and legacy-coordinator-agent holds it at the spec-change tier until this topic ratifies.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool workload and control-plane telemetry", insert this new paragraph directly after the paragraph that begins "**Kueue admission.**" and before "**Board and triggers.**":

**Gate placement and admission history.** For every Workload a gate ClusterQueue (`gates-cq`, `gates-repro-cq`) admits, the fleet observability surface MUST carry one record of its admission. The record names the Workload, its ClusterQueue, the resource flavor of each pod set, and the time of admission. For every pod a gate Job runs, the surface MUST carry one record of its scheduling, naming the pod, its namespace, the node it was bound to, and the time it was bound. Both records MUST be readable on that surface for at least 7 days after the event, independent of whether the Kueue Workload object or the pod still exists in the cluster, so that whether a gate lane was full at a past instant can be answered after the cluster has garbage-collected its objects. They MUST be read with the read-only cluster identity, by watching the API server. The emitter MAY widen the event stream beyond `Warning` or watch Workload and pod status directly; this paragraph requires the records, not the mechanism. The **Cluster events** requirement for `Warning` events is unchanged.

In `SPECIFICATION/scenarios.md`, insert this scenario directly after `## Scenario: a factory namespace near its quota and a saturated ClusterQueue are each readable and the quota trigger fires`:

## Scenario: a gate's lane and node stay readable after its Workload object is gone

Given the k3s cluster's emitters were converged by `ansible/ci-pool.yml`

And a gate Job's Workload was admitted by `gates-cq` on the resource flavor `gates-flavor`, and its pod was bound to `gmktec-xubuntu`

And the Workload and the pod have since finished and been removed from the cluster

When an operator queries the fleet observability surface for that Workload within 7 days of its admission

Then a record of the admission names the Workload, `gates-cq`, `gates-flavor` and the admission time

And a record of the scheduling names the gate pod, its namespace, `gmktec-xubuntu` and the bind time

In `tests/heading-coverage.json`, add one entry in the same revise for that scenario heading (`spec_file` `scenarios.md`), with `"test": "TODO"`, `"work_item": "livespec-dev-tooling-2mp63s"` and a non-empty `reason` saying the paragraph is spec-first and livespec-dev-tooling-2mp63s owns the test. The section's own H2 is unchanged, so its existing entry stands.
