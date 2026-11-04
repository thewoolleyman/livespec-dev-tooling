# 006 — The first A6 after-window: 1.27 cores, not met

Recorded 2026-11-04 by seat dev-host-test-gate-load. This note records the first measured window for the epic's sixth
Definition of Done assertion: after the carriers ship, the routine test and gate load classes together must average under one
CPU core on the dev host, measured by the same method as the baseline in note 003.

## Window and method

- **Host:** vmi3006760, the dev host (KVM, 18 vCPUs).
- **Window:** 2026-11-04 09:54:20Z to 14:21:29Z. That is 1560 intervals of 10 s, 4.33 hours.
- **Sampler:** the transient user unit `vpsload-a6-after` ran the v3 sampler. It is byte-identical to
  `data/002-baseline/sample3.py.txt` (sha256 `c98615a3…`, see `data/006-a6-after/sampler-sha.txt`).
- **Summariser:** `data/002-baseline/analyze3.py.txt`, also byte-identical (sha256 `de4bf093…`). It was run as
  `python3 -I analyze3.py.txt a6-after.jsonl 30`.
- **Data:** the raw window is `data/006-a6-after/a6-after-0954Z-1421Z.jsonl.gz`. The full summariser output is
  `data/006-a6-after/a6-after-analysis.txt`. The decomposition below is `data/006-a6-after/a6-after-decomposition.txt`.

The method's blind spots are in note 002 §2 and §3. In this window, 0 of 1560 intervals attribute more than wall capacity.

## Result: test/gate load averaged 1.27 cores, 9.8% of attributed runtime

The host attributed 13.01 cores of 18. `/proc/stat` accounted for 13.10 wall cores: busy 9.29, sys 4.02, idle 3.58 and iowait
0.23.

| class | baseline (003) | this window |
|---|---|---|
| janitor-post-merge | 1.09 | 0.03 |
| commit-pre-commit-aggregate | 0.90 | 0.02 |
| adhoc-pytest-or-check | 0.49 | 0.18 |
| adhoc-gate-start | 0.12 | 0.73 |
| pre-push | 0.11 | 0.30 |
| commit-red-green-replay | 0.02 | 0.01 |
| coverage-tree | 0.01 | 0.00 |
| **test/gate total** | **2.73** | **1.27** |

**Verdict: assertion 6 is NOT met by this window.** The bar is under one core, and the same-method total is 1.27.

The janitor and hand-commit classes, which were 1.99 cores of the baseline, fell to 0.05 cores. The total is above the bar
because of two bursts in classes that were small in the baseline.

## Where the 1.27 cores came from

The sampler's per-interval `top` lists name the processes behind each class
(`data/006-a6-after/a6-after-decomposition.txt`). Those lists do not cover every process, so the removals below are lower
bounds.

1. **adhoc-gate-start, 0.73 cores. At least 0.57 of it is Rust compilation of the fabro engine.** The processes are `rustc` and
   `clippy-driver` building the `fabro`, `fabro_server`, `fabro_api`, `fabro_petri` and `attractor_steps` crates. Two windows
   carry it: 10:30Z to 11:03Z, and 12:33Z to 13:13Z at 2 to 3.3 cores. The gate-run records under
   `/data/projects/livespec-orchestrator-beads-fabro/tmp/gate-runs/` match them: `uctbct/gate.sh` (10:36Z to 10:59Z),
   `ten-runs.sh` (10:31Z to 11:03Z) and `engine-build.sh` (12:40Z to 13:13Z). Each was started through `gate-start` in that
   repository, and each run records neither `venue` nor `venue_reason`. The class rule matches the gate-run ancestor, so an
   engine build started through the gate runner lands in a routine test/gate class even though it is a build.
2. **pre-push, 0.30 cores. At least 0.22 of it is this seat's own void proof capture.** At 11:17Z to 11:37Z a push from
   `~/.worktrees/livespec-dev-tooling/proof-4k7262-capture-20261104` ran the full local pre-push aggregate at about 3.4 cores. It
   was a 4k7262 host capture attempted on v1.170.0. That release did not yet contain the fix, so the push fell through to the
   local aggregate. The capturer killed it at 20 minutes. The capture was discarded, and it was redone on v1.171.0 at 13:25Z.

Without those two sources, at most 0.48 cores of routine test and gate load remain. That is under the bar with margin. This
note does NOT treat that as the assertion's result: it is a corrected reading, and the assertion is judged by the baseline's
method unchanged.

## Other changes during the window

These are all on the k3s nodes, not on this host. They are listed in `data/006-a6-after/window-notes.txt`:

- 09:35Z to 09:50Z, 11:27Z to 11:38Z and 13:26Z to 13:37Z: CI stack converges on poweredge-xubuntu. The second set
  `LIVESPEC_TEST_PARALLELISM` to 6, and the third reverted it to 3 after PSI60 reached 55 at 13:16Z.
- 11:41Z to 11:42Z: churn slots re-stamped to hp 5, poweredge 27 and gmktec 12.

## Next

- **A second after-window is running.** The unit is `vpsload-a6-after-2`. It started 2026-11-04 14:24:48Z, ends about 18:45Z,
  and uses the same sampler and summariser. This seat runs no local test or gate load on the dev host during it.
- **The engine-build attribution is a finding for the plan proof.** A Rust engine build started through `gate-start` counts as
  routine test/gate load under the baseline's class rules. If it recurs in the second window, the plan proof will report both
  the same-method total and the per-process decomposition, and will name the engine builds as the cause.
