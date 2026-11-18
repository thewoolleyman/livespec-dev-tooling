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

The orchestrator declares no gate_cpu. Its pyproject.toml relies on the renderer default of 5, so lowering the default alone would cut its gates below their use. livespec-dev-tooling's gates use about 3.3 cores by the CPU-time counter `k8s.pod.cpu.time`. The usage gauge reads 3.43 (query toTHf66TeNu), and the counter reads gate cores about 3% lower (query aYYXAQE8FcA). 3.3 rounds to the new default, so it need not declare.

Lane quotas are counted in CPU. gmktec's 15 is 3 x 5, so a lower default with unchanged quotas would let gmktec admit 5 gates instead of 3, on a node that sat at or above capacity in 12 of 24 hours.

The re-derived lanes are gmktec 9, poweredge 21, hp 3 and gamingpc 3, each a whole multiple of the new unit. A container-worker lane that `converge-worker-queues.sh` enrolls is already a multiple of the gate unit, so it follows the unit with no edit. Replayed over the last 24 hours of gate pods (query dbbVLi5S76A, 5-minute buckets, orchestrator gates at 5 and every other gate at 3, packed into those lanes), the new lanes leave about 195 more pod-minutes a day waiting than today's lanes do. That is 1.8% of gate pod-time, concentrated in 32 of 273 buckets.

The default is 3 rather than 2 so that a full-size gate stays larger than the 2-CPU replay Job of **Replay Job size**, which plan assertion 2 depends on.

### Proposed Changes

In contracts.md §"Delegated pre-push gate", **Declared gate resources**: in the sentence "A key that is absent MUST leave that Job at the default the renderer carries: CPU `5`, memory `6Gi`, parallelism `4`", CPU `5` MUST become CPU `3`. Memory and parallelism are unchanged.

A new sentence MUST follow that sentence: "The renderer's default CPU MUST NOT be lowered before every fleet repository whose measured gate use, rounded to the nearest whole CPU, is above the new default has declared its own `gate_cpu` in a merged change. Measured gate use is the mean CPU per gate pod, over gate pods that ran longer than 2 minutes, across the 24 hours before the change, taken from the pod CPU-time counter (`k8s.pod.cpu.time`). For the move from 5 to 3, livespec-orchestrator-beads-fabro MUST first declare `gate_cpu = 5`."

In the same section, **Gate lane headroom** MUST read: "The committed `gates-flavor` lane (gmktec-xubuntu) of `cluster-queue-gates.yaml` MUST keep a nominal quota of at least three default-size gate Jobs: at least three times the renderer's default CPU request, and at least three times its default memory request. It therefore admits at least three concurrent default-size gate Jobs. Every other gate lane MUST keep a nominal quota of at least one default-size gate Job." The literal "at least 15 CPU and at least 18Gi memory" is removed, and every other sentence of that bullet is kept.

A new sentence MUST be added to the same bullet: "Every committed gate lane's nominal CPU quota MUST equal the `gate_cpu` value that `ci-runner/k3s/phase2/node-cpu-budget.yaml` gives that lane's node, and MUST NOT fall below that lane's floor above. The `ci-runner.io/gate-unit-cpu` annotation on `gates-cq` MUST equal the renderer's default CPU request. A change to the default MUST therefore change, in the same commit, the annotation, every committed lane's quota and the budget file's `gate_cpu` values. Every lane's CPU quota MUST stay a whole multiple of the gate unit's CPU (`ci-runner.io/gate-unit-cpu`)."

In the same section, **Placement by node pressure**: the clause "which the pool's lane-size derivation owns" MUST read "which the committed per-node CPU budget owns (**Gate lane headroom**)".

In scenarios.md, the body of "## Scenario: a repository that declares no gate resources keeps the default gate Job size" MUST read "Then the Job's container MUST request 3 CPUs and request and limit memory `6Gi`". The heading and the parallelism line are unchanged.

The scenario "## Scenario: the gmktec gate lane keeps room for three default-size gate Jobs" already asserts the derivation and MUST NOT change.

No H2 heading is added, renamed or removed by this section.
