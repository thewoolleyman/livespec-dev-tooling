# Option sheet: making the factory-vs-CI CPU share explicit

Status: **for the maintainer.** legacy-coordinator-agent ruled at about 11:2xZ on 2026-11-08 that this is an architecture
change to placement and accounting (coordinator duties §9), so the maintainer picks. No implementation item may be filed
until the maintainer chooses. The coordinator lists it under FOR THE MAINTAINER in its handoff.

Author: claude:gmktec-factory-placement (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz). The
coordinator agreed with the measurements and the recommendation, but the choice itself is the maintainer's.

## The question

ci-runtime-and-cost measured average cores from Honeycomb `k8s.pod.cpu.usage` for 09:00-11:00Z on 2026-11-08 (posted on
livespec-dev-tooling-6e5pyj):

| node | CPUs | factory | CI | gates |
| --- | --- | --- | --- | --- |
| poweredge-xubuntu | 72 | ~36.6 (10-12 petri pods) | ~32.7 | 2.6 |
| gmktec-xubuntu | 32 | ~21.8 (6-8 petri pods) | ~10.5 | — |
| hp-xubuntu | 16 | none | (CI only) | — |

The churn-slot cap `C` meters CI pods only, so the factory is the unmetered half. On the same day, cutting gmktec's CI
slots (livespec-dev-tooling#3777) only pushed CI shards onto poweredge. Should the factory's share of each node's CPU be
budgeted explicitly, and how?

## Measured facts (read-only, about 11:10-11:25Z on 2026-11-08)

- **The factory-eligible fleet is CPU-full.** `mpstat 5 3` idle read 1.7 % on poweredge, 1.0 % on gmktec and 29.5 % on
  hp. That is roughly 116 of 120 cores in use across the three nodes. Moving factory pods between nodes moves where the
  contention lands, not how much throughput there is.
- **What sets today's split is the default k3s scheduler, working from REQUESTED CPU:**
  - Factory sandboxes select on `nodeSelector ci-runner.io/factory=true`, which only poweredge and gmktec carry. They
    request 3 CPU with a limit of 6, which makes them Burstable QoS.
  - They also carry a soft hostname topology spread (`maxSkew 1`, `ScheduleAnyway`), rendered by
    sandbox-driver-kubernetes.
  - CI runner pods request 0 CPU, which makes them BestEffort, so the scheduler cannot see them.
  - Requested share at the read was 41 of 72 on poweredge (57 %) against 25 of 32 on gmktec (78 %), so poweredge keeps
    winning the score. That gives the observed 10-12 pods against 6-8.
  - The factory-pressure taint reconciler (`ci-runner/k3s/phase2/factory-pressure-placement/`, bd-ib-plon2p) also fits on
    requests. No node carried its taint at the read.
- **Factory stage time is the wrong grading signal.** This uses the per-stage method of the knee measurements (Honeycomb
  fabro `run_turn` joined to kubeletstats placement, 24 h; recorded in scope events on me5aqz, 08:56Z and about 11:1xZ):
  - gmktec's per-stage factory time runs 0.86 of poweredge's while both nodes are saturated.
  - poweredge's normalized stage time is flat from 10 to 13 concurrent sandboxes (1.00, 1.13, 1.03, 1.01).
  - The cause is CFS weighting. Factory pods are Burstable (gmktec `kubepods-burstable.slice` cpu.weight 743), while CI
    pods are BestEffort (`kubepods-besteffort.slice` cpu.weight 1). The factory wins every contended cycle, so the cost
    of saturation lands on CI job duration rather than on factory turns.
- **The factory-vs-CI share is set implicitly today.** Under contention, the factory always wins.

## Not evidence: the 2026-11-08 dev-tooling janitor timeouts

legacy-coordinator-agent asked for these numbers to be added here. They do NOT support making the share explicit,
and are recorded so that no later reading cites them as if they did.

- **What was seen.** ci-runtime-and-cost's read on livespec-dev-tooling-6e5pyj (13:14:13Z) found 5 dev-tooling
  janitor visits that ran into the 3600 s timeout, all between 10:02Z and 13:07Z on 2026-11-08. Three of them were
  no-merge visits, where the earlier maximum was 1680 s.
- **Where they ran.** All 5 ran on poweredge-xubuntu. Each run stayed in one pod (`petri-<run>-l0`) on one node,
  read from Honeycomb kubeletstats. The runs are h5sifx `01M6X5HVCGAB` (visits 1-3), 4pchid `01M6X4NQE2CC`
  (visit 3) and o5xpdy `01M6XAFZHHTM` (visit 1).
- **The control: same node, same window.** nxeg32 `01M6X82Q8VMC` finished in 943 s and 1273 s. pstquv
  `01M6X5R38914` finished in 1059 s, 977 s and 1047 s.
- **Node load.** poweredge used about 71.5 of its 72 CPUs from 04:00Z to 13:15Z, with no change at 10:02Z.
- **The timed-out pods** used a flat 4.0 cores (their limit is 6) for every visit. Their suites were busy, not
  starved.
- **Reading.** The cause is specific to those runs. It is not host saturation, cetudy's system.slice weight (which
  does not apply to poweredge), the #3777 step-back or its revert, or CI load.
- **Baseline for any dial or share decision.** Over 7 days (66 visits across 68 runs, from fabro events on the petri
  server), uncensored dev-tooling janitor suite times were:

  | Node | n | Median | Max |
  |---|---|---|---|
  | poweredge | 29 | 1752 s | 3543 s |
  | gmktec | 22 | 1350 s | 3223 s |

- **The factory yield of 1 green in 19** over the same window is not separated here into these run-specific
  timeouts and other failures. Do not read it as a CPU-share signal until that split exists.

## Options

### 1. A per-node factory slot budget, derived together with `C` (RECOMMENDED)

- Advertise an extended resource for factory slots on each factory node, through the same node extended-resource
  mechanism the CI churn slots already use (the `node_extended_resource` tag).
- Have each factory sandbox pod request one slot. This is a sandbox-driver-kubernetes pod-spec change, owned by
  kubernetes-sandbox-backend.
- Derive each node's pair (factory slots, `C`) in `ci-runner/k3s/phase2/kueue/DERIVATION.md`, from CI p95 job duration
  against concurrency on that node. That follows the throughput-not-utilization rule in `.ai/ci-node-capacity-reads.md`;
  the data source is ci-runtime-and-cost's CI duration series.
- Keep the sum of factory slots at or above the shared fleet cap (18 today).
- Roll out under coordinator duties §10: one node's slot budget first, then widen.

Why: the factory's share becomes an explicit, committed, per-node number that can be graded on CI p95, which is the
signal that actually moves. It reuses an existing mechanism and leaves the Kueue derivation of CI untouched.

Cost:
- A sandbox-driver change plus a derivation change in two repositories.
- When a node's slots are full, factory launches pend instead of overcommitting.

### 2. Give CI runner pods a CPU request

- Make CI pods request CPU, for example a share of their churn slot, so the scheduler and the factory-pressure reconciler
  can see CI load. That also moves CI out of BestEffort.

Why not first: it changes the Kueue churn-slot derivation itself, and the QoS and CFS standing of every CI pod. That is a
larger change with fleet-wide CI blast radius. It does fix the reconciler's blind spot, though, so it could follow
option 1.

### Rejected

- **Shifting the split toward gmktec.** gmktec is already at 1 % idle. Its implement P50 at 8 or more concurrent
  sandboxes is 73 min (n=10), against 38 min below 8, and it reads 1.37 at 9 sandboxes (n=6, thin).
- **Re-admitting hp-xubuntu as a factory node.** By capacity it would fit about 2 sandboxes: 29.5 % idle is about
  4.7 cores, and 27.2 GiB of allocatable memory fits 3 at 7630Mi each. But hp has been `FACTORY_NODE=false` since
  2026-11-03 (`ci-runner/k3s/phase0-bare-metal/profiles/hp-xubuntu.env`, "Factory posture" block). The placement owner
  decided that (kubernetes-sandbox-backend, bd-ib-nmuyjc) at the coordinator's request, citing the maintainer's direction
  that the factory moves off hp, after hp showed the fleet's worst CI slowdown (p95 37.5 min). Its idle CPU is CI
  headroom. The coordinator confirmed the 11-03 decision stands. This is unrelated to this plan's Definition of Done
  assertion 5, which concerns hp's Fabro-host role in the fabro-hosts inventory.

## Recommendation

Option 1: a per-node factory slot budget derived with `C`, graded on CI p95, one node first. Option 2 is the alternative,
and could follow later to give the pressure reconciler visibility of CI load.
