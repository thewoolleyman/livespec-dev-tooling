# Per-node CPU budget for the self-hosted pool

This budget OWNS one cap: each gate lane's cpu quota. Its authority is
`node-cpu-budget.yaml` beside this file, and `kueue/cluster-queue-gates.yaml`
must equal it.

It CITES, and does not own, the pool's other CPU-bearing caps. Each lives only
in its own file, with its own owner:

- each node's CI churn-slot capacity: `ADMISSION_CAPACITY_C` in
  `../phase0-bare-metal/profiles/<node>.env`;
- each node's factory pod budget: `factory_pod_budget` in
  `ansible/inventory/host_vars/<node>.yml`.

It covers four classes on every pool node: gates, factory sandboxes, CI runners
and the system. Plan `gate-job-resources` owns it (epic
`livespec-dev-tooling-ukoeah`, carrier map 5, 2026-11-13). It is INTERIM: the duty
ends when the radar re-architecture's load-management role takes it. The ruling is
recorded on `livespec-dev-tooling-6tgd2z` at 2026-11-13T19:45:09Z: "the classes
together fit each node, and no node sits idle while work waits".

Each cap has one owner:

| Cap | Owner | Work item |
|---|---|---|
| Churn slots | ci-runtime-and-cost | `livespec-dev-tooling-6e5pyj` |
| Gate lanes | this plan (`node-cpu-budget.yaml`) | `livespec-dev-tooling-wirn53` |
| Factory pod budgets | each node's host_vars owner (gmktec-factory-placement; homelab-k8s-worker-nodes for gamingpc) | — |

## The rule

For each node:

    usable = allocatable CPU - measured system.slice share
    usable >= runner use + gate use + factory use

- Each class's use is MEASURED (the tables below), not read from requests.
- **Requests understate use.** CI pods request no CPU. A gate requesting 5 has
  used up to 26 cores (per-pod max, below). So the scheduler alone cannot keep a
  node inside its budget, and the budget sets the caps.
- **The sum must fit at the peak hours, not only on the 24-hour average.** The
  pool's saturation rule is idle under 5% while the BestEffort CI slice's
  `cpu.pressure` `some` avg60 is over 30 (contracts §"Placement by node
  pressure"). Past that point every extra job only lengthens every job
  (`.ai/ci-node-capacity-reads.md`).

`node-cpu-budget.yaml` beside this file is the authority for the gate lanes.
It names the files that own the other caps.

**Maintainer ruling, 2026-11-13 ~21:3xZ: "Do whatever maximises throughput."**
A request-based fit was considered and NOT taken. It would have required:
- CI workflow pods to request 1.5 cores;
- every node's committed requests to fit its allocatable CPU with every churn
  slot in use.

That fit required cutting the x86 factory pod budget from 19 (its value at
~21:0xZ, before livespec-dev-tooling#4492 made it 20) to 14, which would
have queued about 12% of factory pod-time (below). So under the ruling:
- CI pods stay BestEffort;
- factory pod budgets stay at today's values;
- there is no node request-fit check.

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

**Correction (kubernetes-observability, 2026-11-13).** Sums of the usage gauge
over-weight short-lived pods. Each series gives ONE late value per bucket, so a
pod alive for only part of a bucket is credited for all of it. Against the
cumulative counter `k8s.pod.cpu.time` (query `aYYXAQE8FcA`, 24 h), the gauge
reads:

- runner pods about 2.7x high;
- workflow pods about 10% high;
- gates about 3% high;
- factory about 0% high.

So the gate and factory cores below stand to within about 3%, the CI runner
cores read high, and budget figures should use the counter. Per-pod values
(p50 / p95 / max, per-repository means) are unaffected.

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

The pod-weighted fleet value is 1.54 cores per CI job. The counter reads
workflow pods about 10% lower, so about 1.4. The runner pod is an idle agent. Do not read per-pod CPU from a 24-hour query: its 15-minute
buckets keep one late sample per pod and read the workflow pod at 0.77-1.00
(query `4X3sgRmarYY`).

### Other workloads' requests (live, 2026-11-13 ~20:5xZ; for reference)

| Node | Requests outside gates, factory and CI |
|---|---|
| gmktec-xubuntu | 1.1 (ci-warm-cache 0.5, kueue 0.5, kube-system 0.1) |
| poweredge-xubuntu | 1.3 (kueue 0.5, kube-system 0.3, sccache 0.25, crates proxy 0.1, registry mirror 0.1, warm cache 0.05) |
| hp-xubuntu | 0.6 (ci-warm-cache 0.5, kube-system 0.1) |
| gamingpc-xubuntu | 0 |
| macbook-m4-max-homelab-worker | 0.1 |

## The budget (cores)

Decided by plan gate-job-resources, 2026-11-13, under the maintainer's
throughput ruling.

Today's lanes are in `node-cpu-budget.yaml`, the authority, so they are not
repeated here. wirn53 moves the yaml, the lanes and the gate-unit annotation to
this target in one commit, after the #4565 revise:

| Node | Allocatable (read 2026-11-13T23:33:37Z) | System | Target gate lane |
|---|---|---|---|
| gmktec-xubuntu | 32 | 1.6 | 9 (3 units) |
| poweredge-xubuntu | 72 | 5.7 | 21 (7 units) |
| hp-xubuntu | 14.5 (capacity 16) | 1.2 | 3 (1 unit) |
| gamingpc-xubuntu | 12 (capacity 16; reserves take 4) | not read | 3 (1 unit) |

A container worker's lane is not listed. `converge-worker-queues.sh` derives it
from the gate unit, so it follows the default with no edit.

Churn slots and factory pod budgets are NOT restated here. Each number lives in
its one owning file:

- **Churn slots.** `ADMISSION_CAPACITY_C` in
  `../phase0-bare-metal/profiles/<node>.env`. ci-runtime-and-cost owns them
  under `livespec-dev-tooling-6e5pyj`. livespec-dev-tooling#4568 changes them,
  with the cohort re-sum in `kueue/DERIVATION.md`. Read the values and their
  basis there.
- **Factory pod budgets.** `factory_pod_budget` in
  `ansible/inventory/host_vars/<node>.yml`. The maintainer's throughput ruling
  keeps them at their committed values. Read them there.

How the lanes follow:

- **Gate lanes.** The default request drops to 3 CPUs, so the gate unit is 3.
  Each lane is a whole multiple of it. The rule actually used:
  - **gmktec:** its specification floor, three default-size gates, 9. It runs
    7.4 average gate cores.
  - **hp and gamingpc:** one unit each, the floor for every other lane. They run
    2.0 and 0.8 average gate cores.
  - **poweredge:** the smallest whole multiple that keeps the replayed extra
    gate queueing under 2% of gate pod-time, given the lanes above. 18 replays
    at 2.1% and 21 at 1.8% (query `dbbVLi5S76A`), so 21. Its 17.1 average gate
    cores alone would give 18.

  Without the lane cut, a 3-CPU default would let gmktec admit 5 gates instead
  of 3.

**What the decisions cost, measured on the last 24 hours:**

- **Gates** (query `dbbVLi5S76A`). Today's gate pods were replayed, in 5-minute
  buckets, into the budgeted lanes: orchestrator gates at 5, every other gate
  at 3. They leave about 195 more pod-minutes a day waiting than today's lanes,
  1.8% of gate pod-time, concentrated in 32 of 273 buckets.
  - Lanes of 3 on gamingpc and hp hold no orchestrator gate. Under today's 5,
    each holds one.
  - The coordinator ruled this cost not significant (~21:1xZ).
- **Factory, the option NOT taken** (query `764UoV97fVs`). Factory pods averaged
  11.6 concurrent across the fleet: p50 12.0, p90 18.4, max 21.6. An x86 budget
  of 14 instead of the then 19 (20 since #4492) would have queued about 12% of
factory pod-time, about
  1,950 pod-minutes a day.

## What is in force, and what waits for the specification revise

**In-spec, landing now:**

- **The churn-slot changes**, by ci-runtime-and-cost under `6e5pyj`, with the
  cohort and ClusterQueue quota rebalance and its read-back. A node's declared
  churn-slot capacity is the specification's ONE per-node limit on runner pods.
- **The factory sandbox request stays at 3 cpu.** Lowering it while CI requests
  none would pack MORE sandboxes onto a node.

**After the revise of livespec-dev-tooling#4565, one change (wirn53):**

1. **Prerequisite.** livespec-orchestrator-beads-fabro declares `gate_cpu = 5`
   in a merged change. Its gates use 4.6-5.1 cores and it relies on today's
   default.
2. **The gate default becomes 3.** In the same commit:
   - `gates-cq`'s `ci-runner.io/gate-unit-cpu` becomes 3;
   - `node-cpu-budget.yaml` and every committed lane take the target above;
   - enrolled worker lanes follow the unit through `converge-worker-queues.sh`.

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
