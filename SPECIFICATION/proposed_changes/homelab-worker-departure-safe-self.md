---
topic: homelab-worker-departure-safe-self
author: claude-fable-5-2:homelab-k8s-worker-nodes
created_at: 2026-11-13T01:35:00Z
---

## Proposal: State that a homelab worker's networking agents run without restarts while it carries load

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one bullet to non-functional-requirements.md §"Homelab worker nodes", after the bullet "**Departure and rejoin.**". It states that the networking agents the fleet runs on a homelab worker (its pod-network agent, its service proxy and its network-policy agent) stay up while the worker is a Ready member of the cluster carrying production load, that their restart counts are the observable, and that a measured restart is a defect to be fixed at its cause. Adds one scenario to scenarios.md. Work item livespec-dev-tooling-p4cv4l owns the proof.

### Motivation

The plan homelab-k8s-worker-nodes (epic livespec-dev-tooling-ko26ez) carries this in its Definition of Done: "The worker's networking agents and host collector run without restarts or per-session host steps across the live-load window." Work item livespec-dev-tooling-p4cv4l carries it as its third assertion. The ratified section does not state it. legacy-coordinator-agent checked `## Homelab worker nodes` on master on 2026-11-13 and found that "**Departure and rejoin.**" states the item's first two assertions and that nothing states this one. The launch screen's tier record for the item names this topic, and no proposal carried it.

Measured. On 2026-11-07 the three networking DaemonSet pods on macbook-m4-max-homelab-worker had restarted 17, 11 and 11 times in 38 hours (homelab-worker-flannel, homelab-worker-kube-proxy and homelab-worker-kube-router; recorded on livespec-dev-tooling-p4cv4l). A pod network whose agents restart that often drops in-flight connections for the workloads on the node, which is why the plan made the count a finish-line assertion. After the worker was removed and rejoined on 2026-11-12, the three pods created at 19:07:32Z read 0 restarts at 2026-11-13T00:25Z, inside the live-load window that began at 2026-11-12T22:14Z.

Why a restart count, and why it excludes a departure. The count is what the cluster records and what the plan measures. A worker that leaves the cluster (its host sleeps or loses power) stops its agents with everything else on it; that is the case "**Departure and rejoin.**" governs, and it is not a defect in the agents. The proposed text therefore counts restarts only while the worker's Node stays Ready, and says so.

Why "fixed at its cause". A restart that has been measured and explained is a defect with an owner. Raising a restart threshold, or recreating the pods to zero the count, would hide it. The proposed text forbids the second and leaves no threshold to raise.

What this does not cover. The host collector's half of the plan's sentence is already stated by "**Departure and rejoin.**" ("its host collector MUST NOT depend on a per-session unlock of a host credential store"). This proposal adds nothing about the collector.

In-flight survey, 2026-11-13. No pending proposal changes `## Homelab worker nodes`. The pending proposals `k3s-window-drain-committed-evacuate` and `arc-listener-pods-run-only` change §"Consent-gated pool-node disruption" and §"Runner-pool node rebuild recipe"; neither touches this section.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Homelab worker nodes", insert the following bullet immediately after the bullet that begins "**Departure and rejoin.**". No heading is added, removed or renamed in that file, and no existing sentence is changed.

- **Stable networking agents under load.** The networking agents the fleet runs on a worker (its pod-network agent, its service proxy and its network-policy agent) MUST stay running for as long as the worker's Node is Ready and the worker carries production load. The observable is each agent pod's container restart count, read from the cluster: over a live-load window of at least 24 hours during which the Node stays Ready, each count MUST NOT rise. An agent pod replaced during the window ends that window; the window is counted as proof only if no agent pod was replaced, and a replacement is recorded with its cause. A departure of the worker is not such a restart, and "**Departure and rejoin.**" governs it. A restart that is measured MUST be recorded with its cause and fixed at that cause before the window is counted as proof; the count MUST NOT be cleared by deleting or recreating the agent pods for that purpose, and the window's record MUST name each agent pod, its creation time and its restart count at the window's start and end.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "a worker that leaves mid-run loses no work and rejoins on its own".

## Scenario: a worker's networking agents do not restart while it carries load

Given an enrolled worker whose Node is Ready and which takes CI jobs, gate jobs and factory runs from the fleet's queues

And the restart count of each of its networking agent pods is read at the start of a live-load window of at least 24 hours

When the window ends with the Node having stayed Ready throughout and no networking agent pod replaced

Then each networking agent pod's restart count MUST equal its count at the start of the window

And the record of the window MUST name each agent pod, its creation time and both counts

**Co-edit owed at revise.** This proposal adds one `## ` heading to `scenarios.md` and none to `non-functional-requirements.md`. The revise that accepts it MUST add one `tests/heading-coverage.json` entry for the new scenario heading in the same commit. The scenario needs a real worker and the production cluster over at least 24 hours, so its proof is host-captured: its row is a spec-first `"test": "TODO"` row whose `reason` names the host-captured tier and the owning work item, with a `work_item` key naming livespec-dev-tooling-p4cv4l while that item is open. The revise MUST then run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`.
