---
topic: per-node-cpu-budget-honest-requests
author: claude-opus-5-5
created_at: 2026-11-13T20:39:00Z
---

## Proposal: The default gate request is 3 CPUs, each gate lane's CPU quota is the budget's gate share, and the gmktec lane floor follows the default

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Lower the renderer's default gate CPU request from 5 to 3, measured from gate pods' actual use, so most gates stop over-requesting.

The gmktec lane floor becomes three times the renderer's default and is no longer a literal 15 CPU. Each gate lane's CPU quota becomes the gate share the per-node CPU budget gives that lane's node, never below the floor, and the gate unit follows the default, so a lower default does not silently raise how many gates a node admits.

livespec-orchestrator-beads-fabro, whose gates use about 5 cores, must declare gate_cpu = 5 before the default changes.

### Motivation

Plan gate-job-resources (livespec-dev-tooling-ukoeah) was widened on the maintainer-approved ruling recorded on livespec-dev-tooling-6tgd2z at 2026-11-13T19:45:09Z. It now owns the per-node CPU budget, and the budget needs every class to request about what it uses.

Gate pods that ran longer than 2 minutes averaged:
- 2.9-3.4 cores for livespec-dev-tooling;
- 4.6-5.1 cores for livespec-orchestrator-beads-fabro;
- about 1-1.6 cores for every other repository.

Source: Honeycomb livespec/metrics, k8s.pod.cpu.usage, queries wQQrW3wJxKs, FbosoCKz9um, fDC9tmuJwKw and h6PRCH1Y7oX, 2026-11-12 19:00Z to 11-13 19:00Z.

The orchestrator declares no gate_cpu. Its pyproject.toml relies on the renderer default of 5, so lowering the default alone would cut its gates below their use.

Lane quotas are counted in CPU: gmktec's 15 is 3 x 5. A lower default with unchanged quotas would let gmktec admit 5 gates instead of 3, on a node that sat at or above capacity in 12 of 24 hours.

The default is 3 rather than 2 so that a full-size gate stays larger than the 2-CPU replay Job of Replay Job size, which plan assertion 2 depends on.

An independent live-state review of the first draft of this proposal found the missing orchestrator declaration and the quota effect.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Declared gate resources**: the sentence "A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4`" MUST read CPU `3` in place of CPU `5`. Memory and parallelism are unchanged.

A new sentence MUST follow that sentence: "The default MUST NOT be lowered while a fleet repository whose measured gate CPU use is above the new default relies on it. Such a repository MUST first declare its own `gate_cpu`, as livespec-orchestrator-beads-fabro MUST declare `gate_cpu = 5`."

In the same section, **Gate lane headroom** MUST read: "The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs: at least three times the renderer's default CPU request and at least three times its default memory request. It therefore admits at least three concurrent default-size gate Jobs." The literal "at least 15 CPU and at least 18Gi memory" is removed, and every other sentence of that bullet is kept.

A new sentence MUST be added to the same bullet: "Every gate lane's nominal CPU quota MUST equal the gate share that the committed per-node CPU budget gives that lane's node, and MUST NOT fall below this floor. The `ci-runner.io/gate-unit-cpu` annotation on `gates-cq` MUST equal the renderer's default CPU request. A change to the default MUST therefore re-derive each lane's quota in the same change, and MUST NOT leave a lane admitting more gates than its node's gate share."

In scenarios.md, the body of "## Scenario: a repository that declares no gate resources keeps the default gate Job size" MUST read "Then the Job's container MUST request 3 CPUs and request and limit memory `6Gi`". The heading and the parallelism line are unchanged.

The scenario "## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs" already asserts the derivation and MUST NOT change.

No H2 heading is added, renamed or removed by this section.

## Proposal: The CI job's workflow pod requests its CPU, runner pods request none, and each pool node's committed CPU requests fit its allocatable CPU

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Give the CI job's WORKFLOW pod a real CPU request on its job container; the container hook creates that pod and binds it to the runner pod's node by name. Runner pods keep requesting no CPU.

The result:
- churn-slot capacity stays literally the only per-node limit on runner pods;
- fail-open placement is unaffected;
- the pods doing the CI work leave BestEffort and gain CPU weight under contention.

A kubelet still refuses a name-bound pod with OutOfcpu when its node's requests are full. A new clause therefore requires each pool node's committed CPU requests to fit its allocatable CPU with every churn slot in use. It is spec-first: it is armed only in the change that commits budget values satisfying it, because today's committed values break it on three nodes. One scenario and one heading-coverage entry ship with it.

### Motivation

Same ruling and plan as the first proposal. On gmktec-xubuntu the CI class averaged 10.6 concurrent cores over 24 hours at a request of 0 (W1-W4: 11.2, 12.0, 10.8, 8.3; queries GeJPtsYP2y8, 9HcAtrYUHGZ, y4PSHW5Bwnj, p4JpAQGQcsU). That is the largest class on a node that sat at or above capacity in 12 of the 24 hours. Measured cost per CI job is about 1.7 cores on gmktec, 1.9 on poweredge and 2.0 on hp.

The first draft put the request on the RUNNER container. An independent live-state review showed four problems with that:
- CI work runs in the workflow pod (containerMode: kubernetes, hook-pod-template.yaml), so a request there gives the mostly idle runner pod the weight while the working pod stays BestEffort.
- The committed runner scheduler profile uses NodeResourcesFit, whose filter always checks CPU (ignoredResources skips only extended resources), so it cannot ignore a runner CPU request.
- Fail-open hands runner pods to the default scheduler, which does filter by CPU.
- Today's committed values already exceed allocatable CPU: gmktec's gate lane 15 plus its factory budget 7 x 3 is 36 of 32, before any runner request.

Putting the request on the workflow pod avoids the first three. The fourth is why the fit clause is armed only with the values that satisfy it, per the repository's ordering rule (adoption first, then arming). This ALIGNS with the pending proposal runner-placement-post-add-tie: it adds sentences and changes none of that proposal's wording.

### Proposed Changes

In non-functional-requirements.md, the paragraph **Runner placement follows admission capacity.** MUST gain these sentences after its existing text:

"A CI runner pod MUST NOT request CPU. The CPU a CI job uses MUST instead be requested by the job container of the workflow pod that the runner's container hook creates and binds to the runner pod's node. That request is the pool's CPU per CI job: one fleet-wide value taken from the committed per-node CPU budget, and every runner scale set's hook pod template MUST carry exactly that value. A check in the aggregate MUST fail when any hook pod template's job-container CPU request differs from the budget's value. Because the runner pod requests no CPU, its placement by the runner scheduler profile, and by the default scheduler when placement fails open, never depends on CPU."

A new paragraph MUST follow it:

"**Each pool node's CPU requests fit its allocatable CPU.** A pool node is a node with a declared churn-slot capacity, including a worker that `converge-worker-queues.sh` enrolls at converge time. For every pool node, the sum of the following MUST NOT exceed that node's allocatable CPU:

1. its declared churn-slot capacity times the CI job CPU request;
2. the nominal CPU quota of every gate lane whose flavor names that node;
3. its factory pod budget times the largest committed sandbox CPU request of any factory instance that can place on it;
4. the CPU requests of every other committed workload that is placed on it.

This is the condition under which the kubelet never refuses a CI job's workflow pod for CPU while the node has a free churn slot. A check in the aggregate MUST fail, naming the node and each term with its committed source, when the committed values break it. This paragraph is spec-first: livespec-dev-tooling-wirn53 owns it. The check, and the workflow-pod CPU request above, MUST be armed only in the change that commits budget values satisfying it on every pool node, and never before."

In scenarios.md, a new scenario MUST be added:

"## Scenario: a pool node's committed CPU requests fit its allocatable CPU with every churn slot in use

Given a pool node's committed churn-slot capacity, the CI job CPU request, the nominal CPU quota of each gate lane that names the node, the node's factory pod budget and the largest sandbox CPU request of any factory instance that can place on it, and the CPU requests of every other committed workload placed on it

When the aggregate's node CPU fit check runs

Then it MUST pass when the sum of those terms is at most the node's allocatable CPU
And it MUST fail, naming the node and each term with its committed source, when the sum exceeds the allocatable CPU"

The scenario "## Scenario: a node takes runner pods up to its declared churn-slot capacity and no fewer" MUST NOT change, and MUST stay true.

tests/heading-coverage.json MUST gain an entry for the new scenario heading. It MAY be a spec-first `"test": "TODO"` row whose reason names the integration tier and the owning item livespec-dev-tooling-wirn53, with `"work_item": "livespec-dev-tooling-wirn53"`. The row MUST be registered in the heading-coverage debt register by `just generate-heading-coverage-debt-register`, as the repository's revise co-edit discipline requires.

## Proposal: The node-saturation rule reads the CPU pressure of the CI job's workflow pods

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Contracts §"Placement by node pressure" reads cpu.pressure on the BestEffort slice, which it says holds the CI runner pods. The second section of this proposal moves the pods that do the CI work, the workflow pods, out of BestEffort. Change the reading to the highest cpu.pressure some avg60 among the CI workflow pods' own pod cgroups on the node, read as 0 when the node holds none. The threshold, the idle condition and every other rule of the bullet are unchanged.

### Motivation

Today the BestEffort slice is the right reading because the workflow pods doing the CI work are BestEffort. Once they request CPU they leave that slice, and the gate placement reconciler would stop seeing CI pressure. The same reading is plan gate-job-resources' instrument for its two-sided assertion: no node saturated while work queues, and no node idle while work queues.

The first draft named the runner pods. An independent live-state review showed those mostly measure an idle agent, because CI work runs in the workflow pod. It also recommended the maximum over the mean, so that one starved job is not diluted among idle ones. Per-pod cpu.pressure exists under the nodes' systemd cgroup driver (read on poweredge-xubuntu). A node-local reader needs a pod lookup, through the API or the container runtime, to tell which pod cgroups are CI workflow pods.

The rule's intent, CI pods waiting on CPU, comes from the 2026-11-04 coordinator ruling recorded on livespec-dev-tooling-6e5pyj.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Placement by node pressure**: the reading "the CPU pressure (`cpu.pressure` `some` avg60) of the BestEffort slice that holds the CI runner pods (`kubepods.slice/kubepods-besteffort.slice`)" MUST be replaced by "the CPU pressure of the CI jobs on that node: the highest `cpu.pressure` `some` avg60 among the pod cgroups of the CI workflow pods it holds (the pods the runner container hook creates), whichever QoS slice holds them, read as 0 when it holds none".

Every later reference in that bullet to "that slice pressure" or "the CI slice's pressure" MUST read as this CI workflow-pod pressure. The following MUST NOT change:
- the saturation rule itself: idle under 5% while that pressure is above 30;
- the never-a-false-zero rule for an unread reading;
- the ALARM and exit-status behaviour;
- the static-lane-order fallback.

The sentence "The reconciler MUST NOT set a CPU request on CI runner pods" MUST be kept.

This change MUST land with the workflow-pod CPU request of the second section, never before it. Until that request is armed the workflow pods are BestEffort and the two readings name the same pods.

No H2 heading changes.
