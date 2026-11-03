# 002: fleet CI cost ranking, 7 days to 2026-11-03T01:00Z

Measured 2026-11-03 by the ci-runtime-and-cost seat. This note carries plan assertion 1's figures and the evidence
for the first carrier's leg choice.

## Method (reproducible)

- Window: runs created 2026-10-27T01:00:00Z to 2026-11-03T01:00:00Z, across the seven fleet repositories.
- Run lists: `gh api --cache 6h --paginate "repos/thewoolleyman/<repo>/actions/runs?created=<day>T00:00:00Z..<day+1>T00:00:00Z&per_page=100"`,
  one query per day, because a single 7-day query is capped at 1,000 results. 8,083 runs.
- Jobs: `gh api --cache 24h --paginate "repos/thewoolleyman/<repo>/actions/runs/<run-id>/jobs?filter=all&per_page=100"`.
  Every `CI`, `Fabro sandbox image` and `acceptance-live-golden-master` run was fetched in full. Every other workflow was
  sampled at 25 runs, and livespec's `Master health reconcile` at 95, then scaled by its run count. 44,035 jobs.
- Job minutes are `completed_at - started_at`. Lane: a job whose labels include `ubuntu-*` ran on hosted capacity;
  every other job ran on a k3s/ARC runner, and each such runner holds one `ci-runner.io/churn-slot` for its life.
- Uid divergence: for every orchestrator run attempt, each `<target> (root)` / `<target> (nonroot)` pair whose
  conclusions were one `success` and one `failure`; the failing job's log is read with
  `gh api repos/thewoolleyman/livespec-orchestrator-beads-fabro/actions/jobs/<job-id>/logs`.

## Cost is churn slots, not dollars

All seven repositories are public, so the 135 hosted job-hours cost nothing. The cost is k3s runner capacity:
966 job-hours in 7 days, 13.1% of `C = 44` slots x 168 h (`ci-runner/k3s/phase2/kueue/DERIVATION.md`, C = 44). The
average is low because the demand arrives in bursts. Bursts make the queues, and the queues show up as wall time:
orchestrator CI runs had a median wall time of 9.0 min on pull requests (p90 25.9 min) and 8.8 min on master
pushes (p90 24.1 min).

## k3s job-hours by repository

| Repository | Job-hours | Share |
|---|---:|---:|
| livespec-orchestrator-beads-fabro | 664.4 | 68.8% |
| livespec-dev-tooling | 168.3 | 17.4% |
| livespec-overseer | 54.4 | 5.6% |
| livespec | 26.3 | 2.7% |
| livespec-driver-claude | 22.6 | 2.3% |
| livespec-driver-codex | 21.7 | 2.2% |
| livespec-runtime | 8.3 | 0.9% |
| **total** | **966.0** | |

## The root/nonroot doubling is 59% of all fleet k3s time

Only `livespec-orchestrator-beads-fabro/.github/workflows/ci.yml` carries the uid dimension (bd-ib-sfa2). Its legs:

| Job | nonroot h | root h | median min (nonroot / root) |
|---|---:|---:|---|
| check-per-file-coverage | 143.9 | 135.6 | 6.2 / 6.0 |
| check-coverage | 61.1 | 57.7 | 1.2 / 1.1 |
| check-python-batch | 43.9 | 34.8 | 2.0 / 1.7 |
| check-types | 28.1 | 19.6 | 1.1 / 0.9 |
| check-lint | 16.0 | 8.1 | 0.6 / 0.4 |
| check-format | 15.7 | 8.0 | 0.6 / 0.4 |
| **total** | **308.7 (32.0%)** | **263.7 (27.3%)** | |

The nonroot legs cost about 17% more than root. The cause is the leg's own preparation: a `chown -R` of the workspace
and a private, cold `UV_CACHE_DIR` under `/home/ci`.

## What each uid uniquely caught (7 days)

43 jobs passed under one uid and failed under the other. Every log was read.

- Most are the SAME flaky tests failing on whichever uid lost the race, and each also appears on the other uid in
  another run:
  - `tests/integration/test_fleet_launch_check_scenario242.py:108` (shellcheck over fleet-launch)
  - `test_dispatcher_credential_use_guard.py:527` ("the agent was never stopped after the waiter died")
  - `test_acp_factory_hold_evidence.py:953` (`assert 6 == 8`)
  - `test_acp_codex_headroom_journal.py:305`
  - `tests/conftest.py:1013` ("no launcher run thread ... is alive")
  - `test_otel_receive.py:121` (TimeoutError)
  - `test_session_telemetry_export.py:308`
  - `test_dispatcher_recovery_routing_lock_hold.py:470`

  These are flakes, not uid evidence.
- Nonroot-only:
  - `test_dispatcher_prepare_payload_installs_helpers.py:111` failed at setup under uid 1000 in three runs of PR
    `feat/bd-ib-kzgpzm` (2026-10-30/31). It is a plausible real HOME/permission divergence, and it was caught before
    merge.
  - `test_dispatcher_shell_runner_streaming.py:36` hit a 2.0 s timeout (exit 124) on three master runs. That is a
    timing flake on the slower leg, not a uid defect.
- One `check-lint (nonroot)` failure was runner infrastructure: `EACCES` on `/home/runner/_work/externals/node20`.
- Root-only: nothing but the flakes above.
- The rerun tax is negligible: re-attempt jobs used 58 min in the orchestrator and 101 min in dev-tooling.

## Leg choice for the first carrier (recommended to the coordinator)

On pull requests, keep NONROOT for every uid-doubled job. Move ROOT's full set to a scheduled master workflow that
files a breakage work item when it is red.

- Nonroot is production-shaped. The janitor and factory workers run non-root, and bd-ib-sfa2 exists because a
  nonroot-only miss stayed green in a root-only CI.
- The only plausibly uid-specific catch in the window was nonroot-only.
- The saving is about 264 job-hours a week, 27% of all fleet k3s time. Keeping root on pull requests would instead
  save 309 h, 45 h more, at the cost of the production-shaped leg.
- bd-ib-sfa2's 100%-coverage argument survives: each uid is still independently gated at fail_under = 100. A
  root-only divergence is now found on master after merge rather than before, and the breakage item makes it owned
  work.

## Other low-hanging fruit (measured; filing follows the carrier)

1. **Flaky tests.** Fix or quarantine the flaky tests listed above. They are what turns either leg red. This is not a
   runner-minute saving, but it is the main cause of red runs.
2. **Nonroot-leg overhead.** About 45 h a week over root for the same work. Seed uid 1000's uv cache and avoid the
   full-workspace `chown -R`.
3. **dev-tooling `check-per-file-coverage`.** 84 h a week of k3s (5.8 min median on 685 runs). It is the largest
   single k3s job outside the orchestrator. Candidates: xdist width and test-duration outliers.
4. **dev-tooling `check-fleet-conformance`.** Runs hosted (free) at 3.9 min on all 697 CI runs. It costs wall time
   only, not churn slots, so it is low priority.
5. **Release-dispatch `await sandbox image tags`.** A 10.6 min hosted poll. Free, wall time only.
6. **`check-coverage` consumer jobs.** 1.1 min each, almost all of it container setup to read an artifact. They
   cost 119 h a week across both uids in the orchestrator. After the carrier, that is about 61 h on pull requests.
   Folding the consumer into the producer would save most of it, but the tool-backed matrix-literal rule
   (check-tool-backed-check-completeness) constrains the shape.

## Why CI felt slow on 2026-11-02 (measured after the first pass)

The same jobs got about 3x slower on 2026-11-02:

| Job (median, minutes) | 10-27 to 11-01 | 11-02 00-18Z | 11-02 18Z on |
|---|---|---|---|
| orchestrator check-per-file-coverage | 5.5-6.0 | 9-11 | 19-23 |
| orchestrator check-lint (root) | 0.3 | 0.5 | 0.9 |
| dev-tooling check-per-file-coverage | 3.0-5.6 | 9.3 (11-02 whole day) | 14.9 (11-03) |

On 40 recent orchestrator runs, the nonroot 'Prepare non-root leg' step took a median 120-130 s in every nonroot job.

Concurrency on k3s runners (mean per 3 h bucket) rose over the same period: it was 2-8 on 10-31 and 11-01, then
10-16 during 11-02 and 24-36 from 18Z. Counting only ARC k3s runners at 1-minute resolution, it peaked at exactly 44
at 2026-11-02 20:33Z (orchestrator 35, dev-tooling 6, overseer 3). The cohort sat at its C = 44 cap, which is the
CPU-saturation regime `.ai/ci-node-capacity-reads.md` describes. That regime feeds itself, because slower jobs
overlap more. (An earlier count of 57 included runner-less skipped jobs and was corrected.) The capacity side
belongs to kubernetes-sandbox-backend (baseline recorded on livespec-dev-tooling-zreev4). This plan owns the demand
side.

## Release and pin-bump cascade (measured; coordinator assigned it to this plan)

k3s job-hours by CI class over the 7 days, 964.5 h in total:

| CI class | Job-hours | Share |
|---|---:|---:|
| other pull requests | 431.3 | 44.7% |
| other master pushes | 204.9 | 21.2% |
| release-please pull requests | 102.1 | 10.6% |
| pin-bump pull requests | 80.3 | 8.3% |
| pin-bump master | 77.8 | 8.1% |
| release master | 68.2 | 7.1% |

Release mechanics therefore cost 328 h, 34%. The orchestrator cut 110 releases (release PR CI 79.3 h, release master
CI 52.4 h). dev-tooling cut 49, about 20 of them on 2026-11-02, and each fans out a pin bump to every sibling.
Classification used each CI run's branch and head-commit subject (`gh api --cache ... actions/runs`, `head_commit.message`).

## Carriers filed (2026-11-03)

- bd-ib-pgbr52: host-side breakage filer for the scheduled root-uid workflow.
- bd-ib-xufdwx: the uid move. Nonroot stays on pull requests; root runs every 3 h plus workflow_dispatch and skips an
  unchanged head.
- bd-ib-gb24he: the flaky tests, each with its introducing commit.
- bd-ib-uuatg4: the nonroot preparation step.
- livespec-dev-tooling-aplxhg: coalesce releases into a scheduled window. This is a maintainer decision.

Not filed: dev-tooling check-per-file-coverage. It is a single producer/consumer pair with no duplication; its 84 h
is the suite itself, inflated by the 2026-11-02 contention.
