# 002 — capacity read and the Definition of Done re-word

Recorded 2026-11-10 ~23:45Z by the gate-job-resources seat. Source: the
legacy-coordinator-agent capacity helper. It made a read-only pass,
2026-11-10 23:27-23:36Z. Its raw output stayed in that session's scratchpad
(`k1.out`-`k3.out`, `holds.txt`); the figures it reported are below.

## What the read measured

- **The gates Kueue flavors.** Live `gates-cq` has FOUR flavors, not the three
  in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`. The fourth,
  `gates-worker-taint-arm64-flavor`, is 5 cpu / 8Gi on
  macbook-m4-max-homelab-worker, and `converge-worker-queues.sh` adds it (see
  "Source of truth for the worker gates flavor" below). At
  5 cpu per Job that admits 3 (gmktec-xubuntu) + 2 (poweredge-xubuntu) + 2
  (hp-xubuntu) + 1 (arm64) = 8 concurrent gates.
- **Admission waits.** They were 0-1 s, so the flavor quotas mostly do NOT
  bind today.
- **CPU inside each gate.** This is what strands it: 4 xdist workers in a
  cpu:5 Job, with measured gate use of 0.3-5.7 of the 5 cpu.
- **Latent packing on gmktec-xubuntu.** Once 3 gates run, 28/32 cpu is
  requested, while the node reads 77% idle. Raising the per-gate request ALONE
  would make the scheduler refuse on requests while the CPU sits idle. So the
  request and the quota are sized from MEASURED per-gate cpu at 8 and 12
  workers. A request below the worker count is a legitimate outcome: the Job
  has no cpu limit, so the request is a reservation, not a ceiling. C1 accepts
  fractional and millicore cpu values for this reason.

## Source of truth for the worker gates flavor

This is not a gitops gap. The flavor is GENERATED, and both of its sources are
committed:

- **Generator.** `ci-runner/k3s/phase2/kueue/converge-worker-queues.sh`
  renders `kueue/worker/gates-worker-flavor.yaml` once per architecture
  (`@ARCH@`).
- **Where it goes.** The script places that flavor FIRST in `gates-cq`, ahead
  of the committed fleet flavors.
- **Who runs it.** `converge-ci-stack.sh` runs it, and so does
  `homelab-worker/enroll-workload-classes.sh` after it enrolls or removes a
  worker.
- **Install.** It reaches the node through ansible role `ci_converge_unit`
  (`defaults/main.yml:120-132`).

Its quota counts whole gates per enrolled worker:
`max(1, gate-share-millicores / 5000)`. The gate unit is HARD-CODED in the
script as `gate_millicores=5000` and `gate_memory_gi=8`. C3 must therefore
change two sources in lockstep with any change to the per-gate request:

- `cluster-queue-gates.yaml`, for the three fleet flavors;
- that gate unit in `converge-worker-queues.sh`.

Otherwise the worker flavor keeps counting 5-cpu gates.

## Limits routed outside this plan (plan assertion 6 names them)

| Limit | Measured | Owner |
|---|---|---|
| Factory size screen | refused 72 of 75 tickets | fixed by orchestrator 0.315.1 |
| hp-xubuntu is not a factory node | — | DELIBERATE: maintainer direction 2026-11-03 (factory off hp; CI p95 37.5 min); reversal is a pending maintainer decision, not a limit this plan clears |
| Factory fleet-cap | 12, latent | legacy-dispatcher-agent |
| CI churn-slot cap C | 30, latent | ci-runtime-and-cost |
| Gates request and quota packing | 5 cpu/Job; 28/32 requested at 77% idle | this plan (C1-C4) |

## The Definition of Done re-word (carrier map 2)

Three plan assertions were re-worded on the epic, and a carrier-map scope
event recorded the change:

- **Assertion 3.** The concurrency floor is the EIGHT gates admitted today,
  not seven.
- **Assertion 4.** The measurement records per-gate cpu use as well as wall
  time, and it comes before any default OR quota moves.
- **Assertion 6.** hp-xubuntu not being a factory node is listed as
  deliberate, with a maintainer decision pending. It is not a limit this plan
  clears; a corrective scope event records this. Assertion 6 closes when the
  stranded-capacity section of
  `fleet-utilization.sh` (from the coordinator's docs PR) reads zero FLAGGED
  lines after the fixes. Each limit is named with its owner.

The DoD text in research note 001 is the creation-time snapshot and is
write-once. The epic's `## Definition of Done` section is authoritative.
