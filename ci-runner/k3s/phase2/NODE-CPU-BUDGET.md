# Per-node CPU budget for the self-hosted pool

This is the ONE budget from which every CPU-bearing cap of the pool derives:

- each node's CI churn-slot capacity (`ADMISSION_CAPACITY_C` in
  `../phase0-bare-metal/profiles/<node>.env`);
- each gate lane's cpu quota (`kueue/cluster-queue-gates.yaml`);
- the factory share of each node.

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
| Factory placement | gmktec-factory-placement | — |

## The rule

For each node:

    usable = allocatable CPU - measured system.slice share
    usable >= runner share + gate share + factory share

- **Runner share** is `slots x cores per CI job`.
- **Each share** is sized from MEASURED class demand, not from requests.
- **Requests understate use.** CI runner pods request 0 CPU, and one gate
  requesting 5 has used 11-17 cores, so the scheduler cannot keep a node inside its
  budget by itself. That is why the budget sets the caps.
- **The sum must fit at the peak hours, not only on the 24-hour average.**
  Saturation is idle under 5% while the BestEffort CI slice's `cpu.pressure`
  avg60 is over 30, the pool's saturation rule. Every extra job past that point
  only lengthens every job (`.ai/ci-node-capacity-reads.md`).

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

`usage_usec` deltas of `kubepods.slice` and `system.slice`, with idle from
`/proc/stat`:

| Node | Allocatable | Idle | kubepods cores | system.slice cores | BestEffort pressure full avg10 |
|---|---|---|---|---|---|
| gmktec-xubuntu | 32 | 0.7% | 30.6 | 1.6 | 31.0 |
| poweredge-xubuntu | 72 | 2.9% | 63.1 | 5.7 | 8.1 |
| hp-xubuntu | 14.5 | 12.9% | 12.4 | 1.2 | 3.4 |

gmktec class demand sat at or above capacity in 12 of the 24 hours (20Z, 22Z,
01-03Z, 05-08Z, 13Z, 17Z, 18Z).

### Cores per CI job

Runner-class cores divided by half the runner-class pod count. Each job is one
runner pod and one workflow pod; that pairing is assumed, not yet verified pod
by pod.

| Node | W1-W4 | Basis |
|---|---|---|
| gmktec | 1.6-1.8 | about 1.7 |
| poweredge | 1.4-2.3 | about 1.9 |
| hp | 1.8-2.2 | about 2.0 |
| gamingpc, M4 | (too few jobs) | fleet basis, 1.7 |

## The budget (cores)

| Node | Allocatable | System | Usable | Gates | Factory | Runner room | Slots now | Slots budgeted |
|---|---|---|---|---|---|---|---|---|
| gmktec-xubuntu | 32 | 2 | 30 | 9 | 9-10 | 10-11 | 8 | **6** |
| poweredge-xubuntu | 72 | 6 | 66 | 17-21 | 17 | 28-32 | 17 | 17 |
| hp-xubuntu | 14.5 | 1.2 | 13.3 | 2-3 | 3.3 | 7-8 | 5 | **4** |
| gamingpc-xubuntu | 12 | 0 | 12 | 5 (lane) | 4 (one run) | 3 (average) | 1 | **3** |
| macbook-m4-max-homelab-worker | 12 | 0 | 12 | about 2 | about 1 | arm64 only | 1 | 1 |

On gamingpc and the M4 worker, kubelet reserves are already taken out of
allocatable.

How each row follows:

- **gmktec 8 to 6.** At 8 slots the runner peak is 8 x 1.7 = 13.4 cores. W1 and
  W2 sum 27.9-28.4 class cores plus 1.6 system, against 32. At 6 slots the runner
  peak is 10 cores, about 3.4 cores off every peak hour.
- **hp 5 to 4.** The classes averaged 12.7 cores against 13.3 usable, and 13.9 at
  W2. Four slots at about 2.0 cores is 8 cores of runner room.
- **gamingpc 1 to 3.** The node averages 1.6-3.0 cores busy. Three slots at 1.7
  is 5.1 cores. Add one gate (lane 5, p95 4.5) and one factory run (p95 4.0) and
  the node reaches 13.6 only if all three peak together, against an average of
  about 8. The strict all-peaks reading allows 1.
- **M4 stays 1.** Its slot serves only queues that list
  `churn-slot-worker-arm64-flavor`, and they hold quota 0 there today. The node is
  laptop-hosted, so raising it is the coordinator's call, not a budget limit.
- **poweredge stays 17.** Gates 17.1 and factory 16.9 on average leave about 32
  cores for runners at about 1.9 per job.

Cohort: 31 slots today (17 + 8 + 5 + 1) become 30 (17 + 6 + 4 + 3) on
`churn-slot-flavor`. The arm64 flavor is separate.

## What is in force, and what waits for a specification revise

**In-spec, landing now:**

- **The churn-slot changes**, by ci-runtime-and-cost under `6e5pyj`, with the
  cohort and ClusterQueue quota rebalance and its read-back. A node's declared
  churn-slot capacity is the specification's ONE per-node limit on runner pods.
- **The factory request stays at 3 cpu**, against a measured p50 of 2.0-2.9.
  Lowering it while runners request 0 would pack MORE sandboxes onto a node.
  Factory per-node share is a placement question for gmktec-factory-placement.
  Today's placement can steer by relative pressure but cannot hold a per-node
  count. A `livespec.io/factory-slot` extended resource is the route if a hard
  count is ever needed.

**Spec-blocked: one propose-change from plan `gate-job-resources`.** Four
ratified clauses block the rest of the honest-request budget:

1. Contracts §"Delegated pre-push gate", **Gate lane headroom**: the gmktec gate
   lane keeps at least three default-size gates, 15 CPU. The budget's gmktec gate
   share is 9.
2. The scenario for an undeclared repository's gate: it requests 5 CPUs. The
   measured mean for most repositories is about 1-3.
3. NFR **Runner placement follows admission capacity** and its scenarios:
   churn-slot capacity is the only per-node limit on runner pods, and a
   non-runner CPU request MUST NOT stop a runner placement. A real runner CPU
   request would make the scheduler's resource fit refuse exactly that. The
   preferred amendment drops CPU fit from the runner scheduler profile, which keeps
   "slots are the only per-node runner limit" literally true.
4. Contracts §"Placement by node pressure" reads `cpu.pressure` of "the
   BestEffort slice that holds the CI runner pods". A runner request moves them to
   Burstable, so the rule must read the slices that hold the runner pods.

After that revise:

- runner containers request about 1.7-1.9 cores, as one fleet-wide value;
- the runner ClusterQueues cover `cpu` with a pool-wide quota of that value times
  their churn-slot quota;
- the gate default request falls to the measured mean;
- the gmktec lane's cpu quota is derived from this budget.

**Not done: a gate CPU limit.** A limit must be at least the request, so the
cheapest one at declared parallelism is `max(gate_cpu, gate_parallelism)`: 5 for
dev-tooling and 12 for the orchestrator.

- It saves little: measured on gmktec it lowers mean cores per gate pod by about
  4-6% (1.74 to about 1.65; query `99cNUFSN1M3`), about 0.5 core of gmktec's 7-9
  gate cores.
- It costs gate wall time, the harm this budget is meant to reduce.
- A suite-green replay leg runs the committing host's own `-n`, which a limit at
  declared parallelism would throttle.

It is reconsidered with the propose-change if peak gate bursts remain the binding
term after the slot cut.

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
