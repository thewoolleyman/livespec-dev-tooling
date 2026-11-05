# 004 — Runner-minutes per orchestrator PR CI run: the baseline, and why it went UP after the coverage move

Measured 2026-11-05 ~02:30Z by `claude:ci-runtime-and-cost`, for plan assertion 4: "Over at least 20 pull-request
CI runs of livespec-orchestrator-beads-fabro after the coverage move ships, the median runner-minutes per
pull-request CI run is below the 7-day baseline recorded in this plan's research." Research 002 recorded wall time
(median 9.0 min on pull requests) but no runner-minutes-per-run figure, so this note records that baseline.

## Method

- **Run sets.** `ci.yml` runs with `event=pull_request` and status `completed`, from
  `gh api --cache 3600s 'repos/thewoolleyman/livespec-orchestrator-beads-fabro/actions/workflows/ci.yml/runs?event=pull_request&created=<range>&per_page=100&page=<n>'`.
  - **Baseline:** 2026-10-27T16:15:00Z to 2026-11-03T16:15:00Z, the 7 days before bd-ib-xufdwx merged
    (livespec-orchestrator-beads-fabro#4293, 2026-11-03T16:15:41Z). 706 completed runs; every third run sampled
    (n = 236).
  - **Post:** 2026-11-03T16:15:42Z to 2026-11-05T02:00:00Z. All 194 completed runs.
- **Runner-minutes per run.** For each run, the sum of `completed_at - started_at` over every job of every attempt:
  `.../actions/runs/<id>/jobs?filter=all&per_page=100`. Queue time is excluded. A job counts as k3s when its
  `runner_name` contains `k3s`, and as hosted otherwise.
- The figure is the median over runs. Wall time is `updated_at - run_started_at`.

## Result: assertion 4 is NOT met today

| Window | n | median runner-min / run | p90 | k3s | hosted | median wall |
|---|---:|---:|---:|---:|---:|---:|
| **Baseline**, 7 d before xufdwx | 236 | **32.98** | 115.72 | 32.94 | 0.05 | 10.81 |
| Post, all | 194 | **44.72** | 65.37 | 41.81 | 0.05 | 31.06 |
| Post, k3s-only, before cutover 2 | 143 | 46.65 | 63.08 | 46.60 | 0.05 | 30.03 |
| Post, hybrid since the 17:41Z re-flip | 36 | 46.55 | 71.72 | 38.41 | 8.40 | 39.07 |

The baseline to beat is **32.98 runner-minutes per PR run**; 30.96 over successful runs only, n = 216. After the coverage
move the median is 44.72, 36 % higher, although the root leg left PR CI. Every run in both sets has at least one timed
job.

## Cause: per-file coverage now takes four times as long

Per-job median minutes per run, from the same cached job reads:

| Job | baseline | post, before 08:09Z 11-04 | post, from 08:09Z 11-04 |
|---|---:|---:|---:|
| check-per-file-coverage (nonroot) | 7.0 | 12.2 | **28.0** |
| check-per-file-coverage (root) | 6.8 | — | — |
| check-coverage (nonroot) | 1.3 | 17.8 | 0.6 |
| check-coverage (root) | 1.2 | — | — |
| check-python-batch (nonroot / root) | 2.3 / 1.8 | 3.2 / — | 1.3 / — |
| check-metadata-batch | 2.0 | 3.6 | 3.3 |
| check-types (nonroot / root) | 1.3 / 1.0 | 2.1 / — | 0.8 / — |
| check-lint, check-format (nonroot) | 0.7, 0.7 | 1.2, 1.2 | 0.5, 0.5 |

- **The root leg's removal saved what it was meant to.** Root per-file-coverage (6.8), check-coverage (1.2),
  python-batch (1.8), types (1.0), lint (0.4) and format (0.4) total about 11.6 runner-minutes per run.
- **check-coverage's regression is fixed.** Its 17.8-minute median before 08:09Z was the duplicate suite run that
  bd-ib-xevgsx removed (livespec-orchestrator-beads-fabro#4366); it reads 0.6 now.
- **The cost now comes from check-per-file-coverage (nonroot): 7.0 → 28.0 minutes, about +21 runner-minutes per run.**
  The break is at 2026-11-04T08:09Z. That is livespec-dev-tooling `167d7d82`, "bound CI workflow pods to 3 pytest
  workers per job": `LIVESPEC_TEST_PARALLELISM=3` in `ci-runner/k3s/phase2/arc/hook-pod-template.yaml`. A 6-worker step
  at 13:12Z was reverted by `77e36602`. Before it, the orchestrator's `dev-tooling/just-test-nprocs.sh` gave about
  nproc / 4 workers: 18 on poweredge-xubuntu, 8 on gmktec-xubuntu and 4 on hp-xubuntu.
- The cap was a deliberate node-saturation ruling (hp-xubuntu at 0 % idle; `livespec-dev-tooling-6e5pyj`). It traded
  each job's wall time for node headroom. It probably did not change the CPU-minutes the suite costs, but it
  quadrupled the runner-minutes, which are churn-slot time. Runner-minutes are what this assertion and the churn-slot
  cap both count.

## What this means for the plan

- Assertion 4 measures runner-minutes, so it cannot pass while one job holds a runner for 28 minutes. bd-ib-m26pql
  (shard per-file coverage across k3s pods, each at its own 3-worker cap) is the carrier that can move it. It shortens
  the coverage critical path without lifting the per-pod cap. It does NOT by itself cut total runner-minutes: N shards
  of 3 workers spend about the same worker-minutes, plus each shard's setup. Its own last assertion records that.
- So the honest lever for assertion 4 is per-job worker count against node capacity, decided per node. For example, a
  pod on poweredge-xubuntu (72 cores, 16.8 % idle and CI slice pressure 0.24 at 23:40Z 11-04) could run more than 3
  workers without saturating anything. That is a placement-aware parallelism change, which `6e5pyj` owns, and it needs
  the coordinator's ruling. This note does not propose lifting the cap.
- Re-measure with the same queries after bd-ib-m26pql lands. The comparison stays median runner-minutes per PR run
  against 32.98.
