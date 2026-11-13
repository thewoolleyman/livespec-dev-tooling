# Per-node CPU budget for the self-hosted pool

This is the ONE budget from which every CPU-bearing cap of the pool derives:

- each node's CI churn-slot capacity (`ADMISSION_CAPACITY_C` in
  `../phase0-bare-metal/profiles/<node>.env`);
- each gate lane's cpu quota (`kueue/cluster-queue-gates.yaml`);
- each node's factory pod budget (`factory_pod_budget` in
  `ansible/inventory/host_vars/<node>.yml`);
- the CI job's workflow-pod CPU request (`arc/hook-pod-template.yaml`).

Its machine-readable form is `node-cpu-budget.yaml` beside this file.

It covers four classes on every pool node: gates, factory sandboxes, CI runners
and the system. Plan `gate-job-resources` owns it (epic
`livespec-dev-tooling-ukoeah`, carrier map 5, 2026-11-13). It is INTERIM: the duty
ends when the radar re-architecture's load-management role takes it. The ruling is
recorded on `livespec-dev-tooling-6tgd2z` at 2026-11-13T19:45:09Z: "the classes
together fit each node, and no node sits idle while work waits".

A change to one of the caps above is made HERE first. The cap's own file then
follows. Each cap keeps its own owner:

| Cap | Owner | Work item |
|---|---|---|
| Churn slots | ci-runtime-and-cost | `livespec-dev-tooling-6e5pyj` |
| Gate lanes | this plan | `livespec-dev-tooling-wirn53` |
| Factory pod budgets | this plan | `livespec-dev-tooling-wirn53` |

## The rule

The budget has two halves. Each answers a different question.

**Use: do the classes fit when they run?** For each node:

    usable = allocatable CPU - measured system.slice share
    usable >= runner use + gate use + factory use

- Each class's use is MEASURED (the tables below), not read from requests.
- **Requests understate use.** CI pods request 0 CPU today. A gate requesting 5
  has used up to 26 cores (per-pod max, below). So the scheduler alone cannot
  keep a node inside its budget, and the budget sets the caps.
- **The sum must fit at the peak hours, not only on the 24-hour average.** The
  pool's saturation rule is idle under 5% while CI `cpu.pressure` `some` avg60
  is over 30 (contracts §"Placement by node pressure"). Past that point every
  extra job only lengthens every job (`.ai/ci-node-capacity-reads.md`).

**Requests: can the kubelet always admit a CI job?** Once the CI job's workflow
pod requests CPU, the kubelet refuses it with OutOfcpu when its node's requests
are full. The workflow pod is bound to the runner's node by name, so no scheduler
can move it. With every churn slot in use, each node must therefore satisfy:

    churn slots x ci_job_cpu
    + gate lane cpu quota
    + factory_pod_budget x factory sandbox request
    + other workloads' requests
    <= allocatable CPU

`node-cpu-budget.yaml` beside this file holds every term in machine-readable
form. It names the cap files that must equal its values and shows each node's
sum. The fit is a clause of the pending proposal
`per-node-cpu-budget-honest-requests` (livespec-dev-tooling#4565), and its check
is armed only with values that satisfy it.

## Measurements (2026-11-12 19:00Z to 2026-11-13 19:00Z)

Source: Honeycomb `livespec/metrics`, `k8s.pod.cpu.usage`, read by the
kubernetes-observability seat in four 6-hour windows. A 6-hour window gets
120-second buckets; 5-minute buckets keep one late sample, not a mean, and
read high.

| Window | Query |
|---|---|
| W1 | `GeJPtsYP2y8` |
| W2 | `9HcAtrYUHGZ` |
| W3 | `y4PSHW5Bwnj` |
| W4 | `p4JpAQGQcsU` |

The arithmetic: cores = SUM / 180, and pods = COUNT_DATAPOINTS / 720, which is
exact because there is one sample per pod per 30 s.

### Average concurrent cores per class (W1 / W2 / W3 / W4; mean)

| Node | CI runners | Gates | Factory |
|---|---|---|---|
| gmktec-xubuntu | 11.2 / 12.0 / 10.8 / 8.3; 10.6 | 9.0 / 9.2 / 6.9 / 4.5; 7.4 | 8.2 / 6.7 / 8.9 / 10.0; 8.4 |
| poweredge-xubuntu | 21.7 / 27.5 / 30.6 / 23.8; 25.9 | 21.1 / 21.9 / 13.9 / 11.3; 17.1 | 17.0 / 10.7 / 17.7 / 22.1; 16.9 |
| hp-xubuntu | 7.6 / 7.7 / 7.9 / 6.3; 7.4 | 2.9 / 3.4 / 1.1 / 0.8; 2.0 | 3.4 / 2.9 / 3.2 / 3.5; 3.3 |
| gamingpc-xubuntu | 0.3 / 0.5 / 0.7 / 0.3; 0.5 | 0.7 / 1.7 / 0.6 / 0.0; 0.8 | 0.9 / 0.8 / 0.8 / 1.3; 0.9 |
| macbook-m4-max-homelab-worker | 0.6 / 1.1 / 0.5 / 0.8; 0.7 | 1.6 / 2.3 / 1.9 / 1.1; 1.7 | - / - / 0.6 / 0.9; 0.4 |

poweredge's gate pod count includes the always-on git-gates server, which runs at
about 0.01 cores. Subtract one pod there.

### Per-pod cores (24 h, p50 / p95 / max; query `3RaRVWfjSsL`)

| Class | gmktec | poweredge | hp |
|---|---|---|---|
| CI runners | 0.08 / 2.03 / 8.27 | 0.27 / 2.41 / 11.90 | 0.28 / 2.36 / 9.42 |
| Gates | 1.00 / 6.68 / 13.82 | 1.00 / 8.88 / 26.28 | 1.00 / 6.30 / 10.91 |
| Factory | 2.03 / 5.97 / 6.01 | 2.94 / 5.97 / 6.02 | 2.06 / 5.75 / 6.00 |

Factory pods stop at 6.0 cores on every x86 node, which is their CPU limit, so the
factory class is limit-bound at its p95.

### Gates by repository

Gate pods running longer than 2 minutes. Queries: `bUCpzfEtqA9`, and
`wQQrW3wJxKs` / `FbosoCKz9um` / `fDC9tmuJwKw` / `h6PRCH1Y7oX` (W1 to W4).

| Repository | Per-pod mean cores, p50 across W1-W4 | p95 | Per-pod max |
|---|---|---|---|
| livespec-dev-tooling | 2.9 to 3.4 | 4.3 to 5.7 | up to 17 |
| livespec-orchestrator-beads-fabro | 4.6 to 5.1 | 6.4 to 9.6 | up to 16 |
| livespec-overseer | about 1.3 to 1.6 | | |
| every other repository | about 1 | | |

The renderer's 5-cpu default is honest for the orchestrator's gate and overstates
every other repository's.

### System share and node saturation (host read, 10 s, 2026-11-13 ~19:58Z)

These are `usage_usec` deltas of `kubepods.slice` and `system.slice`, with idle
taken from `/proc/stat`. The pressure column is a 10-second spot read of
`full avg10` on the BestEffort slice. It is NOT the saturation rule's
`some avg60`, and it only shows which node was starving at that moment.

| Node | Allocatable | Idle | kubepods cores | system.slice cores | BestEffort full avg10 (spot) |
|---|---|---|---|---|---|
| gmktec-xubuntu | 32 | 0.7% | 30.6 | 1.6 | 31.0 |
| poweredge-xubuntu | 72 | 2.9% | 63.1 | 5.7 | 8.1 |
| hp-xubuntu | 14.5 | 12.9% | 12.4 | 1.2 | 3.4 |

gmktec class demand sat at or above capacity in 12 of the 24 hours (20Z, 22Z,
01-03Z, 05-08Z, 13Z, 17Z, 18Z).

### Cores per CI job: the workflow pod

Each CI job is one runner pod and one workflow pod. The workflow pod is the one
the container hook creates, named `<runner>-workflow`. The two are measured
apart in query `FLoxCmwxT76` (W1, 120-second buckets):

| Node | Workflow pod cores (mean per pod) | Runner pod cores |
|---|---|---|
| poweredge | 1.40 | 0.06 |
| gmktec | 1.69 | 0.07 |
| hp | 1.78 | 0.10 |

The pod-weighted fleet value is 1.54, so `ci_job_cpu` is **1.5**. The runner pod
is an idle agent. Do not read per-pod CPU from a 24-hour query: its 15-minute
buckets keep one late sample per pod and read the workflow pod at 0.77-1.00
(query `4X3sgRmarYY`).

### Other workloads' requests (live, 2026-11-13 ~20:5xZ)

| Node | Requests outside gates, factory and CI |
|---|---|
| gmktec-xubuntu | 1.1 (ci-warm-cache 0.5, kueue 0.5, kube-system 0.1) |
| poweredge-xubuntu | 1.3 (kueue 0.5, kube-system 0.3, sccache 0.25, crates proxy 0.1, registry mirror 0.1, warm cache 0.05) |
| hp-xubuntu | 0.6 (ci-warm-cache 0.5, kube-system 0.1) |
| gamingpc-xubuntu | 0 |
| macbook-m4-max-homelab-worker | 0.1 |

## The budget (cores)

Decided by plan gate-job-resources, 2026-11-13 ~21:3xZ. Today's values are the
committed caps after the `6e5pyj` slot cut.

| Node | Allocatable | Slots | Gate lane (was) | Factory pods (was) | Other | Request fit, today | Request fit, budgeted |
|---|---|---|---|---|---|---|---|
| gmktec-xubuntu | 32 | 6 | **9** (15) | **4** (7) | 1.1 | 9 + 15 + 21 + 1.1 = 46.1 | 9 + 9 + 12 + 1.1 = **31.1** |
| poweredge-xubuntu | 72 | 17 | **21** (30) | **8** (9) | 1.3 | 25.5 + 30 + 27 + 1.3 = 83.8 | 25.5 + 21 + 24 + 1.3 = **71.8** |
| hp-xubuntu | 14.5 | 4 | **3** (5) | **1** (2) | 0.6 | 6 + 5 + 6 + 0.6 = 17.6 | 6 + 3 + 3 + 0.6 = **12.6** |
| gamingpc-xubuntu | 12 | 3 | **3** (5) | 1 | 0 | 4.5 + 5 + 3 = 12.5 | 4.5 + 3 + 3 = **10.5** |
| macbook-m4-max-homelab-worker | 12 | 1 | 3 (5) | 1 | 0.1 | 1.5 + 5 + 3 + 0.1 = 9.6 | 1.5 + 3 + 3 + 0.1 = **7.6** |

Slots are counted at `ci_job_cpu` 1.5 and factory pods at the 3-CPU sandbox
request. On gamingpc and the M4 worker, kubelet reserves are already taken out of
allocatable.

How each row follows:

- **Slots.** The `6e5pyj` cut (gmktec 8 to 6, hp 5 to 4, gamingpc 1 to 3) is
  sized on USE. At 8 slots the gmktec runner peak is 8 x 1.7 = 13.6 cores.
  W1 and W2 already sum 27.9-28.4 class cores plus 1.6 system, against 32.
  At 6 slots the peak is 10.2 cores, which takes about 3.4 cores off every peak
  hour. hp's classes averaged 12.7 cores against 13.3 usable. The cohort goes from
  31 slots to 30 on `churn-slot-flavor`; the arm64 flavor is separate.
- **Gate lanes.** The default request drops to 3, and each lane drops to the gate
  share of the node's measured gate use. gmktec runs 7.4 average gate cores, so
  it gets 3 gates. poweredge runs 17.1, so it gets 7. hp runs 2.0 and gamingpc
  0.8, so each gets 1. Every lane is a multiple of the 3-CPU gate unit.
- **Factory pods.** They are the remainder that the request fit leaves at the
  3-CPU sandbox request.

**What the budgeted values cost, measured on the last 24 hours:**

- **Gates** (query `dbbVLi5S76A`). Today's gate pods were replayed, in 5-minute
  buckets, into the budgeted lanes: orchestrator gates at 5, every other gate
  at 3. They leave about 195 more pod-minutes a day waiting than today's lanes,
  1.8% of gate pod-time, concentrated in 32 of 273 buckets.
  - poweredge at 18 instead of 21 would cost 2.1%.
  - Lanes of 3 on gamingpc and hp hold no orchestrator gate. Under today's 5,
    each holds one.
- **Factory** (query `764UoV97fVs`). Factory pods averaged 11.6 concurrent
  across the fleet: p50 12.0, p90 18.4, max 21.6.
  - Per node mean / p90: gmktec 3.6 / 6.0, poweredge 5.9 / 9.1, hp 1.4 / 2.0,
    gamingpc 0.5 / 1.0.
  - An x86 factory budget of 14 instead of today's 19 would have held about 12%
    of factory pod-time in queue, about 1,950 pod-minutes a day.
  - That is the material cost of the request fit. The maintainer decides it
    before the revise.
  - The alternative is to keep factory budgets and NOT give CI workflow pods a
    request. That leaves them BestEffort, starving first under contention, and
    leaves plan assertion 7 unmet for CI pods.

## What is in force, and what waits for the specification revise

**In-spec, landing now:**

- **The churn-slot changes**, by ci-runtime-and-cost under `6e5pyj`, with the
  cohort and ClusterQueue quota rebalance and its read-back. A node's declared
  churn-slot capacity is the specification's ONE per-node limit on runner pods.
- **The factory sandbox request stays at 3 cpu.** Lowering it while CI requests 0
  would pack MORE sandboxes onto a node.

**After the revise of livespec-dev-tooling#4565, one change (wirn53):**

1. **Prerequisite.** livespec-orchestrator-beads-fabro declares `gate_cpu = 5` in
   a merged change. Its gates use 4.6-5.1 cores and it relies on today's default.
2. **The gate default becomes 3.** In the same commit:
   - `gates-cq`'s `ci-runner.io/gate-unit-cpu` becomes 3;
   - every committed lane takes its `gate_cpu` above;
   - enrolled worker lanes follow the unit through `converge-worker-queues.sh`.
3. **CI workflow pods request `ci_job_cpu`.** The request goes on the job
   container of `arc/hook-pod-template.yaml`. Runner pods request
   nothing, so churn slots stay the only runner limit.
4. **`factory_pod_budget` takes the values above** in `ansible/inventory/host_vars`.
5. **The aggregate's checks are armed:**
   - the node CPU fit;
   - the template's request equal to `ci_job_cpu`;
   - the lanes equal to `gate_cpu`.
6. **The saturation rule reads the highest pod-level `cpu.pressure` `some`
   avg60 among the CI workflow pods.** The cgroup is
   `kubepods-burstable.slice/kubepods-burstable-pod<uid>.slice`. The threshold
   is set from a 24-hour side-by-side reading with the BestEffort slice.

**Not done: a gate CPU limit.** A limit must be at least the request, so the
cheapest one at declared parallelism is `max(gate_cpu, gate_parallelism)`: 5 for
dev-tooling and 12 for the orchestrator.

- It saves little. Measured on gmktec, it lowers mean cores per gate pod by about
  4-6% (1.74 to about 1.65; query `99cNUFSN1M3`). That is about 0.5 core of
  gmktec's 7-9 gate cores.
- It costs gate wall time, the harm this budget is meant to reduce.
- A suite-green replay leg runs the committing host's own `-n`, which a limit at
  declared parallelism would throttle.

## Throughput baseline (plan assertion 9)

**Gate wall time on gmktec.** No gate span carries a duration or a node, so this
is a pod-lifetime proxy (datapoints x 30 s). Pods longer than 2 minutes, n / p50 /
p95 in minutes:

| Window | n | p50 | p95 |
|---|---|---|---|
| W1 | 75 | 12.0 | 17.0 |
| W2 | 82 | 10.5 | 17.0 |
| W3 | 55 | 13.5 | 18.0 |
| W4 | 37 | 11.5 | 20.5 |

**Factory.** Commit-hook and coverage-pass wall time inside factory runs is the
harm to move. Run `bd-ib-engf4h` (petri `01M7AZVXPM2E`) spent 1,934 s in
`implement_commit_settle`, with one Green hook still in the per-file coverage pass
about 36 minutes in. The 24 hours to 19:57Z show 39 success, 52 failed and 7
cancelled (`yEUAkTJoyhC`). No column records why a run was cancelled, so 7 is
only an upper bound on wall-budget cancels.

The after window re-reads both on the same queries once the slot change has run
for 24 hours.
