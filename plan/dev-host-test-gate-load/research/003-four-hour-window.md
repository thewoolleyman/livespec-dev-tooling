# 003 — The four-hour baseline window (assertion 1)

Recorded 2026-11-01 by seat dev-host-test-gate-load (resumed session). This is the measured window that the epic's first
Definition of Done assertion asks for. It is also the baseline that assertion 6 is judged against.

## Window and method

- **Host:** vmi3006760, the dev host (KVM, 18 vCPUs).
- **Window:** 2026-11-01 16:25:43Z to 20:51:34Z. That is 1530 intervals of 10 s, 4.25 hours.
- **Sampler:** the transient user unit `vpsload-window4h` ran the v3 sampler, byte-identical to
  `data/002-baseline/sample3.py.txt`.
- **Summariser:** `data/002-baseline/analyze3.py.txt`, also byte-identical. It was run as
  `python3 -I analyze3.py.txt window4h.jsonl 30`.
- **Data:** the raw window is `data/003-window/window4h-1625Z-2051Z.jsonl.gz`. The full summariser output is
  `data/003-window/window4h-analysis.txt`.

The method and its blind spots are in note 002 §2 and §3: substring class rules, hidden steal, and slight over-attribution. In
this window, 13 of 1530 intervals attribute more than wall capacity.

## Result: test/gate load averaged 2.73 cores, 19.7% of attributed runtime

The host attributed 13.87 cores of 18. `/proc/stat` accounted for 11.44 wall cores: busy 8.37, sys 4.17, idle 2.63 and iowait
0.44.

| class | cores | share | sys share of the class |
|---|---|---|---|
| other | 3.91 | 28.2% | 67% |
| agent-sessions | 3.46 | 24.9% | 54% |
| op-bd-wrapper | 1.12 | 8.1% | 34% |
| **janitor-post-merge** | **1.09** | 7.9% | 30% |
| factory-dispatch-supervision | 1.08 | 7.8% | 39% |
| **commit-pre-commit-aggregate** | **0.90** | 6.5% | 26% |
| herdr | 0.69 | 5.0% | 66% |
| gh-cli | 0.56 | 4.0% | 55% |
| **adhoc-pytest-or-check** | **0.49** | 3.5% | 75% |
| dolt | 0.24 | 1.7% | 30% |
| **adhoc-gate-start** | **0.12** | 0.8% | 73% |
| **pre-push** | **0.11** | 0.8% | 32% |
| sampler | 0.05 | 0.3% | 37% |
| **commit-red-green-replay** | **0.02** | 0.1% | 21% |
| **coverage-tree** (unowned) | **0.01** | 0.1% | 33% |
| **test/gate total** | **2.73** | **19.7%** | |

Bold rows are the routine test and gate classes. The rows sum to 2.74 because of rounding; the summariser's total is 2.73.

The load comes in bursts. Across 51 five-minute buckets the test/gate total had a minimum of 0.61, a median of 2.52, a 90th
percentile of 4.81 and a maximum of 6.72 cores. Only 7 buckets were under one core: 19:29Z to 19:59Z, when no janitor and no
hand commit ran. The peaks are janitor post-merge runs, 2 to 4 cores each, overlapping hand-commit pre-commit aggregates of 2 to
3 cores. Examples are 17:23Z to 17:29Z, 18:52Z and 20:41Z.

## What it means for the carriers

Assertion 6 asks for the routine classes together to average under one core. These classes total **2.73 cores**. The ones the
plan's carriers move off the host are:

| carrier | classes it moves | baseline cores |
|---|---|---|
| assertion 3: the janitor venue flips. These are livespec-dev-tooling-verj3y plus the per-tenant items named in handoff 2. | janitor-post-merge | 1.09 |
| assertion 2: livespec-dev-tooling-3buhph | commit-pre-commit-aggregate | 0.90 |
| assertion 4: livespec-dev-tooling-qgv3tb | adhoc-pytest-or-check and adhoc-gate-start | 0.61 |
| sewnfp, owned by plan sv6m5p | commit-red-green-replay | 0.02 |
| assertion 5: already delegated | pre-push | 0.11 |

If every carrier ships, the residue is pre-push's world-reading members, local fallbacks, and `--local` runs. Pre-push alone
is 0.11 today, so the one-core bar is reachable with margin. No class falls outside the plan's carriers.

Most of the host's load is not test/gate load. That includes the agent sessions, the op-bd wrapper at 1.12 cores (more than
the janitor), factory supervision, herdr, and gh. Note 002 §5 relayed that to the coordinator. On 2026-11-01 the lever carriers
were placed under livespec-dev-tooling-dfixhe, not under this plan.
