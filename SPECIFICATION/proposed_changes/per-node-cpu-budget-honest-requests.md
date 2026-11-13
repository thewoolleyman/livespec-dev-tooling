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

Lower the renderer's default gate CPU request from 5 to 3. The new value comes from what gate pods actually use, so most gates stop over-requesting.

The gmktec lane floor becomes three times the renderer's default, no longer a literal 15 CPU. Every other gate lane keeps at least one default-size gate. Each lane's CPU quota becomes the gate share that the committed per-node CPU budget gives that lane's node, and the gate unit follows the default. A lower default therefore does not silently raise how many gates a node admits.

livespec-orchestrator-beads-fabro must declare gate_cpu = 5 in a merged change before the default moves.

### Motivation

Plan gate-job-resources (livespec-dev-tooling-ukoeah) was widened on the maintainer-approved ruling recorded on livespec-dev-tooling-6tgd2z at 2026-11-13T19:45:09Z. It now owns the per-node CPU budget, which needs every class to request about what it uses.

Measured gate use (Honeycomb livespec/metrics, `k8s.pod.cpu.usage`, per-pod mean over gate pods that ran longer than 2 minutes, 2026-11-12 19:00Z to 11-13 19:00Z; queries wQQrW3wJxKs, FbosoCKz9um, fDC9tmuJwKw, h6PRCH1Y7oX):

| Repository | Mean cores per gate pod |
|---|---|
| livespec-dev-tooling | 2.9-3.4 |
| livespec-orchestrator-beads-fabro | 4.6-5.1 |
| every other repository | about 1-1.6 |

The orchestrator declares no gate_cpu. Its pyproject.toml relies on the renderer default of 5, so lowering the default alone would cut its gates below their use.

Lane quotas are counted in CPU. gmktec's 15 is 3 x 5, so a lower default with unchanged quotas would let gmktec admit 5 gates instead of 3, on a node that sat at or above capacity in 12 of 24 hours.

The re-derived lanes are gmktec 9, poweredge 21, hp 3 and gamingpc 3, each three times the new unit or a multiple of it. A container-worker lane that `converge-worker-queues.sh` enrolls is already a multiple of the gate unit, so it follows the unit with no edit. Replayed over the last 24 hours of gate pods (query dbbVLi5S76A, 5-minute buckets, orchestrator gates at 5 and every other gate at 3, packed into those lanes), the new lanes leave about 195 more pod-minutes a day waiting than today's lanes do. That is 1.8% of gate pod-time, concentrated in 32 of 273 buckets.

The default is 3 rather than 2 so that a full-size gate stays larger than the 2-CPU replay Job of **Replay Job size**, which plan assertion 2 depends on.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Declared gate resources**: in the sentence "A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4`", CPU `5` MUST become CPU `3`. Memory and parallelism are unchanged.

A new sentence MUST follow that sentence: "The renderer's default CPU MUST NOT be lowered before every fleet repository whose gates use more than the new default has declared its own `gate_cpu` in a merged change. Use is measured as the mean `k8s.pod.cpu.usage` per gate pod, over gate pods that ran longer than 2 minutes, across the 24 hours before the change. For the move from 5 to 3, livespec-orchestrator-beads-fabro MUST first declare `gate_cpu = 5`."

In the same section, **Gate lane headroom** MUST read: "The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs: at least three times the renderer's default CPU request, and at least three times its default memory request. It therefore admits at least three concurrent default-size gate Jobs. Every other gate lane MUST keep a nominal quota of at least one default-size gate Job." The literal "at least 15 CPU and at least 18Gi memory" is removed, and every other sentence of that bullet is kept.

A new sentence MUST be added to the same bullet: "Every committed gate lane's nominal CPU quota MUST equal the `gate_cpu` value that `ci-runner/k3s/phase2/node-cpu-budget.yaml` gives that lane's node, and MUST NOT fall below that lane's floor above. The `ci-runner.io/gate-unit-cpu` annotation on `gates-cq` MUST equal the renderer's default CPU request. A change to the default MUST therefore change, in the same commit, the annotation, every committed lane's quota and the budget file's `gate_cpu` values. Every lane MUST stay a whole multiple of the gate unit."

In the same section, **Placement by node pressure**: the clause "which the pool's lane-size derivation owns" MUST read "which the committed per-node CPU budget owns (**Gate lane headroom**)".

In scenarios.md, the body of "## Scenario: a repository that declares no gate resources keeps the default gate Job size" MUST read "Then the Job's container MUST request 3 CPUs and request and limit memory `6Gi`". The heading and the parallelism line are unchanged.

The scenario "## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs" already asserts the derivation and MUST NOT change.

No H2 heading is added, renamed or removed by this section.

## Proposal: The CI job's workflow pod requests its CPU, runner pods request none, and each pool node's committed CPU requests fit its allocatable CPU

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Give the CI job's WORKFLOW pod a real CPU request on its job container. The runner's container hook creates that pod and binds it to the runner pod's node by name. Runner pods keep requesting no CPU.

The result:
- churn-slot capacity stays literally the only per-node limit on runner pods;
- fail-open placement is unaffected;
- the pods doing the CI work leave BestEffort and gain CPU weight under contention.

A kubelet still refuses a pod bound by name with OutOfcpu when its node's requests are full. A new clause therefore requires each pool node's committed CPU requests to fit its allocatable CPU with every churn slot in use. Every term of that sum is read from a named committed file.

The clause is spec-first. It is armed only in the change that commits values satisfying it, because today's committed values break it on every pool node. One scenario and one heading-coverage entry ship with it.

### Motivation

Same ruling and plan as the first proposal.

CI work runs in the workflow pod (containerMode: kubernetes, `ci-runner/k3s/phase2/arc/hook-pod-template.yaml`). All 17 runner values files mount that one template through the `arc-hook-pod-template-<revision>` ConfigMap that `converge-hook-pod-template.sh` renders.

Measured per pod (query FLoxCmwxT76; 2026-11-12 19:00Z to 11-13 01:00Z; 120-second buckets; cores = SUM / 180, pods = COUNT_DATAPOINTS / 720):

| Node | Workflow pod cores | Runner pod cores |
|---|---|---|
| poweredge | 1.40 | 0.06 |
| gmktec | 1.69 | 0.07 |
| hp | 1.78 | 0.10 |

The pod-weighted fleet value is 1.54 cores per workflow pod, so the CI job CPU request is 1.5. The runner pod is an idle agent.

The first draft put the request on the RUNNER container. An independent live-state review showed four problems with that:
- A request on the runner gives the weight to a mostly idle pod, while the working pod stays BestEffort.
- The committed runner scheduler profile uses NodeResourcesFit, whose filter always checks CPU, so it cannot ignore a runner CPU request.
- Fail-open hands runner pods to the default scheduler, which also filters by CPU.
- The committed values already exceed allocatable CPU.

Putting the request on the workflow pod avoids the first three. The fourth is why the fit clause is armed only with values that satisfy it, per the repository's ordering rule (adoption first, then arming).

Committed request sums, with every churn slot in use at 1.5 cores per CI job and each factory pod at its 3-CPU sandbox request:

| Node | Allocatable | Today | Budgeted |
|---|---|---|---|
| gmktec-xubuntu | 32 | 46.1 (6 slots 9 + lane 15 + 7 factory 21 + other 1.1) | 31.1 (9 + 9 + 4 factory 12 + 1.1) |
| poweredge-xubuntu | 72 | 83.8 (17 slots 25.5 + 30 + 9 factory 27 + 1.3) | 71.8 (25.5 + 21 + 8 factory 24 + 1.3) |
| hp-xubuntu | 14.5 | 17.6 (4 slots 6 + 5 + 2 factory 6 + 0.6) | 12.6 (6 + 3 + 1 factory 3 + 0.6) |
| gamingpc-xubuntu | 12 | 12.5 (3 slots 4.5 + 5 + 1 factory 3) | 10.5 (4.5 + 3 + 3) |

"Other" is the live CPU requests of every other running workload on the node (ci-warm-cache, kueue, kube-system and the CI cache singletons), read 2026-11-13 ~20:5xZ.

The budgeted factory pod budgets cost factory throughput. Over the last 24 hours of factory pods (query 764UoV97fVs), an x86 factory budget of 14 instead of today's 19 would have held about 12% of factory pod-time in queue, about 1,950 pod-minutes a day. That figure is recorded so the cost is decided knowingly.

This ALIGNS with the pending proposal runner-placement-post-add-tie. It adds sentences after that paragraph's first sentence, which is the only one that proposal changes.

### Proposed Changes

In non-functional-requirements.md, the paragraph **Runner placement follows admission capacity.** MUST gain these sentences after its existing text:

"A CI runner pod MUST NOT request CPU. The CPU a CI job uses MUST instead be requested by the job container of the workflow pod that the runner's container hook creates and binds to the runner pod's node. That request is the pool's CI job CPU: the `ci_job_cpu` value of `ci-runner/k3s/phase2/node-cpu-budget.yaml`. The one committed hook pod template, `ci-runner/k3s/phase2/arc/hook-pod-template.yaml`, MUST carry exactly that value as its job container's CPU request, and every runner values file MUST mount that template. A check in the aggregate MUST fail when the template's job-container CPU request differs from `ci_job_cpu`, or when a runner values file mounts a different template. Because the runner pod requests no CPU, its placement never depends on CPU, whether the runner scheduler profile places it or the default scheduler does when placement fails open."

A new paragraph MUST follow it:

"**Each pool node's CPU requests fit its allocatable CPU.** A pool node is a node with a declared churn-slot capacity, including a worker that `converge-worker-queues.sh` enrolls at converge time. `ci-runner/k3s/phase2/node-cpu-budget.yaml` MUST list every pool node, with its `allocatable_cpu` and its `other_workloads`. Each entry of `other_workloads` names one workload placed on that node and its CPU request. Where this repository commits the workload's manifest, the entry also names that manifest. A workload the cluster distribution installs, such as k3s's kube-system pods, carries its request as read from the live node. For every pool node, the sum of these terms MUST NOT exceed `allocatable_cpu`:

1. its churn-slot capacity (`ADMISSION_CAPACITY_C` in `ci-runner/k3s/phase0-bare-metal/profiles/<node>.env`) times `ci_job_cpu`;
2. the nominal CPU quota of every gate lane in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml` whose flavor names that node, or, for an enrolled worker, the lane `converge-worker-queues.sh` derives for it;
3. its `factory_pod_budget` (`ansible/inventory/host_vars/<node>.yml`) times the largest committed sandbox CPU request of any factory instance that can place on it;
4. the CPU requests its `other_workloads` entries list.

This is the condition under which the kubelet never refuses a CI job's workflow pod for CPU while the node has a free churn slot. A check in the aggregate MUST fail when the committed values break it, naming the node and each term with its committed source. It MUST also fail when an `other_workloads` entry that names a manifest differs from the request in that manifest.

The converge MUST compare each node's `allocatable_cpu` with the kubelet's reported allocatable CPU, and MUST report a difference as a failure naming the node and both values.

This paragraph is spec-first: livespec-dev-tooling-wirn53 owns it. The fit check, the template check and the workflow-pod CPU request MUST be armed together. They MUST be armed in the change that commits budget values satisfying the fit on every pool node, and never before."

In scenarios.md, a new scenario MUST be added:

"## Scenario: a pool node's committed CPU requests fit its allocatable CPU with every churn slot in use

Given `ci-runner/k3s/phase2/node-cpu-budget.yaml` lists a pool node with its `allocatable_cpu` and its `other_workloads`
And the node's committed churn-slot capacity, the budget's `ci_job_cpu`, the nominal CPU quota of each gate lane that names the node, the node's `factory_pod_budget`, and the largest sandbox CPU request of any factory instance that can place on it

When the aggregate's node CPU fit check runs

Then it MUST pass when the sum of those terms is at most the node's `allocatable_cpu`
And it MUST fail, naming the node and each term with its committed source, when the sum exceeds the node's `allocatable_cpu`"

The scenario "## Scenario: a node takes runner pods up to its declared churn-slot capacity and no fewer" MUST NOT change, and MUST stay true.

tests/heading-coverage.json MUST gain an entry for the new scenario heading. It MAY be a spec-first `"test": "TODO"` row whose reason names the integration tier and the owning item livespec-dev-tooling-wirn53, with `"work_item": "livespec-dev-tooling-wirn53"`. The row MUST be registered in the heading-coverage debt register by `just generate-heading-coverage-debt-register`, as the repository's revise co-edit discipline requires.

## Proposal: The node-saturation rule reads the CPU pressure of the CI job's workflow pods

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Contracts §"Placement by node pressure" reads cpu.pressure on the BestEffort slice, which it says holds the CI runner pods. The second section of this proposal moves the pods that do the CI work, the workflow pods, out of BestEffort.

This section changes the reading to the highest cpu.pressure `some` avg60 among the CI workflow pods' own pod cgroups on the node. A node holding none reads 0. A node whose workflow pods cannot be identified is an unread reading, never 0. The saturation threshold becomes a committed value with 30 as its initial value, and it is re-measured before this section is armed.

### Motivation

Today the BestEffort slice is the right reading, because the workflow pods doing the CI work are BestEffort. Once they request CPU they leave that slice, and the gate placement reconciler would stop seeing CI pressure. The same reading is plan gate-job-resources' instrument for its two-sided assertion: no node saturated while work queues, and no node idle while work queues.

The first draft named the runner pods. An independent live-state review showed those mostly measure an idle agent (0.06-0.10 cores per pod), because CI work runs in the workflow pod. It also recommended the maximum over the mean, so that one starved job is not diluted among idle ones.

Per-pod cpu.pressure exists under the nodes' systemd cgroup driver (read on poweredge-xubuntu). A Burstable workflow pod's file is `/sys/fs/cgroup/kubepods.slice/kubepods-burstable.slice/kubepods-burstable-pod<uid>.slice/cpu.pressure`, with the pod UID's dashes written as underscores. A node-local reader needs a pod lookup, through the API or the container runtime, to tell which pod cgroups are CI workflow pods.

The threshold of 30 was set against the whole BestEffort slice. The highest single pod reads at least as high as a slice that holds it, so carrying 30 over unchanged would classify more nodes as saturated. The threshold is therefore made a committed value, and the arming change must record both readings side by side over 24 hours and set it from that record.

The rule's intent, CI pods waiting on CPU, comes from the 2026-11-04 coordinator ruling recorded on livespec-dev-tooling-6e5pyj.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Placement by node pressure**: the reading "the CPU pressure (`cpu.pressure` `some` avg60) of the BestEffort slice that holds the CI runner pods (`kubepods.slice/kubepods-besteffort.slice`)" MUST be replaced by this text: "the CPU pressure of the CI jobs on that node: the highest `cpu.pressure` `some` avg60 among the pod cgroups of the CI workflow pods it holds, whichever QoS slice holds them. The CI workflow pods are the pods the runner container hook creates. For a Burstable pod that cgroup is `kubepods.slice/kubepods-burstable.slice/kubepods-burstable-pod<uid>.slice`, with the pod UID's dashes written as underscores. A node that holds no CI workflow pod reads 0. A node whose CI workflow pods cannot be identified, because the pod lookup failed, has an unread reading, never 0."

The text "that slice pressure avg60 is above 30" MUST read "that CI-job pressure avg60 is above the `saturation_pressure_threshold` of `ci-runner/k3s/phase2/node-cpu-budget.yaml`, whose initial value is 30". A new sentence MUST follow: "The change that arms this reading MUST record the BestEffort-slice reading and this reading side by side for every gate-lane node over 24 hours. It MUST set `saturation_pressure_threshold` from that record."

Every later reference in that bullet to "that slice pressure" or "the CI slice's pressure" MUST read as this CI-job pressure. The following MUST NOT change:
- the idle condition of the saturation rule: idle under 5%;
- the never-a-false-zero rule for an unread reading;
- the ALARM and exit-status behaviour;
- the static-lane-order fallback.

The sentence "The reconciler MUST NOT set a CPU request on CI runner pods" MUST be kept.

This change MUST land with the workflow-pod CPU request of the second section, never before it. Until that request is armed the workflow pods are BestEffort and the two readings name the same pods.

No H2 heading changes.
