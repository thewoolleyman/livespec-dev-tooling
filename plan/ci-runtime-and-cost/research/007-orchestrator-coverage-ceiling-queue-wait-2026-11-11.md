# 007 — Orchestrator k3s coverage queue wait against the ARC maxRunners ceiling (2026-11-11)

Plan ci-runtime-and-cost (livespec-dev-tooling-ib3oe3), handoff 49 NEXT step 4. Read-only measurement.

## Question

Does livespec-orchestrator-beads-fabro's k3s coverage queue wait come from the ARC scale set's `maxRunners`, while the churn-slot cohort had slots free? The ceiling is `max(2 x nominalQuota 9, 6) = 18` (DERIVATION.md, "Orchestrator to 9, dev-tooling to 9, within 30").

A recorded exception under DERIVATION.md "Recorded exceptions to the rule" is justified only if the answer is yes.

Context: since 2026-11-04 the orchestrator runs as a hybrid. Only its coverage legs ride k3s: `check-per-file-coverage-shard`, `check-per-file-coverage` and `check-coverage`.

## Verdict

**EXCEPTION JUSTIFIED, bounded.** The ceiling bound for 47 minutes in 24 h while the cohort had free slots, 3 or more free in 44 of those minutes.

- **Strict count:** 57 coverage jobs waited more than 2 min across those minutes, 261 job-minutes of wait in total. 133 of those job-minutes fall inside ceiling-bound minutes.
- **Broad count** (orchestrator at 17 or more runners, proxy below the cohort): 139 jobs and 718 job-minutes. The upper bound on what a higher ceiling could have saved is 534 overlapping job-minutes.

The waits come in bursts. Most of the 07Z hour is one: p50 2.8 min, p95 10.9 min, max 14.1 min. That is the hour of the coordinator's 07:41Z STRANDED-CAPACITY flag.

A candidate is 18 -> 24, the pre-2026-11-08 value with a known kill switch. It only helps while the cohort has room. The cohort was at or over its total in 5 of the ceiling minutes, and raising the ceiling there adds gated pods, which is the kine Slow SQL cost DERIVATION.md "Bounding maxRunners to the quota" measured.

Moving dev-tooling's non-coverage CI to hosted at 07:34:42Z, and gamingpc's 31st slot, both add headroom from today on.


## Correction (coordinator, 2026-11-11)

Any converge-ci-stack run applies ALL of master (measured by gate-job-resources on livespec-dev-tooling#4139). So an exception merged from this note goes live at the first converge-ci-stack run after the merge, with no separate apply step. The acceptance window starts at that converge, and the acceptance record names the run.

## Figures, window 2026-11-10T09:46:19Z to 2026-11-11T09:46:19Z

**Orchestrator k3s jobs.** 1,279 jobs over 243 ci.yml runs, every one on scale set `livespec-orchestrator-k3s`:

| Job | Count |
|---|---|
| check-per-file-coverage-shard | 864 |
| check-per-file-coverage | 208 |
| check-coverage | 207 |

**Queue wait** (`started_at - created_at`, minutes):

| Hour (UTC) | n | p50 | p95 | max |
|---|---|---|---|---|
| **overall** | **1279** | **0.28** | **4.88** | **14.08** |
| 2026-11-10T09 | 8 | 0.27 | 1.28 | 1.28 |
| 2026-11-10T10 | 46 | 0.27 | 2.80 | 4.88 |
| 2026-11-10T11 | 41 | 0.25 | 0.28 | 0.28 |
| 2026-11-10T12 | 81 | 0.28 | 5.57 | 5.98 |
| 2026-11-10T13 | 53 | 0.27 | 0.90 | 2.07 |
| 2026-11-10T14 | 47 | 0.27 | 0.77 | 3.97 |
| 2026-11-10T15 | 46 | 0.25 | 0.30 | 1.80 |
| 2026-11-10T16 | 46 | 0.25 | 0.28 | 0.92 |
| 2026-11-10T17 | 19 | 0.25 | 0.30 | 0.30 |
| 2026-11-10T18 | 17 | 0.25 | 0.28 | 0.28 |
| 2026-11-10T19 | 20 | 0.20 | 0.25 | 0.27 |
| 2026-11-10T20 | 16 | 0.27 | 0.32 | 0.32 |
| 2026-11-10T21 | 32 | 0.25 | 0.28 | 0.30 |
| 2026-11-10T22 | 41 | 0.27 | 0.30 | 0.32 |
| 2026-11-10T23 | 47 | 0.27 | 0.30 | 0.35 |
| 2026-11-11T00 | 35 | 0.28 | 0.32 | 0.35 |
| 2026-11-11T01 | 58 | 0.30 | 1.83 | 2.00 |
| 2026-11-11T02 | 71 | 0.33 | 3.58 | 4.65 |
| 2026-11-11T03 | 87 | 0.28 | 1.62 | 5.60 |
| 2026-11-11T04 | 93 | 0.33 | 4.95 | 8.47 |
| 2026-11-11T05 | 81 | 0.45 | 2.95 | 4.10 |
| 2026-11-11T06 | 77 | 0.35 | 5.05 | 7.07 |
| 2026-11-11T07 | 100 | 2.82 | 10.87 | 14.08 |
| 2026-11-11T08 | 64 | 0.28 | 5.92 | 7.05 |
| 2026-11-11T09 | 53 | 0.28 | 1.12 | 1.97 |

**Concurrency**, sampled at each minute's :30 instant, counting jobs with `started_at <= t < completed_at`:
- Orchestrator maximum: **18**, the ceiling.
- 17 or more runners: 127 minutes. Exactly 18: 50 minutes.
- Per-minute binning instead reads a false maximum of 23, because it double-counts job turnover inside a minute. Do not use it.

**Cohort-occupancy proxy** = concurrent k3s jobs of the orchestrator + livespec-dev-tooling (`livespec-dev-tooling-k3s` 1,570 jobs, `livespec-dev-master-k3s` 708) + livespec (`livespec-local-ci-k3s`, 229 jobs). The cohort total is 30 slots, 31 from gamingpc's read-back at about 09:44Z.

- Of the 127 minutes at 17 or more, 122 had the proxy below the cohort total and 5 were at or above it. The proxy ranged 17 to 31 in those minutes.
- Free-slot headroom over those 122 minutes:

| Free slots | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Minutes | 3 | 4 | 6 | 2 | 6 | 2 | 10 | 13 | 17 | 22 | 19 | 12 | 6 |

  101 minutes had 6 or more free slots.
- Free-ceiling minutes by hour:

| Hour (UTC) | Minutes |
|---|---|
| 2026-11-10T10 | 5 |
| 2026-11-10T11 | 2 |
| 2026-11-10T12 | 15 |
| 2026-11-10T13 | 9 |
| 2026-11-10T14 | 6 |
| 2026-11-10T15 | 1 |
| 2026-11-10T16 | 3 |
| 2026-11-11T02 | 7 |
| 2026-11-11T03 | 2 |
| 2026-11-11T04 | 14 |
| 2026-11-11T05 | 19 |
| 2026-11-11T06 | 3 |
| 2026-11-11T07 | 26 |
| 2026-11-11T08 | 10 |

- Minutes at exactly 18 with cohort headroom: 47, of which 44 had 3 or more free slots.

**Ceiling-bound waits** (waited more than 2 min, across a ceiling minute with free cohort slots):

| Count | Minute rule | Jobs | Summed wait (job-min) | Inside bound minutes (job-min) |
|---|---|---|---|---|
| Broad | at 17 or more | 139 of 151 jobs that waited over 2 min | 717.6 | 534 |
| Strict | at exactly 18 with 3 or more free | 57 | 261.4 | 133 |

## Caveats

- **The proxy omits seven low-volume repos.** In the window their ci.yml run counts were: livespec-overseer 49, driver-claude 22, driver-codex 21, runtime 25, console 11, git-jsonl 27, driver-pi 25. Each is under 400 runner-min/day (research 005), so together they average about 2 or fewer concurrent jobs. The 6-or-more headroom in 101 of the 122 minutes survives that.
- **Slots are per node.** A free cohort slot is a free churn slot on SOME node, because the quota sum equals the node capacity sum. The proxy does not model node affinity.
- **Queue wait here is job `created_at` to `started_at`.** It includes ARC runner-pod start (about 0.25 min at p50), not only ceiling waits. That is why the strict count requires a wait over 2 min.

## Reproduce

Every read uses `gh api --cache 3600s`. Runs are listed with `per_page=100`, and jobs are fetched once per run attempt.

```text
# collect (per repo): runs, then each attempt's jobs, keeping k3s-runner jobs that started
gh api --cache 3600s "repos/thewoolleyman/<repo>/actions/workflows/ci.yml/runs?per_page=100&page=<n>&created=%3E%3D2026-11-10T09:46:19Z"
gh api --cache 3600s "repos/thewoolleyman/<repo>/actions/runs/<run_id>/attempts/<attempt>/jobs?per_page=100"
#   keep: runner_name contains 'k3s' (or labels contain it), started_at set, conclusion != skipped
#   repos: livespec-orchestrator-beads-fabro, livespec-dev-tooling, livespec
# other-repo volume
gh api --cache 3600s "repos/thewoolleyman/<repo>/actions/workflows/ci.yml/runs?per_page=100&created=%3E%3D2026-11-10T09:46:19Z" --jq .total_count
```

The analysis scripts are `collect.py`, `analyze.py` and `proxy.py`, in the session scratchpad `qwait/` directory. The definitions:
- Concurrency at instant `t` is the count of jobs with `started <= t < completed`, sampled at each minute's :30.
- A ceiling minute has orchestrator concurrency of 17 or more, and strictly 18.
- A minute is free when the proxy is below the cohort total (30, or 31 from 2026-11-11T09:44Z).
- A job is ceiling-bound when it waited more than 2 min and its `[created, started)` window contains a free ceiling minute.
