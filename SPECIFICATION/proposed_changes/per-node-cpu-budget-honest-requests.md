---
topic: per-node-cpu-budget-honest-requests
author: claude-opus-5-5
created_at: 2026-11-13T20:05:11Z
---

## Proposal: The default gate request is 3 CPUs, and the gmktec lane floor follows the default rather than a literal 15

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Lower the renderer's default gate CPU request from 5 to 3, measured from how many cores gate pods actually use. State the gmktec lane's floor only as three times the renderer's default requests, so a lower default lowers the floor with it. Memory and parallelism defaults are unchanged. A repository whose gates need more, such as livespec-orchestrator-beads-fabro at 5, declares it as today.

### Motivation

Plan gate-job-resources (livespec-dev-tooling-ukoeah) was widened by the maintainer-approved ruling recorded on livespec-dev-tooling-6tgd2z at 2026-11-13T19:45:09Z. The plan now owns the per-node CPU budget, and the budget needs every class to request what it uses. Gate pods running longer than 2 minutes averaged 2.9-3.4 cores for livespec-dev-tooling and 4.6-5.1 for livespec-orchestrator-beads-fabro, and about 1-1.6 for every other repository. The source is Honeycomb livespec/metrics, k8s.pod.cpu.usage, queries wQQrW3wJxKs, FbosoCKz9um, fDC9tmuJwKw and h6PRCH1Y7oX over 2026-11-12 19:00Z to 11-13 19:00Z. The 5-CPU default is honest only for the orchestrator, which declares its own value. The gmktec lane's cpu quota is counted in CPU (15 = 3 x 5). The contract states that floor as a literal 15 CPU, so the lane cannot follow the budget even once the default moves. 3, not 2, keeps a full-size gate larger than the 2-CPU replay Job of Replay Job size, which plan assertion 2 depends on.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Declared gate resources**, the sentence "A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4`" MUST read CPU `3` in place of CPU `5`. Memory `6Gi` and parallelism `4` are unchanged.

In the same section, **Gate lane headroom** MUST read: "The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs: at least three times the renderer's default CPU request and at least three times its default memory request. It therefore admits at least three concurrent default-size gate Jobs." The literal "at least 15 CPU and at least 18Gi memory" is removed. Every other sentence of that bullet is kept: the schema floor, the derivation the tests assert, and the rule that a repository's declared resources MUST NOT be met by lowering the lane below the floor.

In scenarios.md, the body of "## Scenario: a repository that declares no gate resources keeps the default gate Job size" MUST read "Then the Job's container MUST request 3 CPUs and request and limit memory `6Gi`". The heading and the parallelism line are unchanged.

The scenario "## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs" already asserts the derivation and MUST NOT change.

No H2 heading is added, renamed or removed, so tests/heading-coverage.json is unchanged.

## Proposal: CI runner pods request their CPU per job, the runner scheduler profile does not filter on it, and every node's requests fit its allocatable CPU

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Give CI runner pods a real CPU request, so the scheduler and the node budget can see the largest class on gmktec, which today requests nothing. The paragraph "Runner placement follows admission capacity" keeps churn-slot capacity as the ONLY per-node limit on runner pods: the runner scheduler profile MUST NOT refuse or rank a node by CPU. A new clause requires each pool node's CPU requests to fit its allocatable CPU with every churn slot in use, so the kubelet never refuses a runner pod with OutOfcpu. One scenario and one heading-coverage entry ship with it.

### Motivation

Same ruling and plan as the first proposal. On gmktec-xubuntu the CI-runner class averaged 10.6 concurrent cores over 24 hours (W1-W4: 11.2, 12.0, 10.8, 8.3; queries GeJPtsYP2y8, 9HcAtrYUHGZ, y4PSHW5Bwnj, p4JpAQGQcsU) at a request of 0. That is the largest class on a node that sat at or above capacity in 12 of the 24 hours. Measured cost per CI job is about 1.7 cores on gmktec, 1.9 on poweredge and 2.0 on hp. A runner CPU request under today's text has two problems. The scheduler's resource fit would refuse a runner pod on a node whose non-runner pods request most of its CPU, which the scenario "a node takes runner pods up to its declared churn-slot capacity and no fewer" forbids. And the kubelet's own admission check refuses a pod whose request exceeds the node's unrequested allocatable CPU, whatever the scheduler decided. So the request needs both the profile exemption and a fit guarantee. This proposal ALIGNS with the pending proposal runner-placement-post-add-tie, which rewrites this paragraph's placement-score wording. It adds sentences and changes none of that wording, so whichever is revised first, the other applies on top.

### Proposed Changes

In non-functional-requirements.md, the paragraph **Runner placement follows admission capacity.** MUST gain the following sentences after its existing text. They change none of its existing sentences, and none of the wording the pending proposal runner-placement-post-add-tie rewrites:

"A CI runner pod that requests a `ci-runner.io/churn-slot` MUST also request CPU on its runner container. The request is the pool's CPU per CI job, one fleet-wide value taken from the committed per-node CPU budget (`ci-runner/k3s/phase2/NODE-CPU-BUDGET.md`). Its workflow pod, which the container hook binds to the runner pod's node by name, MUST NOT carry a CPU request. The runner scheduler profile MUST NOT refuse a node, or rank one node above another, by CPU. A runner pod's CPU request therefore decides neither whether nor where it is placed, and a node's declared churn-slot capacity stays the only per-node limit on how many runner pods it holds. Every ClusterQueue that admits runner pods MUST cover `cpu` with a nominal quota at least its churn-slot nominal quota times that request, so a runner pod's CPU request never makes it inadmissible."

In the same section, a new paragraph MUST follow it:

"**Each node's CPU requests fit its allocatable CPU.** For every pool node, the sum of these MUST NOT exceed that node's allocatable CPU:

- its declared churn-slot capacity times the runner CPU request;
- the nominal CPU quota of every gate lane whose flavor names that node;
- its factory pod budget (the `factory_pod_budget` of its ansible host_vars) times the factory sandbox pod's CPU request.

This is the condition under which the kubelet never refuses a runner pod for CPU while the node has a free churn slot. A check in the aggregate MUST fail, naming the node and each term with its committed source, when the committed values break it."

In scenarios.md, a new scenario MUST be added:

"## Scenario: a node's committed CPU requests fit its allocatable CPU with every churn slot in use

Given a pool node's committed churn-slot capacity, the runner CPU request, the nominal CPU quota of each gate lane that names the node, and the node's factory pod budget and the factory sandbox CPU request

When the aggregate's node CPU fit check runs

Then it MUST pass when the slots times the runner request, plus the gate lane quotas, plus the factory budget times the factory request, is at most the node's allocatable CPU
And it MUST fail, naming the node and each term with its committed source, when that sum exceeds the allocatable CPU"

The scenario "## Scenario: a node takes runner pods up to its declared churn-slot capacity and no fewer" MUST NOT change, and it MUST stay true: a non-runner pod's CPU request MUST NOT stop a runner pod from being placed while the node has a free churn slot.

tests/heading-coverage.json MUST gain an entry for the new scenario heading. It MAY be a spec-first `"test": "TODO"` row whose reason names the integration tier and the owning item livespec-dev-tooling-wirn53, with `"work_item": "livespec-dev-tooling-wirn53"`, registered in tests/heading-coverage-debt.json, as the repository's revise co-edit discipline requires.

## Proposal: The node-saturation rule reads the CPU pressure of the CI runner pods themselves, not of the BestEffort slice

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Contracts §"Placement by node pressure" reads the cpu.pressure of the BestEffort slice that holds the CI runner pods. Once runner pods request CPU they leave BestEffort for Burstable, which also holds gates and factory sandboxes. Change the reading to the CI runner pods' own pod cgroups: the mean of their cpu.pressure some avg60, and 0 on a node holding none. The threshold, the idle condition and every other rule of the bullet are unchanged.

### Motivation

The second proposal of this file moves runner pods out of the BestEffort QoS class. Under today's wording the gate placement reconciler would then read a slice that no longer holds the CI pods, and it would never see CI pressure. The same reading is plan gate-job-resources' instrument for its two-sided assertion: no node saturated while work queues, and no node idle while work queues. The rule's intent is CI pods waiting on CPU, recorded on livespec-dev-tooling-6e5pyj by the 2026-11-04 ruling. The pods' own cgroups carry that intent whatever their QoS class.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Placement by node pressure**, the reading "the CPU pressure (`cpu.pressure` `some` avg60) of the BestEffort slice that holds the CI runner pods (`kubepods.slice/kubepods-besteffort.slice`)" MUST be replaced by "the CPU pressure of the CI runner pods on that node: the mean of `cpu.pressure` `some` avg60 over the pod cgroups of the CI runner pods it holds, whichever QoS slice holds them, read as 0 when it holds none".

Every later reference in that bullet to "that slice pressure" or "the CI slice's pressure" MUST read as this CI-runner pod pressure. The saturation rule itself (idle under 5% while that pressure is above 30), the never-a-false-zero rule for an unread reading, the ALARM and exit-status behaviour, and the static-lane-order fallback MUST NOT change.

The sentence "The reconciler MUST NOT set a CPU request on CI runner pods" MUST be kept. The runner CPU request is set by the runner scale-set templates, never by the reconciler.

No H2 heading changes.
