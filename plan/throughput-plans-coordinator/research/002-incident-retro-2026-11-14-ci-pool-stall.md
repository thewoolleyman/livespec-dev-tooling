# Incident retro: fleet CI pool stall, 2026-11-13/14

Captured by throughput-plans-coordinator on the maintainer's word, 2026-11-14 ~05:3xZ: "Okay, yes, go ahead and capture the incident retro and add to your plans whatever is necessary to prevent this sort of thing in the future." The maintainer asked first: "Who let this incident happen and why?"

## What happened

Master CI verdicts stalled for more than 60 minutes in all three large repositories. At the worst read (05:11Z):

- livespec-overseer: 241 min;
- livespec-orchestrator-beads-fabro: 189 min (03:45Z);
- livespec-dev-tooling: 131 min (04:49Z).

Small-repository PR open to CI green went from 4-5 min to about 19 min. livespec-dev-tooling lead time p50 reached 271 min. The fleet's 6-hour non-docs merged-green rate fell to 6.67/h, below its 6.90 floor.

The fix had to be carried through the incident protocol, livespec-dev-tooling-asxhj3: livespec-dev-tooling#4628 (a small-queue floor of 2) and #4635 (PowerEdge gate lane 30 to 20 cpu). The fix's own CI queued in the jammed pool it was meant to clear.

## Cause: four decisions, each reasonable alone, and nothing watching how they combined

1. **The PowerEdge gate lane grew from 2 to 4 to 6 gates on 11-11.** Commits 99231b3e and 84e3c346, livespec-dev-tooling-ukoeah, gate-job-resources. Gates run Burstable and CI pods BestEffort, so on PowerEdge the gates took CPU from CI.
   - One master coverage run (43543797308) took 102.5 min there, against 27 min normally, and ended red on the Ansible "Local RPC server did not start" starvation flake (livespec-dev-tooling-biq757).
   - livespec-dev-tooling's B' group held every newer merge for 106 min behind it.
   - The 11-14 03:03Z gates-cq re-order took PowerEdge from 0.4% to 3.7% idle (CI-slice pressure 38.7 to 6.86), and its gate p50 from 35.5 to 12.0 min.
2. **The CI cohort was cut to 30 churn slots on 11-13.** Commit 0787ea64, livespec-dev-tooling-6e5pyj, the ci-runtime-and-cost cohort-30 change, graded by legacy-coordinator-agent. Eight small repositories were left with one CI slot each and no guaranteed floor. Under load each one serialized its PR's parallel jobs: 1 admitted, 5 pending, 52 arc-runner pods at the Kueue admission gate.
3. **A demand surge in single-slot repositories.** livespec-overseer ran 1,973 CI jobs on 11-13 against 145 on 11-11, mostly its own release machinery: 12 releases, release-please PR re-runs, release-dispatch fan-out, chore master pushes. livespec-console-beads-fabro ran 720. No release-cadence limit applied.
4. **No check watched the signal that broke.**
   - STRANDED-CAPACITY flags only a binding cap beside IDLE nodes. The nodes were saturated, so it passed silently.
   - Nothing alarmed on master-verdict age or CI queue wait.
   - The capacity changes in 1 and 2 were not followed by a read of CI-side job time.

Coordinator side: this seat took its role at 01:13Z. The slowdown showed in the new M2/M3 metrics around 02:50Z. It was read as a stop-the-line only from about 03:0xZ, when throughput-metric's awaiting-verdict read crossed 60 min.

## Not a cause (checked)

- **The orchestrator master-lane variable.** An earlier version of this retro, and the coordinator's first answer to the maintainer, said livespec-orchestrator-beads-fabro#5188 merged on 11-13 at 19:05Z and shipped with CI_RUNNER_LABELS_MASTER unset for about 8 h. That was WRONG: 19:05Z is the commit's authored date. The PR merged at 2026-11-14T03:01:35Z, and ci-runtime-and-cost set the variable at 03:08:25Z, about 7 minutes later. Before that merge, master's ci.yml did not read the variable at all. The orchestrator's 01:47Z-03:00Z shard wait was the PR pool's cohort starvation (cause 2). The master lane was RELIEF, not a cause: its first run went push to green in 34.3 min. The expression also has a declared fallback chain, so a static "unset and defaultless variable" check would not have fired. Corrected by ci-runtime-and-cost's read.
- **The ARC listener move** (66780a46, crvvxt): listener count never dropped below 15.
- **Suite growth:** trivial jobs grew as much as heavy ones, and check-per-file-coverage did not grow.
- **The github-ci "gap":** this was export lag. Spans post at run end, and the runs were slow.
- **gate-job-resources' early claim that CI jobs doubled from 11-11** came from wrapped-duration spans (bt2cnw class) and was retracted. The corrected fleet job p50 is 33.3, 34.9, 38.1 s.

## Guards, each with an owning plan

| # | Guard | Owner (epic) | Fleet scope |
|---|---|---|---|
| G1 | A stop-the-line ALARM (Honeycomb trigger, committed) when any repository's oldest merge without a master verdict exceeds 60 min, beside the table's printed block | throughput-metric (livespec-dev-tooling-oe7cfw); kubernetes-observability delivers the trigger | all 15 repositories |
| G2 | Every capacity, quota or lane change carries a CI-side read at +2 h (CI queue wait, job p50 with duration_ms < 1 day, node CI-slice pressure) and a measured revert trigger in its DERIVATION section; a check refuses a DERIVATION entry without them | gate-job-resources (livespec-dev-tooling-ukoeah) | the k3s pool |
| G3 | WITHDRAWN: the variable-unset cause was a misread of a commit date (see "Not a cause"), so no guard is owed for it | — | — |
| G4 | An incident lane for capacity-config fixes whose CI does not run in the pool it repairs: hosted capacity, or apply on the incident-ci verdict | expedited-incident-response-flag (livespec-dev-tooling-bqnzcm), via legacy-coordinator-agent | livespec-dev-tooling incident path, then the fleet |
| G5 | Fleet-utilization's STRANDED-CAPACITY gains a SATURATED-POOL signal: a binding queue beside nodes with idle below 5% and CI-slice pressure above 30, with queue-wait p95 | legacy-coordinator-agent's scripts/coordinator tooling | the k3s pool |
| G6 | A release-cadence window for repositories that release per push (livespec-overseer first: 12 on 11-13) | the overseer owner, via legacy-coordinator-agent | every repository on Release Please |
| G7 | Items held on spec-change topics nobody filed are flagged mechanically (e34ks3, qeou2e, biq757 tonight) | spec-implementation-lockstep (routed by legacy-coordinator-agent) | every tenant |

The CI demand levers stay in progress: row 5c (approved by the maintainer; about 2,340 runner-min/day) and coverage sharding at constant runner-minutes (livespec-dev-tooling-mxjbmi, bd-ib-p622hp).

## What this plan changes in itself

- Every tick treats an AWAITING MASTER VERDICT line over 60 min as a stop-the-line read that same tick, and routes it.
- Every capacity ruling this seat makes carries a measured revert trigger and a +2 h CI-side read.
- This seat tracks G1-G7 to closure as inherited waits.
