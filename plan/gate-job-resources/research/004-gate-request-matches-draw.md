# 004 — the orchestrator gate request matches its draw (item (i))

Recorded 2026-11-15 by the gate-job-resources seat (session 2a5d41). The plan
was reopened by throughput-plans-coordinator on legacy-coordinator-agent's
ruling, at the maintainer's request, for item (i) only. Items (ii) and (iii)
belong to homelab-k8s-worker-nodes (livespec-dev-tooling-ko26ez): (ii) is the
arm64 churn-slot quota and (iii) is fleet-utilization.sh with node enrollment.

## Root cause, as briefed (node cgroups, 2026-11-15 06:47Z)

- Every orchestrator gate pod requested 5 cpu, had no CPU limit, and ran
  `LIVESPEC_TEST_PARALLELISM=12`. It drew about 16 cores.
- gmktec-xubuntu's gates-flavor lane (10 cpu) admitted two such gates, gt5tv
  and 9jmnf. Together they took 32.4 of 32 cores, and the BestEffort CI
  runners starved (BestEffort full avg60 40).
- gamingpc-xubuntu read 0.14% idle at 06:51Z under one gate, h5f9x.

## Draw, measured per repository

The figures are Honeycomb `k8s.pod.cpu.usage` over the 12 hours to about
07:00Z on 2026-11-15, from the `metrics` dataset. The filter was pod name
prefix `gate-<repo>-` and only samples above 0.5 cpu were counted.

| repository | node | gate pods | P50 | P90 | MAX |
|---|---|---|---|---|---|
| orchestrator | gmktec | 39 | 1.00 | 26.15 | 30.33 |
| orchestrator | gamingpc | 35 | 2.96 | 14.71 | 15.34 |
| orchestrator | hp | 10 | 1.00 | 14.36 | 14.37 |
| orchestrator | poweredge | 8 | 2.36 | 48.40 | 49.26 |
| dev-tooling | M4 | 76 | 1.60 | 5.67 | 10.67 |
| dev-tooling | gmktec | 55 | 1.20 | 4.99 | 17.21 |
| dev-tooling | gamingpc | 33 | 1.23 | 5.30 | 7.18 |
| dev-tooling | poweredge | 22 | 2.37 | 4.96 | 13.60 |
| dev-tooling | hp | 14 | 1.00 | 4.22 | 8.79 |

Only the orchestrator's draw is far above its request. livespec-dev-tooling
runs the default 4 workers, and its P90 matches the 5-cpu default. The
orchestrator's P90 is set by what each node had free. On gamingpc and hp it
reached the whole allocatable.

## The change

The orchestrator now declares `gate_cpu = 10` and `gate_parallelism = 10`,
with `gate_memory = "8Gi"` unchanged. Before the change it declared 5 cpu (the
default) and 12 workers. The change is in livespec-orchestrator-beads-fabro
`pyproject.toml`, branch `chore/gate-cpu-matches-draw`. No Kueue lane or
flavor changes.

- **The request now equals the worker count.** Under contention, the gate's
  measured P90 at 12 workers was 12.11 cores (note 003). So 10 workers on a
  10-cpu request counts close to the real draw.
- **Where the gate fits.** gmktec's 10-cpu lane admits one orchestrator gate,
  where it used to admit two. The PowerEdge's 20-cpu lane admits two. The
  5-cpu lanes (gamingpc, hp, and the arm64 worker lane on the M4) admit none.
- **Why not request 16 cpu at 12 workers.** A 16-cpu gate fits only the
  PowerEdge lane, so the fleet could run only one orchestrator gate at a time.
- **Wall time.** 10 workers falls between the measured 929 s (8 workers) and
  797 s (12 workers) test runs. That is expected to stay under the yljbpf
  900 s line.
- **Bursting.** The Job still has no CPU limit, by contract (the
  gate-job-template comment), so an admitted gate can burst onto idle cores.
  If bursts still starve CI after this change, the next lever is a spec
  change that adds a gate CPU limit. It is not taken here.

## Baseline before the change, and the revert trigger

Read at about 06:58Z with `mpstat 1 5` and
`kubepods-besteffort.slice/cpu.pressure`:

| node | idle % | BestEffort full avg60 |
|---|---|---|
| poweredge-xubuntu | 0.19 | 38.94 |
| gmktec-xubuntu | 0.08 | 38.57 |
| hp-xubuntu | 7.09 | 3.58 |
| gamingpc-xubuntu | 49.57 | 1.37 |

The briefed revert trigger is "any node under 5% idle with BestEffort full
avg60 over 30 across two 10-minute windows". poweredge and gmktec already met
it before the change. This seat therefore reads the trigger as: revert if a
node meets it in both windows after the change AND is no better than this
baseline. A second revert condition is any orchestrator gate that waits more
than five minutes for a lane.

To revert, restore `gate_parallelism = 12` and remove `gate_cpu` in the
orchestrator's `pyproject.toml`.

The +2 h CI-side read covers three things:

- gate pod p50 per node, against the DERIVATION.md baselines (PowerEdge 35.5,
  gmktec 20.0, hp 19.0, gamingpc 8.5, M4 10.0 min);
- CI queue wait;
- node CI-slice pressure.

## The expected effect, stated before the read (throughput-plans-coordinator, 2026-11-15)

- **The expected mechanism is fewer co-resident gates, not a capped draw.**
  The request does not cap anything. An admitted gate still bursts toward its
  P90 when cores are idle, and BestEffort CI still loses to any Burstable pod
  under contention. What changes is admission: at most one orchestrator gate
  per 10 cpu of lane. So the read measures the per-node count of co-resident
  orchestrator gates, set against node idle % and BestEffort full avg60.
- **Gate capacity falls.** Fleet-wide, the most orchestrator gates that can
  run at once falls from about 8 to 3. Before, they could take every 5-cpu
  slot: gmktec 2, PowerEdge 4, gamingpc 1, hp 1. After, they fit gmktec 1 and
  PowerEdge 2. The +2 h read therefore adds the gates-cq pending count and
  each gate's queue wait (admission time minus creation time).
- **Who owns lane sizes.** Lane sizes on gamingpc and hp belong to
  homelab-k8s-worker-nodes, and this seat asked it whether either node can
  hold a 10-cpu lane. On gamingpc, 12 allocatable less one 4-cpu factory
  sandbox leaves 8 cpu. hp has 16 cores.
- **The next lever is queued.** If CI starvation persists, the next step is a
  CPU limit on the gate Job. It is filed now as a propose-change so it waits
  in the queue: topic `gate-job-cpu-limit`.
