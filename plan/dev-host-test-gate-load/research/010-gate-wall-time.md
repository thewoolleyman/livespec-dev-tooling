# 010 — Gate wall time: the suite inside the Job is the slow part, not queueing or the dev host

Recorded 2026-11-11 by seat dev-host-test-gate-load. The maintainer asked, through legacy-coordinator-agent, why hook
gates take as long as they do now that they run as cluster Jobs. Session 5fd46e9c collected the data on 2026-11-10 and
sent the findings to the coordinator. This note records them. It changes no Definition-of-Done assertion and no carrier.

## Data and method

- **Gate runs.** These are every `tmp/gate-runs/*/` record under `/data/projects/*` that started in the 24 hours before
  2026-11-11 00:04Z (`survey.py.txt`). The analysis covers commit, amend and push runs only. Each run's `output.log` is cut into
  segments (`seg.py.txt`), using the delegated client's own Job lines (`job_name`, `job_started_at`, verdict timestamp):
  - `a` is dev-host time before the first gate Job is created.
  - `job` is time from Job creation to verdict.
  - `gaps` is time between consecutive Jobs.
  - `d` is dev-host time after the last verdict.
- **Gate Jobs.** These come from a `kubectl get jobs,pods -n gates -o json` snapshot of the 36 gate Jobs created
  2026-11-10 21:25:45Z to 23:03:50Z (`jobs.py.txt` → `jobsum.json`). The cluster has since deleted those Jobs. The raw
  snapshot stays in the seat's `tmp/` and is not committed, because it carries internal endpoints. `jobsum.json` keeps
  the derived per-Job timings and node.
- **Blind spots.** `gate-submitter` cannot list `events` or Kueue `workloads` in `gates` (403, saved in the data
  directory). So admission is measured as Job creation → Job `startTime`, not from the Workload's own conditions.
  Four Jobs were still running at the snapshot, so they have no run time.

Data: `data/010-gate-walltime/`.

## Findings

All gate Jobs in the snapshot requested `cpu: 5`, `memory: 6Gi` and ran with `LIVESPEC_TEST_PARALLELISM=4`.

| stage | measured |
|---|---|
| Kueue admission (Job created → started) | median 1 s, max 32 s (36 Jobs) |
| Pod start (scheduled → container started), gmktec / poweredge / hp | 5-15 s / 6-10 s / 7-62 s |
| Pod start, macbook-m4-max-homelab-worker | 85-92 s on all 11 Jobs it ran |
| Dev-host time before the first Job (`a`), median | 0.6-1.4 min in every repository with n ≥ 16 |
| Gaps between Jobs, and dev-host time after the verdict | median 0.0 and ≤ 0.4 min |

End-to-end wall time, median (p90), by repository and kind, for runs that delegated to at least one Job:

| repository | commit | amend | push |
|---|---|---|---|
| livespec-orchestrator-beads-fabro | 3.1 (8.2), n=21 | 44.5 (47.5), n=5 | **40.7 (45.4)**, n=16 |
| livespec-dev-tooling | 4.4 (12.2), n=198 | 11.1 (16.9), n=66 | 10.1 (17.0), n=100 |
| livespec-console-beads-fabro | — | — | 10.2, n=2 |
| livespec-overseer | — | — | 9.5, n=4 |
| every other repository | ≤ 1.6 | ≤ 2.8 | ≤ 3.5 |

Where the time goes:

1. **The orchestrator's coverage member dominates its push and amend.** In all 16 orchestrator pushes the run's
   `check-per-file-coverage` member had a median wall of 38.2 min (max 46.0). It runs 14,539 to 14,898 test items on 4
   xdist workers. In a typical run (`20261110T113614Z-3997276`), the member took 2,209 s out of a 2,312 s `check-pre-push`.
   Nothing in queueing or on the dev host comes close.
2. **Queueing is negligible.** Admission is about a second and pod start is seconds, with one exception: the macbook
   homelab worker adds about 1.5 min of pod start on every Job. It ran 11 of the 36 Jobs.
3. **The dev host's share of a gate is about a minute.** That share is the `a` segment: hook preamble, staging the tree,
   creating the Job. This is consistent with assertion 6's aim. The hand-commit path's wall time sits in the cluster, not
   on the VPS.

## What this suggests (findings, not filed)

- Orchestrator push and amend time is a test-suite size and parallelism question, owned by that repository. Coverage at
  4 workers inside a 5-CPU request is the binding constraint. The `gate-job-resources` plan (declared gate Job resources)
  is the place to raise per-repository parallelism. This plan files nothing for it.
- The macbook worker's 85-92 s pod start most likely comes from its image pull or its VM layer. It belongs to that node's
  owner (homelab worker plans) and is sent there as an observation.
