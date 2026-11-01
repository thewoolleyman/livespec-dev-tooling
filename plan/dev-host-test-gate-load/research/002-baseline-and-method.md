# 002 — First baseline, a corrected sampler, and where the dev host's CPU goes

Recorded 2026-11-01 by seat dev-host-test-gate-load. The maintainer confirmed the epic's six Definition of Done assertions
unamended in this tab at about 16:00Z ("thats good, continue").

Raw data and tools are in `data/002-baseline/`:

- `samples.jsonl`, `sample.py.txt`, `mpstat2.txt`: the 30-minute v1 baseline, 15:24:59Z to 15:56:35Z, 180 intervals of 10 s. The
  sv6m5p seat recorded it. mpstat timestamps are host-local (CET, UTC+1), so `16:24:54` means 15:24:54Z.
- `sample3.py.txt`, `analyze3.py.txt`: the corrected v3 sampler and its summariser (stored as `.txt` so the repo's Python gates do not treat scratch tools as product code; run as `python3 -I sample3.py.txt 10 <count> out.jsonl`), and `v3-part1-1553Z-1611Z.jsonl`, the first v3 slice. Assertion 1's 4-hour window and assertion 6's
  after-window MUST use these.

## 1. The v1 baseline over-counts and its absolute numbers are not usable

v1 (`sample.py`) charges each live process its own CPU delta plus its reaped-children (`cutime`) delta. It nets out what
a vanished child was charged while alive, but it credits that only to the child's DIRECT parent. A grandchild reaped through
a dying intermediate is therefore charged twice: once while alive, and again as its whole lifetime in the surviving
ancestor's `cutime`. For example, pytest-xdist workers under a pytest main under `just check`.

The measured consequence is that 65 of 180 intervals attribute more CPU than the host has (18 cores × 10 s). The first interval
charges `bash /tmp/just-J8wJJH/check`, a hand commit's pre-commit aggregate, with 1347 core-seconds in 10 s. Over the
whole window v1 attributes 32.3 cores to an 18-core host.

What the v1 data can still say, with the 65 impossible intervals dropped (which biases toward quiet intervals):

| class (v1 rules) | mean cores, impossible intervals dropped |
|---|---|
| agents-and-other | 12.18 |
| commit-pre-commit-aggregate | 0.85 |
| herdr | 0.75 |
| adhoc-pytest-or-check | 0.71 |
| pre-push | 0.20 |
| dolt | 0.18 |
| adhoc-gate-start | 0.08 |
| janitor-post-merge | 0.03 |
| k3s-docker / coverage-tree | ~0 |
| **test/gate total** | **1.87** |

v1 also classifies by substring over the whole ancestor chain, including Claude seat processes whose command line is the seat's
PROMPT. A seat prompt that mentions "just check", "coverage" or "janitor" pulls every child of that seat (sleeps, `claude plugin
update`, …) into a test class. Treat v1's class split as indicative only.

## 2. The v3 sampler

`sample3.py` takes **no `cutime` at all**:

- A live process is charged its own `utime+stime` delta from `/proc/<pid>/stat`. Processes are keyed by (pid, starttime), so an
  `exec` is not a death.
- A process that EXITS is charged from a bpftrace `sched_process_exit` event (`group_dead` only). The event carries the whole
  group's `sum_exec_runtime`, minus what the process was charged while it was alive. Every CPU-second is counted once,
  wherever the child was reaped. This includes children reparented to a subreaper, which made a v2 "nearest surviving
  ancestor" netting over-count.
- Classification never reads an agent-session process's command line, and the ancestor walk stops at one. A `just check` a
  seat runs is still found, because the `just` process sits below the seat.
- The remainder is split into the classes the coordinator asked for: `agent-sessions`, `factory-dispatch-supervision`,
  `op-bd-wrapper` (op, `with-livespec-env.sh`, bd/bd-real/bd-guard, and the wrapper's `sudo`), `gh-cli`, `agent-hooks`,
  `herdr`, `dolt`, `k3s-docker`, `sampler` (its own cost, ~0.04 cores) and `other`.
- Per interval it also records the host's `/proc/stat` totals for a cross-check.

Known blind spots: class rules are substring heuristics on command lines and cwd. A short-lived process never seen alive is
classified from its exit `comm` and its parent chain, so `git` alone cannot tell push from commit, and its ancestors decide.
About 5 of 107 intervals attribute up to a few percent over wall capacity: per-process times are adjusted to
`sum_exec_runtime`, and the snapshot is not atomic.

## 3. Hidden steal: the absolute "cores" figure needs care on this host

On vmi3006760 (KVM, 18 vCPUs) every vCPU's `/proc/stat` accounts only ~65% of wall time. A 5 s read summed 5521 of the
9304 expected ticks, and each CPU accounted 319–368 of 500. `steal` reads 0, and the boot log shows no `kvm-guest: stealtime`
line. The hypervisor does not expose steal time, so roughly a third of wall time the guest wanted is unaccounted. mpstat
percentages are percentages of the accounted remainder only. That is why mpstat showed 82–90% busy while `/proc/stat` busy
was ~9 of 18 cores. Per-process times use `sum_exec_runtime` on kvm-clock, which counts preempted time. So v3's attributed
runtime (~15 of 18 cores) exceeds `/proc/stat`'s busy figure.

Consequence for assertion 6: "under one CPU core" is judged on v3's attributed runtime, the same method as the baseline.
This note also reports the test/gate SHARE of attributed runtime, because that share does not depend on the steal.

## 4. First v3 readings (part 1 of the 4-hour window, 15:53Z–16:11Z, 103 intervals)

Attributed runtime 15.2 cores of 18. `/proc/stat` accounted 11.6, of which busy 9.4, sys 4.6, idle 1.9.

| class | cores | share | sys share of the class |
|---|---|---|---|
| other | 4.30 | 28.3% | 66% |
| agent-sessions | 3.70 | 24.3% | 53% |
| **janitor-post-merge** | **1.56** | 10.3% | 19% |
| **commit-pre-commit-aggregate** | **1.12** | 7.3% | 38% |
| op-bd-wrapper | 1.01 | 6.6% | 34% |
| factory-dispatch-supervision | 0.97 | 6.4% | 42% |
| herdr | 0.63 | 4.2% | 66% |
| gh-cli | 0.54 | 3.6% | 53% |
| **coverage-tree** | **0.52** | 3.4% | 36% |
| **adhoc-pytest-or-check** | **0.45** | 3.0% | 71% |
| dolt | 0.23 | 1.5% | 19% |
| **pre-push** | **0.08** | 0.5% | 25% |
| **adhoc-gate-start** | **0.02** | 0.2% | 72% |
| commit-red-green-replay (sewnfp, sv6m5p) | 0 | 0 | |
| **test/gate total** | **3.75** | **24.7%** | |

Five-minute profile of test/gate cores: 3.3, 4.1, 4.0, 3.7. A janitor post-merge run (≈2 cores) overlapped a hand commit's
pre-commit aggregate (0.5–1.6) and a coverage tree (0.5–1.0). The load is bursty, so the 4-hour window, not this 18-minute
slice, sets the baseline. The window resumed at 16:11:45Z under the transient user unit `vpsload-window4h` and ends about
20:27Z. The first sampler was stopped at 16:11:37Z: this seat killed its bpftrace child by mistake while chasing a false
"process absent" reading from its own over-narrow `pgrep` pattern. Part 1 is truncated there.

## 5. Where the system time goes: TLB-shootdown IPIs (coordinator's lead, not test/gate)

A 15 s `perf record -a -g` (16:3xZ) put **19–23% of ALL host CPU samples in one kernel function, `smp_call_function_many_cond`**.
That is the sender side of cross-CPU TLB-flush IPIs. The callers, from 5775 samples:

- `madvise` → `tlb_finish_mmu`: 2002 samples, the largest. The top `comm` is `mi-scavenger`, the mimalloc scavenger thread
  inside Claude Code / Bun processes (1182).
- copy-on-write fault after `fork` (`wp_page_copy`): 1401.
- process exit (`exit_mmap`): 1188. The largest is `gh` (1143), a multi-threaded Go binary exec'd ~160 times in one busy
  minute.
- `munmap`: 700.

On a guest without paravirtual TLB flush (that needs the steal-time feature, see §3), every shootdown is a real IPI that waits
for preempted vCPUs. A 60 s bpftrace of exited processes adds: 1107 `sleep` execs a minute (polling loops), `op` at ~770 ms of
CPU per call (36 calls, 27.7 s), and `gh` at ~210 ms per call.

None of this is test/gate load. It is relayed to the coordinator (gitops-fleet-capacity-monitoring, epic
livespec-dev-tooling-dfixhe).

## 6. Pre-push delegation, first pass (assertion 5)

From each repository's `tmp/gate-runs/*` since 2026-10-31. Only pushes started through the gate runner leave a record here; a
bare `git push` from a shell does not.

| repo | pushes | delegated (passed or refused on the cluster) | lefthook skip (no matching push files) | other |
|---|---|---|---|---|
| livespec-dev-tooling | 26 | 23 | 3 | 0 |
| livespec-orchestrator-beads-fabro | 41 | 35 | 5 | 1 run with no output (started, never finished) |
| livespec | 4 | 3 | 1 | 0 |
| livespec-overseer | 13 | 10 | 3 | 0 |
| livespec-console-beads-fabro | 0 | – | – | – |
| livespec-runtime | 0 | – | – | – |

Every orchestrator push that did not show "delegated gate passed" was one of three things: a delegated REFUSAL (the Job
ended Failed, for example on `check-per-file-coverage` 10-31 16:56Z or `check-heading-coverage-debt-register` 11-01 13:41Z), a
lefthook skip, or one unfinished run. None ran the aggregate locally. The coordinator's "22 unexplained" are those refusals and
skips. Members that still run on the dev host, in every delegated repo seen: **`check-branch-protection-alignment` and
`check-no-workflow-edits`**. Each reads an authorization held outside the tree, which the Job is not handed. Console and
runtime declare `delegated_gate = true` but have no gate-runner pushes recorded yet. Their verification is still owed.
