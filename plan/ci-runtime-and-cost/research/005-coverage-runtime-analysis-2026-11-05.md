# 005 — How to cut coverage job runtime: two independent analyses, one synthesis

Written 2026-11-05 ~10:40Z by `claude:ci-runtime-and-cost`, for the maintainer's request of 2026-11-05 ~07:24Z:

> "Do an analysis of the best way to address the coverage job runtimes. I know two possible ways. One is to optimize
> the jobs by parallelization. The other approach is to just have fewer tests, which can be addressed by the fuzzing
> work that we started but didn't finish. But now I started discussing this in some track. If there are other options
> that would help, let me know."

The maintainer also asked for the analysis to think outside the box. Two models answered the same read-only brief
independently, and neither read the other's report:

- **GPT-6-Astra** (`codex exec -m gpt-6-astra`, finished ~07:51Z). Its report is Appendix B.
- **Fable** (a Claude subagent, finished 10:28Z). It did not read Astra's report. Its report is Appendix A.

Both reports are reproduced verbatim below. Paths in them that point at a session `scratchpad/` are working files
from those sessions and are not durable. The forge queries they name (`gh api --cache …`) are the reproducible source.

## Verification done by this session

- **Fable's headline claim was read against the code on master (95b7afc1).** `livespec_dev_tooling/flake_retry.py`
  `mark_untouched_tests` loops `for item in items: retry_marker_for(...)`. `retry_marker_for` calls `_closure`, which
  re-reads and `ast.parse`s the test module, its conftest chain and the transitive in-repository import closure.
  There is no cache keyed on the test path or on the module path. The per-item cost the report measures follows
  directly from that code.
- **The five-run sharding measurement was taken independently by this session** (§"Finding: sharding traded
  runner-minutes for wall time" below). It agrees with Fable's n=15 figures: coverage-chain median 19.1 here against
  17.5 there, over different run windows.

## Where the two analyses agree

- **Parallelisation is mostly spent.** Four shards bought the 35 → ~18 min coverage-chain median. A further doubling
  buys a few minutes and costs runner-minutes, until the redundant per-worker work below is gone.
- **"Fewer tests" acts on the smaller share of the time.** Test execution is roughly a quarter to a third of the
  worker-time in a shard. Both reports put the pre-test phase (start-up, collection and whatever runs at collection
  time) at 2-4x the test phase in a typical post-merge shard.
- **There is no unfinished fuzzing project.** Both searches found what the maintainer most likely means: the
  mutation-testing lineage. That is `plan/fleet-mutation-testing-rule-26/` (epic livespec-dev-tooling-oi2two,
  backlog, no commit since 2026-10-28), rebooted from livespec's `plan/mutation-testing-keystone` (livespec-mutreal).
  The maintainer opened it with "10,000 tests is ridiculous" in the coordinator session on 2026-10-27 ~23:00Z (epic
  dfixhe). Hypothesis property testing is already a dependency fleet-wide. The only real fuzzing is the Rust console's
  finished cargo-fuzz tree. Both recommend a small mutation kill-matrix pilot before any pruning, because a
  kill-matrix is the only method that proves a test redundant.
- **Faster tracing (`COVERAGE_CORE=sysmon`) is not available.** The fleet runs Python 3.10.16. Branch coverage under
  sysmon needs Python 3.14, so this lever waits for a fleet Python upgrade.
- **Remove proven duplicate work first.** That means:
  - livespec-dev-tooling-jerpfe: dev-tooling's `check-coverage` re-runs the whole suite, measured at about 25 min per
    run.
  - bd-ib-hjo7lb: the orchestrator should omit `tests/` from coverage measurement. Test code is 72% of measured
    statements, and the livespec NFR's omit-only blocklist already excludes test scaffolding, so this is conformance,
    not a rule change.
- **Balance shards by measured duration.** Round-robin by file name leaves one shard about 5 min behind another on the
  median run.
- **Affected-test selection and result caching need a ratified spec change before any build.** "PR gate ≡ master gate"
  forbids a smaller gate on pull requests. The 100% per-file gate needs every file's coverage data. Content-hash reuse
  of coverage data, with the same rule on both events, is the only shape either report found compatible in principle.

## Where they differ, and which reading this synthesis adopts

**What the pre-test phase is.**

- **Astra** measured the pre-test phase (282-358 s per shard) but explicitly could not attribute it. It proposed
  replacing xdist inside each shard with 3 disjoint pytest processes, so each file is collected once rather than once
  per worker.
- **Fable** attributed most of it to `livespec_dev_tooling.flake_retry`, which re-derives each test FILE's closure once
  per collected ITEM (13,170 items, 1,465 files) in every worker. Its evidence:
  - **A natural experiment across all 16 sharded runs.** When the change set contains `justfile`, `pyproject.toml`,
    `uv.lock`, `conftest.py` or the plugin itself, the plugin returns early. Pre-test is then 156-229 s per shard.
    Otherwise it is 285-881 s, median about 520.
  - **The unsharded job.** Pre-test was 1,015 s with the loop running and 70 s when the loop was skipped.
  - **A local cProfile.** 72% of collect-only time is inside `mark_untouched_tests`.
  - **The timing.** The cost appeared in CI exactly when livespec-dev-tooling-bejgoo (v1.172.0) made the change set
    computable in depth-1 checkouts, at ~17:11Z 2026-11-04.

**Adopted: Fable's reading.** It is measured three independent ways and matches the code. Astra's disjoint-process
experiment is still sound, but it should be judged against the floor left after the plugin is fixed (~220 s per
shard). It should not be judged against today's inflated phase, most of which the plugin fix removes outright.

## Finding: sharding traded runner-minutes for wall time

These are the first five clean orchestrator PR runs after livespec-orchestrator-beads-fabro#4441. Runs that sat
through the 08:05-09:34Z k3s job-pod outage are excluded. The coverage chain runs from the first shard start to the
end of check-coverage, from `actions/runs/<id>/jobs`.

| Run | Coverage chain (min) | Runner-min, whole run | Shards (min) |
|---|---:|---:|---|
| 41984440269 | 24.4 | 83.9 | 20.2 / 17.0 / 16.5 / 18.7 |
| 41985277701 | 12.3 | 44.0 | 7.8 / 7.4 / 9.7 / 9.1 |
| 41988368018 | 13.9 | 50.1 | 10.3 / 9.1 / 9.4 / 10.8 |
| 41989460528 | 19.3 | 60.1 | 15.8 / 12.3 / 14.2 / 6.9 |
| 42003433611 | 19.1 | 58.1 | 12.9 / 16.7 / 5.6 / 12.4 |

- **Wall time:** the median coverage chain is **19.1 min**, against the unsharded median of 35.0 min (p90 63.4).
- **Cost:** the median is **58.1 runner-minutes per PR run**, against 44.72 after the 3-worker cap and 32.98 at the
  research-004 baseline.
- **Ruling:** legacy-coordinator-agent (~09:54Z) ruled to keep sharding and recover the minutes, in this order:
  balanced shards, then cheaper per-shard collection, then livespec-dev-tooling-6e5pyj.
- **Consequence for that order:** the analysis above shows the plugin fix IS the cheaper per-shard collection, and it
  is the largest single item. It is listed first below, and the coordinator has been told.

## Ranked recommendation

1. **Fix the flake-retry closure loop.** Memoize the decision per test file, cache the parse per module, and compute
   the change set once per process: **livespec-dev-tooling-5y3luz**.
   - Measured basis: about 300 s of plugin time per shard.
   - Saving: about 20 runner-min per orchestrator PR run and about 5 min off the coverage chain. It also lands fleet-wide,
     in every pytest session, including factory Red/Green legs, local `just check`, dev-tooling's own coverage job and
     the root-uid leg.
   - Gate risk: none, because the markers and verdicts are identical. Spec change: none.
2. **Remove the proven duplicates and rebalance:**
   - jerpfe: dev-tooling, about 25 min per run.
   - hjo7lb: omit `tests/`, about 2 min wall and 8 runner-min.
   - **bd-ib-eq5ics:** duration-balanced shards, about 2-3 min wall. Runner-minutes are neutral, because balancing moves
     time between shards rather than removing it.
   - Fold the 1-second `check-coverage` consumer into the combine job: about 1.5 min wall and one job setup per run. It
     is not filed yet, because the `check-coverage` slug must stay a literal matrix member.
   - Make the 11 Honeycomb provisioner calibration tests in-process: about 250 worker-seconds.
3. **Re-measure, then choose the collection lever.** With the plugin fixed, measure the per-shard collection floor. If
   it is still about 220 s, compare Astra's disjoint processes, Fable's 8 shards with `--dist worksteal`, and
   `--assert=plain` on the coverage run. The last of these is a diagnostics policy call, not a verdict change.
4. **Structural, behind a propose-change:** content-hash reuse of coverage data, built on the closure analysis the
   plugin already has. The scheduled full runs serve as the safety net.
5. **Thin the root-uid leg.** Run it only when master moved since the last run, or nightly. That is 10 runs in 16 h at
   22-66 min each today.
6. **Fewer tests.** Run a small mutation kill-matrix pilot under rule-26 first, then prune what the matrix proves
   redundant. Coverage-overlap analysis can rank candidates but cannot prove redundancy.

The maintainer's two named options map onto this list as follows. Parallelisation is item 3 and is mostly spent;
"fewer tests" is item 6, which is right for rule-26's own reasons but is not the lever for this runtime.

## Carriers recorded

The carrier-map scope event on livespec-dev-tooling-ib3oe3 (2026-11-05 ~10:40Z) adds livespec-dev-tooling-5y3luz and
bd-ib-eq5ics to assertion 3. The disjoint-process and `--assert=plain` experiments, content-hash reuse, and suite
pruning are recorded there as explicit deferrals.

---

## Appendix A — Fable report (verbatim)

### Coverage job runtime — independent analysis (Fable, 2026-11-05)

Read-only analysis for the maintainer. No repository, ledger, PR, dispatch or session was touched.
Every figure is marked **[M]** measured (source named) or **[E]** estimated. The other model's report
was not read.

**Headline.** The coverage job is slow for a reason neither of the two named options addresses:
since 2026-11-04 ~17:11Z, every xdist worker in every pytest session of every fleet repository spends
more time inside the `livespec_dev_tooling.flake_retry` plugin than it spends running tests. The
plugin re-parses the test file, its conftest chain and its whole transitive in-repo import closure
**once per collected test item** (13,170 items), not once per test file (1,465). Fixing that one
loop is a bug fix with zero gate risk and is worth more than the 4-shard layout was. After it, the
next wins are balanced sharding plus omitting `tests/` from measurement, and then a content-hash
coverage reuse built on the dependency analysis the plugin already has.

---

#### 1. Where the time goes

##### 1.1 The sharded layout, measured on the forge (n = 15)

Source: `gh api --cache` over `actions/workflows/ci.yml/runs` and `actions/runs/<id>/jobs` for
livespec-orchestrator-beads-fabro, successful runs created 05:52Z–07:45Z 2026-11-05 (the shard PR's
own run plus every post-merge run). Excluded: run 41990482610 (07:54Z, its combine job was killed by
the 08:04:56Z ARC runner-deprecation incident) and everything after 08:05Z (every k3s job failed at
0.1–10 min; the 09:24Z runs died at a 615 s workspace step). Scripts and raw data:
`scratchpad/jobs.py`, `scratchpad/orch-jobs.json`, `scratchpad/natexp.py`.

| Quantity | Median | p90 / max | Note |
|---|---:|---:|---|
| Shard start → `check-coverage` end (coverage critical path) | **17.5 min** | 23.5 / 24.1 | min 11.8 (the quiet 06:05Z run the brief quotes as 12.0) |
| Longest shard job | 14.8 min | 20.2 | shard jobs ranged 6.0 – 20.2 min across runs |
| Shortest shard job in the same run | 10.0 min | | median max−min **3.4 min** |
| Runner pickup (run created → first shard start) | 0.3 min | 0.4 | queueing is not the problem |
| Tail after the last shard | **2.8 min** | | 19 s gap + 102 s combine job + 17 s gap + 30 s check-coverage job |
| Shard job setup (job start → `just coverage-shard` step) | 16–44 s | | checkout 5 s, init containers 5 s, prepare workspace 4 s, nonroot prep 1 s, upload 4 s |
| Runner-minutes of the coverage chain per run | ≈ 50 + 1.7 + 0.5 | | 4 shards × ~12.5 + combine + check [E from the step medians] |

The n=1 figure in the brief (12.0 min) was the best case, not the typical one: the median
critical path is 17.5 min and the longest shard is where most of it goes.

**Systematic round-robin imbalance [M].** Median `just coverage-shard N 4` step duration by shard
index: 1 = 787 s, 2 = 553 s, 3 = 679 s, 4 = 862 s. Sorting file names and dealing them round-robin
puts the expensive files unevenly; shard 4 is ~5 min slower than shard 2 on the median run.

##### 1.2 Inside a shard: the pre-test phase dominates

The shard log stamps the script start (`:: coverage-shard N/4`), the first flush (pytest's banner,
`created: 3/3 workers`, `3 workers [N items]` all share one timestamp, which is the first test
result), and the `slowest durations` line. So "pre" = uv run + pytest start + xdist spawn +
per-worker collection + everything in `pytest_collection_modifyitems`; "test" = test execution.

| Run (created) | Change set hits `_UNSAFE_NAMES`? | pre / test seconds per shard (1,2,3,4) |
|---|---|---|
| 41976780315 05:52 (shard PR) | yes (`justfile`) → closure loop skipped | 203/191 · 156/172 · 219/284 · 213/220 |
| 41978119805 06:05 (merge) | yes (`justfile`) → skipped | 229/197 · 227/199 · 227/279 · 218/215 |
| 41981821804 06:38 | no → loop ran | 419/131 · 305/153 · 352/118 · 366/213 |
| 41984440269 07:02 | no → loop ran | **867**/221 · 710/264 · 734/219 · **790/378** |
| 41984375523 07:01 | no → loop ran | 881/235 · 711/265 · 742/227 · 788/399 |
| 41989460528 07:45 | no → loop ran | 586/236 · 230/148 · 518/185 · 541/381 |
| all 14 loop-ran runs | | pre 285–881 s (median ≈ 520); test 112–399 s (median ≈ 200) |
| the 2 loop-skipped runs | | pre 156–229 s; test 172–284 s |

Source: `natexp.py` over all 16 sharded runs; change sets from `pulls/<n>/files` / `commits/<sha>`.
The only thing that differs between the two groups is whether `flake_retry.retry_marker_for` returns
early (`justfile`, `pyproject.toml`, `uv.lock`, `conftest.py` or the plugin file in the change set)
or runs its closure for every item. When it runs, the shard's pre-test phase is **2–4× its test
phase**.

**The same effect on the unsharded single job [M]** (`check-per-file-coverage (nonroot)` logs,
master pushes):

| Job | Date | Workers / items | pre-test | test phase | Why |
|---|---|---|---:|---:|---|
| 124730447982 | 11-01 02:46 | 8 / 12,767 | 34 s | 143 s | no plugin yet (research 003's reference run) |
| 126165727652 | 11-03 19:52 | 8 / 12,906 | 52 s | 228 s | plugin loaded, change set unknown at depth-1 → withheld |
| 126512025533 | 11-04 10:03 | 3 / 12,980 | 104 s | 1,304 s | 3-worker cap live; still withheld |
| 126828769570 | 11-04 20:01 | 3 / 13,167 | **1,015 s** | 1,346 s | bejgoo fix (dev-tooling v1.172.0, pinned 17:11Z) makes the change set computable → loop runs |
| 126993752186 | 11-05 01:46 | 3 / 13,163 | 70 s | 1,032 s | pin-bump commit touches `uv.lock` → loop skipped |

So on the whole suite the loop costs **~900 s per worker** (≈ 0.07 s per item), and every worker
pays it. This is why the job's median moved 25 → ~37 min at 17:11Z on 2026-11-04 (push-run trend in
`scratchpad/tasks/bb92a6rl2.output`: 08:09Z–17:11Z 11.8–35 min, after 17:11Z 17.8–64 min), on top
of the 3-worker cap's 12 → 25 min step at 08:09Z that research 004 identified.

**Local confirmation [M]** (dev host, load 15–36, so absolute numbers are inflated; ratios hold):

- cProfile of `pytest --collect-only` on 10 test files / 86 items: 12.0 s of 16.8 s (72 %) inside
  `flake_retry.mark_untouched_tests` → `retry_marker_for` (86 calls, 0.137 s each) → `_closure`;
  935k `ast.walk` calls. `scratchpad/collect10.prof`.
- 39 files / 448 items, collect-only: with plugin 47.4 s, with `-p no:livespec_flake_retry` 14.5 s;
  under `--cov --cov-branch`: 110 s vs 47 s.
- The cause is in `livespec_dev_tooling/flake_retry.py`: `mark_untouched_tests` loops
  `for item in items: retry_marker_for(test_path=Path(str(item.path)), ...)`, and `_closure`
  re-reads and re-parses the test module, every `conftest.py` up the tree (`tests/conftest.py` is
  1,214 lines) and the transitive in-repo import closure, with no cache keyed on `test_path` or on
  module path. The result depends only on the test file, so 13,170 computations do the work of
  1,465, and a per-module AST cache would reduce those to roughly the number of distinct modules.
  The plugin shipped 2026-11-03 (crxcy4, v1.166.0); the per-item cost was masked in CI until bejgoo
  (v1.172.0) made the change set computable at depth-1 on 2026-11-04.

##### 1.3 The rest of the budget (quiet run 41978119805, loop skipped, so this is the floor)

| Component | Measured | Share of one shard's ~430 s |
|---|---|---:|
| Collection + imports + xdist spawn, per worker, 366 files, under branch tracing | ~220 s [M, 2 runs] | ~50 % |
| Test execution, 3 workers, ~3,300 tests | 197–279 s [M] | ~50 % |
| Tests ≥ 10 s (sum of listed phases, all 4 shards) | 558 s of ≈ 2,700 worker-s [M] | 20 % of test worker-time |
| `coverage combine` of 4 shard files | 1.4 s [M] | — |
| `per_file_coverage` verifier (single-threaded, 187,838 statements of which 72 % are `tests/`) | ~62 s [M] | combine job 102 s total |
| `check-coverage` consumer job | 30 s job, 1 s of actual work [M] | + 17 s gap |

- Collection is paid **12 times per run** (4 shards × 3 workers; each xdist worker collects every
  file of its shard). Research 003 measured the cold cost as assertion rewriting (56 CPU-s of 85 for
  the whole suite) — but that was 34 s per worker for 1,384 files on 11-01, against ~220 s per
  worker for 366 files now. The 2 loop-skipped runs still pay `change_paths()` (five git queries
  including a `fetch --deepen=1` per worker) and run 12 collections at once on one node; I could not
  split those from the import cost from logs alone. Local: coverage tracing makes collection
  **3.2× slower** (14.5 → 47 s, no plugin) [M].
- Coverage tracing overhead on in-process test execution: **1.9×** (16 files, 127 tests: 15.8 s →
  30.3 s, no plugin) [M]. CTracer is in use (`coverage debug sys`); `COVERAGE_CORE` unset.
- The slowest tests [M, `--durations` in the logs]: `tests/test_provision_honeycomb_tdd_calibration.py`
  — 11 tests, ~250 s (subprocess-driven, `subprocess.run` of the provisioner);
  `tests/test_phase1_mechanical_coverage.py::…no_newly_covered_warnings` 59–67 s;
  `tests/dev-tooling/checks/test_no_fleet_toolchain_literals.py` 25 + 13 s;
  `tests/integration/test_fleet_launch_scenario297.py` 15 s (already trimmed by lwiila);
  `test_fabro_port_seam.py` 13 + 12 s. 149 test files call `subprocess.run/Popen/check_output`
  and 59 spawn a Python interpreter; each Python child pays interpreter start + coverage start +
  data-file write because of the `.pth` hooks (research 003).
- Within-shard tail: in shard 3 of the quiet run the last 116 s of 279 s produced one progress
  line — the 59 s and 37 s tests ran at the end with idle workers beside them.
- Under load the test phase scales ~1.2–1.9× and the pre-test phase 3–4× (41984440269 vs
  41978119805), because the pre-test phase is pure CPU on 12 concurrent processes plus the loop.

**Worker-time budget per run, loop running, moderate load [E from the medians above]:** plugin loop
≈ 4×3×300 s = 3,600 s (≈ 40 %), collection/imports ≈ 4×3×220 s = 2,640 s (≈ 30 %), tests ≈ 2,400 s
(≈ 28 %), everything else < 2 %. Only the last 28 % is what "fewer tests" acts on directly.

##### 1.4 livespec-dev-tooling (second repo) [M, cached jobs 2026-11-05 05:00–07:36Z]

`check-per-file-coverage` 11.7–41.3 min (12 runs) and `check-coverage` **5.7–43.9 min** because it
re-runs the suite (jerpfe, `ready`). Serial chain: 17–85 min per run. Its 650 test files / 5,686
tests also load the same plugin (dev-tooling is the plugin's own package and depends on
`pytest-rerunfailures==14.0`), so §1.2 applies there too.

##### 1.5 The root-uid leg [M]

`ci-root-uid.yml` ran 10 times in the last 16 h at 21.9–66.5 min wall each (unsharded, 3 workers),
≈ 5–8 churn-slot hours per day on k3s. It re-runs on schedule even when master has not moved.

---

#### 2. Options

Format: effect (wall / runner-min) · cost · gate-strength risk · spec conflict.

##### A. Fix the flake-retry closure loop — memoize per test file, cache per module  ← do first
- **Effect [M-based E]:** pre-test phase per shard median ~520 s → ≤ 220 s (the loop-skipped floor);
  longest shard 14.8 → ~9 min; critical path 17.5 → ~12 min; ≈ 20 runner-min per PR run saved;
  the unsharded root leg and dev-tooling's job drop by ~15 min each. The same saving lands in every
  pytest session fleet-wide: factory Red/Green legs, local `just check`, livespec, the drivers.
- **Cost:** one dev-tooling Red/Green PR (`livespec_dev_tooling/flake_retry.py`): a `dict[Path,
  marker]` keyed on `test_path` inside `mark_untouched_tests`, plus an `ast.parse`/`_imports`
  cache per module path inside `_closure`. Existing tests in `tests/livespec_dev_tooling/
  test_flake_retry*.py` pin the behaviour. Release → automatic pin bumps.
- **Risk:** none to the gate (identical markers, identical verdicts).
- **Spec:** none.
- **Also worth doing in the same change:** compute `change_paths()` once per session instead of per
  worker (five git calls incl. a network fetch ×3 workers), or in the controller and pass it via
  `config` — small, [E] 5–15 s per shard.

##### B. Omit `tests/` from measurement (bd-ib-hjo7lb, `ready`)
- **Effect [E from research 003 + §1.3]:** verifier 62 s → ~20 s per run; tracing during collection
  and test execution cheaper (test bodies are 72 % of measured statements) — I estimate 15–30 % off
  the collection phase and 5–15 % off the test phase; ≈ 2 min wall, ≈ 8 runner-min.
- **Cost:** `omit` edit + the third DoD bullet (dead test helpers). Low.
- **Risk:** loses "dead test helper" detection unless another check carries it.
- **Spec:** conformance, not a change — livespec NFR §"Code coverage thresholds" (l. 1095) says the
  omit-only blocklist excludes "test scaffolding".

##### C. Balance shards by measured duration, more shards, work-stealing
- **Effect [M for the imbalance]:** today's max−min of 3.4 min and the shard-4-vs-2 gap of 5 min
  mostly vanish → ~2–3 min off the critical path. 8 shards instead of 4: per-shard collection
  halves (each worker collects 183 files) and tests halve → shard wall ~4–5 min after A [E];
  runner-min roughly neutral (+4 setups of ~0.7 min vs. less redundant collection); churn slots 8
  per PR (15 of 21 were free on poweredge at 05:05Z). `--dist worksteal` (xdist 3.8 has it) removes
  the within-shard tail (~1–2 min on the longest shard [E]).
- **Cost:** the shard script reads a committed timings file (from `--durations` JSON of a master
  run, refreshed by a scheduled job) and deals greedily; one-line xdist flag. Low–medium.
- **Risk:** none (same union of files; a stale timings file only unbalances).
- **Spec:** none.

##### D. Workers per pod from the pod's CPU (livespec-dev-tooling-6e5pyj, `ready`)
- **Effect [M, one point]:** the 6-worker window on 11-04 13:29Z ran the test phase in 318 s vs
  ~1,300 s at 3 workers under load the same morning; 6 workers per shard halves the test phase
  (−1.5–2 min) and halves nothing else. **Does not reduce worker-time**; the cap was a
  node-saturation ruling, so this needs the per-node CPU budget 6e5pyj owns.
- **Cost:** medium (DERIVATION.md, hook template, kueue quota).  **Risk:** none.  **Spec:** none.

##### E. Cut the redundant per-worker collection
- Options: (i) more shards with fewer workers each (C already does this), (ii) warm the rewritten
  `*-pytest-8.3.4.pyc` through `actions/cache` with normalised mtimes (pytest validates by
  mtime+size, and a fresh checkout has checkout-time mtimes, so the cache needs a `touch -d` pass —
  fiddly), (iii) `--assert=plain` on the coverage run only (removes the 4–10× rewrite cost research
  003 measured, but failure messages lose introspection — a policy call).
- **Effect [E]:** collection 220 s → 60–100 s per shard; ≈ 2 min wall, 25 runner-min.
- **Cost:** low for (iii), medium for (ii).  **Risk:** (iii) weakens diagnostics, not the verdict.
- **Spec:** none, though (iii) deserves a line in the orchestrator's testing-approach section.

##### F. Faster tracing: `COVERAGE_CORE=sysmon`
- **Not available.** The fleet is pinned at Python **3.10.16** (`requires-python`, pyright
  `pythonVersion`, the sandbox image: the shard log prints `Python 3.10.16`). `sysmon` needs 3.12,
  and **branch** coverage under sysmon needs 3.14's branch events. So this is a fleet Python
  upgrade (image, pins, PEP-695-era checks). Potential [E]: the 1.9× tracing overhead → ~1.2×, i.e.
  25–35 % off collection + tests. High cost, not a near-term lever; record it as the prize for the
  3.14 upgrade.

##### G. Fewer or cheaper tests
- **Mutation-score-guided pruning** (plan `fleet-mutation-testing-rule-26`, epic
  livespec-dev-tooling-oi2two, `backlog`): the right long-term instrument, but its own survey
  (research 001) found mutmut non-functional in every Python repo and `pure_trees` unarmed, and the
  plan has had no commit since 2026-10-28. Months, not weeks. Each pruned test saves ~0.07 s of
  loop (until A) + ~0.2 worker-s of execution; halving the suite after A saves ≈ 3–4 min of a 9-min
  shard [E]. **Risk:** real — mutation kill-matrix pruning is the only pruning method that proves a
  test is redundant; coverage-overlap pruning (below) does not.
- **Coverage-overlap pruning** (cheaper, available now): run once with `--cov-context=test`;
  a test whose covered lines/arcs are a strict subset of another's in the same module is a
  *candidate*. Weak evidence (an assertion can be unique while its coverage is not). Use it to
  rank what the kill matrix looks at first, not to delete.
- **Property-based tests replacing example tests:** hypothesis is already a dependency and used in
  11 files here (45 in livespec). Replacing N example tests by one `@given` with 100 examples cuts
  item count (good for collection and the loop) but not execution time, and it changes the
  behavioural obligation of the spec's scenario tests. Net runtime effect ≈ 0 before A, small after.
  It is not "fewer tests" in the runtime sense. **Spec:** livespec NFR §"Property-based testing for
  pure modules" mandates PBT on pure modules; replacing scenario tests would be a propose-change on
  the orchestrator's testing-approach section.
- **In-process instead of subprocess (the honeycomb calibration file first):** that one file is
  250 s of worker time (10 % of all test execution); a module-scoped fixture running the
  provisioner once, or an in-process call, saves ~4 min worker-time / ~1 min on its shard [E].
  Then `test_phase1_mechanical_coverage` (60 s) and the 59 Python-spawning files. Low cost each,
  long tail, no gate risk, no spec conflict (the subprocess-coverage `.pth` hooks keep measuring
  whatever remains).

##### H. Test-impact / affected-test selection
- **Spec:** forbidden in the naive form — livespec NFR l. 1327 "PR gate ≡ master gate": no gating
  job or `just check` target may run a smaller set on a PR than on a master push. BUT the same
  section (l. 1329, ratified 2026-11-04, "Config-value fast path") already admits ONE changeset
  predicate, computed from the diff alone and applied identically on both events. Any affected-test
  selection would have to take that shape (same reduced set on PR and master) and would need a
  propose-change extending the admitted predicate class. The 100 % per-file gate is the harder
  constraint: per-file coverage of an untouched file cannot be asserted without its tests' data —
  unless that data is reused (I).

##### I. Content-hash reuse of coverage data (testmon-like), reconciled with the 100 % per-file gate
- **Idea:** the flake-retry plugin already computes, per test file, the conservative closure (test
  module + conftest chain + transitive in-repo imports + string-literal path hints) and the
  session's change set. Shard the suite as today, but for every test file whose closure is
  untouched since the merge-base, *reuse* that file's coverage rows from the merge-base master
  run's published `.coverage` (per-file sliced via `--cov-context` or one data file per test file)
  instead of running it. `coverage combine` fresh + reused → the verifier still judges full-suite
  data at 100 % per file; the verdict's inputs are identical when the closure analysis is right.
- **PR ≡ master:** the master push applies the same rule against its parent, so neither event runs
  a smaller *gate*; what shrinks is re-execution of provably unaffected tests.
- **Effect [E]:** typical PR touches a handful of files → most shards near-empty → coverage chain
  3–6 min, runner-min ≈ 10. The scheduled root-uid run (full suite, 3-hourly) and a nightly full
  nonroot run are the independent safety net that catches a closure miss within hours.
- **Cost:** high (data layout, merge-base artifact lookup, closure as a shared library, failure
  modes when the base artifact is missing → fall back to full run). **Risk:** medium — dynamic
  imports, fixtures reading data files, subprocess-executed code the AST closure cannot see; the
  plugin's `_UNSAFE_NAMES` and literal matching are already the conservative guards for the same
  question. **Spec:** needs a propose-change on livespec NFR §"Code coverage thresholds" ("computed
  under `pytest --cov`") and §"PR gate ≡ master gate" to admit reused data with an explicit
  invalidation rule; do not build before that is ratified.

##### J. Move or thin the root-uid leg
- 10 runs / 16 h at 22–66 min on k3s. Options: shard it the same way (saves wall, not slots); run
  only when `master` moved since the previous run (today it re-proves the same SHA); once nightly
  instead of 3-hourly. [E] −3 to −6 churn-slot hours/day. Low cost. **Spec:** none — the
  scheduled run is additional to the PR gate; bd-ib-sfa2's argument needs each uid gated at 100 %,
  not a cadence. Maintainer direction already moved it off PRs (xufdwx).

##### K. Drop the `check-coverage` consumer job; parallelise the verifier
- The consumer job does 1 s of work in a 30 s job plus a 17 s gap; the verifier is 62 s
  single-threaded. Fold the aggregate `fail_under` into the combine job (the per-file verdict file
  already exists) and run `per_file_coverage` over a process pool (research 003 lever 3).
- **Effect [E]:** −1.5 min critical path, −1 job setup per run. **Cost:** low. **Risk:** none.
  **Spec:** `check-coverage` is a tool-backed slug that must be a literal matrix member
  (check-tool-backed-check-completeness) — keep the slug, change what it does.

##### L. Hosted-runner shards (a measurement, not a recommendation)
- The 62-min hosted figure was one 4-vCPU runner with 1 worker, unsharded, loop withheld — honest
  execution time, ≈ 1.4× slower per worker than k3s. 12 hosted shards × 2 workers would be ~6 min
  each plus image pull (the sandbox image is pulled per hosted job) [E]; free runner-minutes, zero
  churn slots. The maintainer ruled coverage stays on k3s; the sharded hosted shape was never
  measured, so one `workflow_dispatch` pilot would settle whether the ruling still costs anything.
  **Spec:** none.

##### M. Small things with small effects
- Job setup is 16–44 s per shard and ~45 s in the combine job: fine.
- `uv run` adds ~1 s; `hypothesis` is a plugin but idle; `local_gate_slots` is inert in pods.
- Dev-tooling's duplicate suite run in `check-coverage` (jerpfe, `ready`): −6 to −44 min per
  dev-tooling run. Not an orchestrator lever but the largest single waste in the second repo.

---

#### 3. Ranked recommendation

1. **Fix `flake_retry` so the closure is computed once per test file with a per-module AST cache
   (A), and compute the change set once.** Expected: coverage critical path 17.5 → ~12 min median,
   ~20 runner-min per PR run, and a fleet-wide saving in every pytest session (factory Green legs
   included). Measure before/after with the script→first-flush timestamps in the shard logs
   (`natexp.py` does it); expect pre-test ≤ 220 s per shard. This is a correctness-neutral bug fix;
   it can go today.
2. **Reshape the shards: balance by measured file durations, go to 8 shards, add `--dist
   worksteal`; land hjo7lb (omit `tests/`) and fold the consumer job into the combine job
   (B + C + K).** Expected after 1: critical path ~7–8 min, runner-min roughly flat vs today's ~52
   (fewer redundant collections offset more setups). Measure first: the per-shard collection time
   with the plugin fixed — if it is still ~220 s, collection (not tests) decides the shard count,
   and option E(iii) `--assert=plain` on the coverage run becomes worth its policy call.
3. **Then the structural win: content-hash coverage reuse built on the flake-retry closure (I),
   behind a propose-change**, with the scheduled full runs as the safety net; in parallel, make the
   honeycomb calibration tests in-process (G, ~1 min on their shard) and thin the root-uid schedule
   (J). Hold the Python 3.14 / sysmon upgrade (F) as the lever that follows, not one for now.

On the two options the maintainer named: parallelisation is already mostly spent (4 shards bought
the 35 → 17.5 min median; the next doubling buys ~3 min and nothing on runner-minutes until the
plugin loop and redundant collection are gone), and "fewer tests" acts on the ~28 % of worker-time
that is test execution — valuable for the rule-26 reasons, but not the lever for this runtime. The
kill-matrix plan is the honest way to shrink the suite; coverage-overlap ranking can feed it.

---

#### 4. The unfinished "fuzzing work" and the maintainer's "track"

Searched (delegated sweep, spot-checked by me): every `plan/` tree incl. `plan/archive/` under
`/data/projects/livespec*` (13 repos), their `SPECIFICATION/`, `.ai/`, `docs/`; all 11 beads
tenants read-only with `--status all` (dumps in `scratchpad/ledger-*.json`); Claude transcripts
under `~/.claude/projects` (21 days); Codex sessions under `~/.codex`.

- **There is no unfinished Python fuzzing or hypothesis-migration effort anywhere in the fleet.**
  `hypothesis==6.122.3` is already a dependency in livespec, dev-tooling, both orchestrators and the
  runtime (livespec 45 importing files, orchestrator 39, dev-tooling 9); the spec mandates PBT on
  pure modules. No `atheris`. The only real fuzzing is the Rust console's finished cargo-fuzz tree
  (`livespec-console-beads-fabro/fuzz/`, `check-fuzz`, nightly soak; archived plan
  `test-adequacy-gates`) — crash-finding, unrelated to shrinking Python suites. The only related
  open item is bd-ib-6qb2mc (`blocked`): `pure_trees` empty so `check-pbt-coverage-pure-modules`
  scans zero files (plan `pure-trees-role-key-scope`, livespec-dev-tooling-8zv3) — that is about
  *adding* property tests.
- **What "started but didn't finish" most plausibly is: the mutation-testing lineage.**
  `plan/mutation-testing-keystone/handoff.md` (2026-08-04; `livespec-mutreal`, `livespec-mutreal.1`
  both `backlog`) and its reboot **`/data/projects/livespec-dev-tooling/plan/fleet-mutation-testing-rule-26/`**
  (epic `livespec-dev-tooling-oi2two`, `backlog`, commissioned by commit `e94ac495` on 2026-10-28;
  0 comments, 0 children, no commit since). Its charter is the maintainer's verbatim "10,000 tests
  is ridiculous… utilizing the existing mutation testing"; its DoD is a per-test kill matrix per
  repo, removal of tests the matrix proves redundant, and a before/after table of test counts and
  runtime. Its survey (`research/001-rule-26-survey-and-baseline-2026-10-28.md`) found mutation
  testing a no-op in every Python repo.
- **The "track" where the maintainer started discussing it:** coordinator session
  `~/.claude/projects/-data-projects-livespec-dev-tooling/229eb13f-213e-4fe7-aa19-aad6b9475029.jsonl`
  (epic `dfixhe`), 2026-10-27 23:00–23:02Z — "Okay 10,000 tests is ridiculous. I want you to start a
  subagent to commission a new plan…", followed by asks for test-count/runtime metrics and
  parallelisation. The word "fuzzing" does not appear in the maintainer's messages there; the
  mechanism named was mutation testing. The 2026-11-05 07:24Z remark itself is in session
  `721810d4-1da0-402d-97f2-44f7e377aafe.jsonl` (the ci-runtime-and-cost seat), whose assistant also
  mapped it to rule-26. The runtime side is carried by `plan/implement-test-performance`
  (`sv6m5p`, research 003 is the suite profile) and `plan/ci-runtime-and-cost` (`ib3oe3`, research
  004 is the runner-minutes baseline). Codex history has no fuzz/PBT prompts in Oct–Nov 2026.

---

#### Appendix — sources and reproducibility

- Forge reads: `gh api --cache 1h|2h` on `repos/thewoolleyman/livespec-orchestrator-beads-fabro/
  actions/workflows/ci.yml/runs`, `actions/runs/<id>/jobs`, `actions/jobs/<id>/logs`,
  `pulls/<n>/files`, `commits/<sha>`; dev-tooling and `ci-root-uid.yml` likewise.
  Scripts: `scratchpad/jobs.py`, `scratchpad/natexp.py`; data: `orch-runs.tsv`, `orch-jobs.json`,
  `orch-push-runs.tsv`, `orch-push-jobs.json`, `logs/*.log`, `tasks/bb92a6rl2.output`.
- Local: `collect10.prof`, `sample40.txt`, `sample16.txt`; commands in the transcript. Dev host
  load was 15–36 during the runs — use ratios, not absolutes.
- Code read: `dev-tooling/just-coverage-shard.sh`, `dev-tooling/just-check-per-file-coverage.sh`,
  `dev-tooling/just-test-nprocs.sh`, `pyproject.toml` (coverage/pytest tables), `.github/workflows/
  ci.yml`, `livespec_dev_tooling/flake_retry.py`, `flake_retry_changes.py`,
  `ci-runner/k3s/phase2/arc/hook-pod-template.yaml`; livespec NFR lines 1095, 1327, 1329;
  dev-tooling plan research `implement-test-performance/003`, `ci-runtime-and-cost/002`, `004`.
- Ledger items read (from the dumps): bd-ib-m26pql, hjo7lb, uxv5al, lwiila, xufdwx;
  livespec-dev-tooling-6e5pyj, jerpfe, crxcy4, bejgoo, oi2two, sv6m5p, ib3oe3.

---

## Appendix B — GPT-6-Astra report (verbatim)

### Coverage runtime: reduce repeated work before reducing confidence

Read-only analysis, 2026-11-05. No repository edits, ledger writes, PRs, dispatches, or messages to other sessions were made. This report is the deliverable; no recommendation below is an instruction to dispatch work.

**Recommendation:** first remove proven duplicate work and implement the already-ratified exclusion of test modules from coverage; second, experimentally replace repeated xdist collection with disjoint file partitions inside the existing CPU budget; third, balance those partitions and make the identified expensive tests cheaper. Resume the mutation kill-matrix plan as a separate quality-and-size programme. Do not make completing that programme a prerequisite for runtime improvements.

The most important reframing is that **test count, executed examples, CPU work, runner occupancy, and feedback latency are different quantities**. One property test can execute hundreds of examples. Increasing workers can improve runner-minutes while leaving CPU-minutes unchanged. Removing thousands of cheap tests may save less than removing one repeated suite run or hundreds of repeated imports.

#### 1. What a recent run actually spent

##### Scope and measurement method

The principal specimen is successful orchestrator PR CI run [41985277701](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/actions/runs/41985277701), head `1c579ac584d6ad1e8f62fbfc926b3b7abbd549ac`, created 2026-11-05 07:09:47 UTC. I read all 19 jobs through the cached, paginated GitHub jobs API, the six coverage-chain job logs, and the combined coverage artifact. No suite or collection run was started locally.

Labels used below:

- **Measured:** directly read from this investigation's logs, artifact, source, or ledger.
- **Historical:** an earlier measurement in the named research note, not a new benchmark.
- **Estimate:** arithmetic or a conditional model; not a promised improvement.
- Runner-minutes mean the sum of job start-to-completion durations, excluding queueing. They are neither CPU-minutes nor a hosted-runner bill. Wall time means elapsed time along the coverage dependency chain unless stated otherwise.

The local orchestrator source inspected was `e926219fe50ca71206886823441449830a33706a`. The shared primary checkout was initially behind its remote and was refreshed by another actor during the investigation; I did not fetch, pull, reset, or edit it. Its pre-existing untracked measurement files were left alone. CI measurements are anchored to the run above, not to a moving checkout.

##### Current four-shard timeline

| Shard / job | Job ID | Tracked test files / collected cases | Job seconds | pytest seconds | Before collection-count banner | After banner through pytest completion |
|---|---|---:|---:|---:|---:|---:|
| 1/4 | 127104462774 | 367 / 3,204 | 544 | 503.43 | 358.47 s | 144.96 s |
| 2/4 | 127104462652 | 366 / 3,167 | 468 | 426.23 | 282.12 s | 144.11 s |
| 3/4 | 127104462687 | 366 / 3,178 | 446 | 406.86 | 294.42 s | 112.44 s |
| 4/4 | 127104462736 | 366 / 3,627 | 581 | 534.56 | 315.10 s | 219.46 s |
| Combine + per-file verdict | 127108248446 | all four artifacts | 76 | — | — | — |
| Aggregate verdict consumer | 127108822045 | same canonical verdict | 28 | — | — | — |

Every shard used **three workers**, Python **3.10.16**, pytest **8.3.4**, pytest-cov **6.0.0**, and coverage **7.14.1**. Total: **1,465 files, 13,176 collected cases; 13,171 passed and five skipped**. The brief's 1,463-file figure is already slightly stale.

The collection-count banner is emitted after xdist collection; pytest's session banner is buffered until that point. I derived session start from completion timestamp minus pytest's reported elapsed time. Therefore the pre-banner column includes worker startup, plugin and module imports, assertion rewriting, and collection. It is **not an isolated import profiler**. The post-banner column includes test setup/call/teardown, reporting/worker shutdown and within-shard coverage combination. It is **not pure test-body CPU time**.

Measured totals:

- First shard job start **07:10:10** to consumer completion **07:22:09**: **719 s = 11.98 min**.
- The six coverage jobs consumed **35.72 runner-minutes**. All 19 jobs consumed **44.00 runner-minutes**.
- The four pytest sessions sum to **1,871.08 job-seconds**; **1,250.11 s (66.8%) precede the collection-count banners**, and 620.97 s follow them. This is a sum of overlapping job durations, not CPU time.
- Shard setup to the test step took approximately **28–34 s each**; remaining shard overhead includes invocation startup and artifact upload/cleanup. Total non-pytest time across the four shard jobs was **167.92 s**.
- The slowest shard finished at 07:19:52. Combine waited **14 s**, then spent **24 s** setting up/downloading before its command. `coverage combine` itself took approximately **1.14 s**, from 07:20:30.679 to 07:20:31.822. The rest of the 40-second command step, roughly **38 s**, was verifier startup/analysis. Combine-job publication and cleanup consumed the remaining approximately 12 seconds.
- The consumer waited **19 s**, then held a runner for **28 s** to execute a verdict-reading command lasting about **one second**. It did **not** rerun pytest or coverage analysis.

This independently confirms that the new coverage chain is around 12 minutes on at least another specimen. It does **not** establish a new median/p90 or a causal speedup against the old 35-minute median: hardware, contention, revisions, and workload changed.

##### Where imports, tracing, and collection fit

The current logs establish a large pre-test phase, but cannot divide its 282–358 seconds into import, assertion rewrite, filesystem latency, scheduler contention and collection bookkeeping. There is no current per-worker CPU trace or import-time profile in these artifacts. Any claim that a particular one owns all five minutes would overstate the evidence.

Useful historical evidence is [implement-test-performance research 003](/data/projects/livespec-dev-tooling/plan/implement-test-performance/research/003-suite-time-profile.md): on November 1, cold versus warm local collection took 85 versus 32 CPU-seconds; assertion rewriting plus compilation took roughly 65 CPU-seconds; CI collection took 32 s with eight workers and 76 s with eighteen. Those numbers concern an earlier tree and environment. They support investigating repeated collection and cold rewriting; they cannot be directly scaled to today's 300-second phase. The brief's later >600-second collection observation and approximately 8,000 suite CPU-seconds were not independently reproduced here and are not used as measured denominators in the forecasts.

The mechanism is verified in [the current shard script](/data/projects/livespec-orchestrator-beads-fabro/dev-tooling/just-coverage-shard.sh): it passes one quarter of the files to pytest, then xdist's three workers each collect that same quarter. Thus the fleet performs approximately **three full-suite-equivalent file collections**, not twelve: sharding already removed the old whole-suite-per-worker problem across pods, but duplication remains inside each pod. This behavior is documented by [pytest-xdist](https://pytest-xdist.readthedocs.io/en/stable/how-it-works.html).

Coverage artifact **13396436238**, `coverage-data-nonroot`, was downloaded and queried as an in-memory SQLite database. It has branch data and coverage version 7.14.1:

| Artifact group | Measured files | Arc rows | Distinct positive source-line origins, summed per file |
|---|---:|---:|---:|
| `tests/` | 1,445 | 287,259 | 217,809 |
| Other files | 1,020 | 109,417 | 80,346 |

Tests account for **72.4% of arc rows** and **73.1% of these executed line origins**. These are database trace measures, **not coverage.py's statement denominator**. The historical 134,705/187,838 = 71.7% statement count is separately recorded in research 003. Both instruments support the conclusion that test scaffolding dominates the measured data; neither implies that excluding it will make the job 72% faster.

Branch tracing overhead has **not** been isolated by an identical traced/untraced experiment. The current `.python-version` is 3.10.16, and the pinned coverage implementation confirms that `sysmon` cannot run there. With branch coverage, Python 3.12/3.13 still fall back; Python **3.14+** is the relevant candidate. Coverage's [version-matched configuration documentation](https://coverage.readthedocs.io/en/7.14.1/config.html#run-core) explicitly states these limitations. Dropping branch coverage to use an older sysmon core would violate the gate.

##### Slow test files and phases

The logs retain only phases taking at least ten seconds. Therefore these are **lower bounds on file totals**, not an exhaustive file-duration ranking. All twenty reported slow phases were `call` phases; no setup/teardown phase crossed the ten-second reporting threshold. That does not mean setup and teardown were free.

| File, relative to `tests/` | Sum of reported slow calls | Largest individual call | What source inspection shows |
|---|---:|---:|---|
| `test_provision_honeycomb_tdd_calibration.py` | 106.75 s | 33.73 s, second-run idempotence | Repeated real Bash provisioner runs against a local HTTP fixture; shell/curl/process overhead is real. |
| `integration/test_workflow_publish_draft_hook_limit.py` | 65.73 s | 35.23 s, late push deadline | Real temporary git repos, real push/hooks/process trees and deliberate timeout behavior. |
| `livespec_orchestrator_beads_fabro/commands/test_dispatcher_stall_window.py` | 41.58 s | 21.58 s, cancellation attribution | Watchdog/integration behavior, with two other calls at ten seconds. |
| `test_phase1_mechanical_coverage.py` | 41.38 s | 41.38 s | One test invokes seven whole-repository mechanical checks. |
| `dev-tooling/checks/test_spec_id_presence_discipline.py` | 33.75 s | 12.52 s | Several tests independently walk/analyze the real package. |
| `livespec_orchestrator_beads_fabro/commands/test_dispatcher_heartbeat_probe.py` | 20.00 s | 10.00 s | Two watchdog cases. |
| `dev-tooling/checks/test_no_fleet_toolchain_literals.py` | 14.42 s | 14.42 s | Whole-repository conformance scan. |
| `integration/test_fleet_launch_scenario297.py` | 12.68 s | 12.68 s | Integration harness invoked from aggregate. |
| `livespec_orchestrator_beads_fabro/commands/test_dispatcher.py` | 10.34 s | 10.34 s | Dispatch-span forwarding case. |

These sum to **346.63 s of slow call durations**, overlapping across workers. They are not 346.63 seconds removable from the critical path.

A static scan of tracked Python test files found `subprocess.` text in **159 files**, `time.sleep(` in fourteen, `@given` in eleven, and **25 autouse fixtures across four conftest files**. Text hits include mocks and declarations; they are not subprocess counts or proof of prohibited sleeps. They identify profiling targets. Autouse fixtures affect test execution, not automatically collection; keep those two cost categories separate.

The longest shard has 14.5% more cases than the shortest-count shard. Mean pytest duration is 467.77 s against a maximum of 534.56 s. **Perfect balancing of the measured total work could recover at most about 67 seconds** under the simplifying assumption of identical runner speeds and no added overhead. Some variation instead comes from imports or node load. Per-worker idle time is not logged, so I cannot report a measured xdist idle fraction or attribute every tail second to scheduling.

##### The larger fleet saving: a suite really does run twice

Dev-tooling successful run [41980574918](https://github.com/thewoolleyman/livespec-dev-tooling/actions/runs/41980574918), head `731a4d7d5cdb28d5d05f8afe6810ea8564d0a20e`, independently confirms the duplicate-suite defect:

- Producer job **127089495100** ran 06:28:11–07:09:27, **41m16s**; all **7,609 tests passed**, pytest elapsed 2,388.72 s.
- Consumer job **127104341745** ran 07:09:44–07:35:27, **25m43s**. At 07:10:04 it explicitly rejected the existing coverage file because its provenance marker was missing, then ran all **7,609 tests again**, taking 1,516.60 s.
- Source confirms the consumer requires `.livespec-coverage-reuse-token`, while the workflow's producer artifact carries `.coverage` alone.

This is the ready work item **“In CI the dev-tooling coverage consumer reruns the whole suite because its provenance token is missing” (`livespec-dev-tooling-jerpfe`)**. Keeping the provenance check and transporting its receipt is the fix; removing the check would recreate stale/focused-coverage false passes. A consumer under three minutes would save **at least 22.7 wall and runner-minutes on this specimen**. This is a stronger fleet-wide opportunity than any speculative orchestrator test-pruning percentage.

#### 2. Gate constraints that change the answer

1. **100% first-party line and branch coverage remains mandatory.** Livespec NFR “Code coverage thresholds” requires omit-only measurement, forbids a `source` allowlist, and requires the reporting threshold of 100. Dev-tooling's identically named NFR also binds its threshold and exclusions.
2. **Excluding tests is now explicitly required locally.** Orchestrator [constraints, “Inherited from livespec”](/data/projects/livespec-orchestrator-beads-fabro/SPECIFICATION/constraints.md:25) says the omit list MUST exclude test modules under `tests/`. Its current coverage configuration still omits only selected test subtrees. Implementing **“Measure first-party source and omit test modules” (`bd-ib-hjo7lb`, ready)** is conformance, not a new policy proposal. Its acceptance text requires addressing or explicitly recording the loss of dead-helper detection. It is incorrect to assume measuring imported tests discovers a helper that was never imported.
3. **PR/master parity is necessary but not sufficient.** Livespec NFR's CI gate rule forbids fewer gating checks on a PR than on a master push. Applying the same unsafe filter to both events meets symmetry while still violating full-suite requirements. NFR “Writing Green,” dev-tooling's test-only-commit clause, and the maintainer's [implement-test-performance charter](/data/projects/livespec-dev-tooling/plan/implement-test-performance/research/001-charter-implement-test-performance.md) retain full-suite validation. A same-name check that silently selects fewer tests does not settle the policy question.
4. **There is already one approved no-suite class.** Livespec NFR **“Config-value fast path”** requires schema/parse-only validation for changes consisting exclusively of values of specifically listed capacity/cap/timeout/quota keys, identically on PR and master. It explicitly says every other change runs the full aggregate. This is materially narrower than “docs-only” or “no Python changed.” I found no such class-selection logic in the two inspected `ci.yml` workflows; trace the existing carrier before duplicating implementation.
5. **Root moved already.** The root-UID leg is scheduled in `ci-root-uid.yml`, every three hours with an unchanged-head skip. The nonroot leg stays on PR/master. The earlier root move is not another incremental PR saving. The dated research puts its merge at November 3 (#4293), rather than treating the brief's November 4 date as authoritative.
6. **Time-based tests already have a conformance route.** Orchestrator constraints prohibit real-time sleeps as condition waits and elapsed-time pass/fail verdicts, allowing reasoned exemptions when real time is the subject. Replacing waits with injected clocks or explicit events often needs no new rule. A process-kill/deadline integration test still needs to prove real OS behavior; arbitrarily shortening its bound can recreate known flakes.
7. **100% reported coverage is not an exhaustive dependency proof.** The inspected shared verifier analyzes files in the coverage report. It cannot by itself certify that every required module entered the measured universe, nor that all historical regressions were tested. Any selection/cache scheme must retain explicit file-universe and input/provenance checks. Unioning old arc data into a new tree can manufacture 100% without executing the affected obligation.

#### 3. Options, cost, expected effect, and policy fit

Estimates are against the 11.98-minute / 35.72-runner-minute orchestrator coverage chain unless another baseline is named. They overlap and **must not be added together**. Implementation effort is an order-of-magnitude engineering estimate, not a dispatch promise. “No new proposal” means no identified coverage-policy conflict; ordinary verification and repository governance still apply.

| Option | Expected wall-time and runner-minute effect; basis | Implementation cost | Gate risk and spec disposition |
|---|---|---|---|
| **Repair dev-tooling artifact provenance transport** | **22.7–25 min saved** in both wall and runner time on the measured 25m43s duplicate consumer, depending on retained reporting/setup. Not an orchestrator saving. | Small, roughly half to one day plus CI proof; existing ready carrier. | Low if receipt/data/tree validation is preserved. No new policy proposal. |
| **Omit test modules from coverage** | Estimate **0.4–1.0 min wall, 0.8–2.1 runner-min**: analyzer 38 s × 60–70% reduction plus a hypothetical 5–15% reduction of the 621 aggregate post-banner seconds. No collection saving credited. | Small, half to one day including first-party path controls. | Low; explicitly required by local constraints. Retain all tests and 100% first-party line/branch threshold. Record dead-helper implications. |
| **Partition before pytest: three disjoint single-process pytest invocations inside each existing shard pod** | **Highest-upside same-capacity experiment:** estimate **1.8–3.5 min wall and 7–14 runner-min saved** if half to all of the current pre-banner work is file-proportional. Calculation below. | Medium, about 1–3 days for manifests, process supervision and correct artifact/exit handling. | Low-to-medium execution risk, no intended weakening. Must prove all node IDs execute exactly once, preserve setup/teardown, combine all branch data, and fail on any missing/failed partition. No new policy proposal identified. |
| **Duration- and collection-weighted four-shard balancing** | **0–1.1 min wall**, approximately **0 runner-min** saved at fixed total work; 67 s is the current idealized max-to-mean gap. May save more only if it also avoids repeated expensive fixtures. | Small/medium, about 1–2 days once complete timings exist. | Low. Balance setup+call+teardown and cold collection, not just counts or >10 s calls. No new proposal. |
| **Pod/node-budget-aware xdist workers** | Raising 3→6 at fixed effective CPU availability gives an optimistic **1.8 min wall / 5.2 runner-min** execution saving if only the measured post-banner phase halves; collection duplicates may erase or reverse it. Zero guaranteed gain. | Medium, existing CPU-budget carrier; roughly days plus observation. | Same gate, but throughput and contention risks. Current node/factory budget governs. No free cap increase assumed. |
| **Eight external shards, still three workers each** | Ideal file-linear model halves pytest work per job: up to **4.5 min wall saved**, before extra queueing. At least **~2.8 extra runner-min setup** for four extra jobs at today's ~42 s/job non-pytest overhead; workload duplication/queueing can cost more. | Small script/matrix change; medium capacity validation. | No gate weakening if complete union checked. Doubles peak test processes 12→24. Not a same-capacity comparison. |
| **Twelve external shards with one worker each** | Same twelve test processes; possible collection savings as above, but **eight extra setups ~5.6 runner-min** offset the benefit. Prefer in-pod partitions first. | Small/medium. | Same suite possible; increased pod/slot pressure. No new proposal identified. |
| **Work stealing / front-load long tests** | Estimate **0–0.5 min wall**, roughly **0–1 runner-min** from reduced idle tails; not measured. Cannot fix the pre-banner phase or move work between current pods. | Small, under a day for experiment. | Same tests; use logged worker timelines to verify. [xdist worksteal](https://pytest-xdist.readthedocs.io/en/stable/distribution.html) supports uneven runtimes, but fixture scope/order isolation still matters. |
| **Persist valid rewritten bytecode; reduce eager imports and plugin loading** | Conditional: remove 20–40% of pre-banner work → **1.1–2.1 min on shard 4 and 4.2–8.3 runner-min**. Historical cold/warm data support the mechanism, not these current percentages. | Medium, 1–3 days for profiling and a trustworthy cache. | Cache only compiled artifacts, not test outcomes; content/Python/pytest/rewrite/config keyed, safe trust boundary, no stale mtime+size substitution. Preserve required plugins. No new coverage proposal; shared-cache deployment rules may apply. |
| **Disable assertion rewriting (`--assert=plain`)** | Unmeasured; if rewriting is 10–30% of pre-banner wall, **0.5–1.6 min wall / 2.1–6.3 runner-min**. Zero if imports/contention dominate. | Tiny switch, substantial diagnostic evaluation. | Ordinary asserts still run, but livespec NFR requires pytest default assertion introspection. Needs a propose-change for this use; not a first recommendation. |
| **Stop repeat repository scans and repeated fixture construction inside tests** | Known scan calls contribute at least **89.55 worker-seconds** (41.38 + 33.75 + 14.42); at three workers, removing all would be at most **0.50 runner-min**, usually **0–0.25 min wall**. A 50–80% reduction of the Honeycomb file's reported 106.75 s adds approximately **0.30–0.47 runner-min**, at most 0.30–0.47 min wall if critical. Broader fixture savings unmeasured. | Medium per cluster, 1–3 days. | Keep real-tree conformance once, fixture-based behavior tests, idempotence and negative controls. Share immutable input/AST snapshots only within a proven unchanged tree. No new proposal when assertions are preserved. |
| **Replace redundant subprocess cases with in-process tests** | No measured global spawn count. Illustration: 1,000 avoidable starts × 0.1–0.5 s = **100–500 CPU-seconds**, about **0.6–2.8 runner-min** at three effective CPUs/job and **0.14–0.69 min wall** balanced over twelve CPUs. Measure actual starts first. | Medium/high, several days, selectively. | Preserve real executable/argv/env/exit/signal/UID tests where those are the contract. The slow Honeycomb subject is Bash, so “call Python main” is not its solution. No proposal for equivalently covered pure logic; deleting required boundary tests would need contract review. |
| **Injected clocks/events instead of accidental real waits** | Estimate **0.2–0.6 min wall / 0.3–0.9 runner-min** for selected ten-second watchdog clusters; no global savings established. Real hook-limit tests are not all safely removable waits. | Medium, 1–3 days per seam. | Strengthens determinism when the same ordering/timeout arithmetic is asserted. Existing no-real-time-waits rule generally supports it; preserve explicitly real-time subjects. |
| **Property tests or fuzz generators replace examples** | **Zero defensible immediate fleet saving.** A twenty-example family replaced by 100 generated cases can be **5× execution work** before generator/shrinker cost. Conditional 10% reduction of post-banner work would save only **~0.37 min critical / 1.03 runner-min**; reducing source/import footprint may add more. | High, days/weeks for useful models and before/after evidence. | Risk of losing specific regressions or precise oracles. Keep explicit regression/boundary examples and deterministic replay; pure-module PBT is already required. No automatic permission to delete scenario obligations. |
| **Coverage-overlap-guided pruning** | If it truly removes 10–20% of both collection and execution cost, estimate **0.9–1.8 min wall / 3.1–6.2 runner-min**; current evidence establishes no removable fraction. | Medium/high: one diagnostic attribution run, selection/review, full validation. | Identical line/branch sets do not imply identical assertions or fault detection. Use overlap to shortlist, not authorize deletion. Preserve heading/scenario obligations and exact first-party coverage. |
| **Mutation-kill-matrix-guided pruning** | Same conditional **0.9–1.8 min / 3.1–6.2 runner-min** for a measured 10–20% cost reduction, not a forecast. Matrix construction initially adds substantial offline compute. | High: finish broken/unarmed adoption, per-test attribution and cost-aware reduction; weeks fleet-wide. | Better evidence than coverage overlap, still finite-mutant evidence. Preserve killed-mutant identities, branch coverage, regressions, scenario mappings; do not merely preserve a score. On-demand plan already commissioned; not another required per-PR gate. |
| **Python 3.14 + sysmon branch tracing** | Current 3.10 toggle: **0 saving** because unavailable. Illustrative traced-phase speedups of 1.2×–2× would save **1.5–4.5 min wall / 5.2–15.6 runner-min**, if applicable across the whole pytest phase; actual effect may be much smaller. | High relative to config fixes: image/toolchain/dependency and coverage-equivalence validation. | Preserve branch data and 3.10 compatibility obligations. A newer test interpreter alone is not a forbidden syntax change; raising the supported floor requires propose-change. Replacing all floor-version evidence needs explicit compatibility-policy review. Dynamic coverage contexts and plugins can constrain sysmon use. |
| **Parallel per-file report analysis / cache immutable parse results** | Remaining analysis approximately 38 s: ideal four-way analysis saves **~28 s = 0.47 min** in both wall and runner-min, before spawn/combine overhead. Less after omitting tests. | Medium/high versus small absolute benefit. | Must preserve exclusions, arc semantics, current source identity and per-file verdict. No new proposal for exact equivalent analysis. |
| **Co-locate the aggregate verdict consumer with combine** | Save **~47 s wall** (19 s dependency queue + 28 s job) and **~0.45 runner-min** on this specimen, with about one second still needed for verdict replay. | Small/medium; preserve canonical slug and aggregate wiring. | Low; keep both required semantics and CI completeness/parity. Orchestrator already eliminated repeated analysis, so do not claim that saving again. |
| **Move the root leg again / reduce its frequency** | **0 additional PR wall or runner-minute saving**: already moved. Weekly resource savings would depend on measured scheduled-run volume, not supplied here. | No action needed for the original suggestion. | Removing it weakens UID divergence detection. Further schedule/coverage reduction needs review of the adopted both-UID policy. |
| **Use the approved config-value fast path** | On eligible changes, avoid almost the whole **12-min / 35.7-runner-min coverage chain**, minus schema validation; fleet mean saving is approximately eligible fraction × that amount. Eligibility rate unknown. | Medium, coordinated existing classification/wiring work. | No new rule needed for the exact committed-key class. No generic docs/no-Python exemption. Both PR/master classify the same diff and must fail schema violations. |
| **General affected-test selection, on both PR and master** | If selection before collection genuinely retains 10% of cost, ideal **~8 min wall / 28 runner-min saved** from pytest, with setup/verifier costs remaining. Node-ID deselection after full collection saves much less. | High: dependency closure including non-Python inputs, fallback policy, measurement. | Needs propose-change beyond the config-value exception and full-suite requirements. PR-only selection also violates parity. Never merge old arcs merely to make the 100% number green. |
| **Content-hash result reuse across identical inputs** | At a valid complete-input hit, up to **~12 min wall / 35.7 runner-min** avoided, minus receipt checks. Mean benefit is hit rate × saving; no hit rate measured. | High: trusted receipts, complete input/environment keys, invalidation and retention. | Same-run producer/consumer reuse is already accepted. General cross-run replay needs an explicit policy for evidence lifetime, full-suite obligations and live-state gates. Tree hash alone is insufficient. |
| **All tests untraced + a small traced coverage-witness set** | Speculative. If tracing doubles test CPU and witnesses cost 10% of an untraced suite, total becomes 1.2U instead of 2U: **40% CPU saving** before duplicate collection. If tracing overhead is only 10%, the same scheme is slightly slower. | High: attribution and witness selection, two execution modes, prove artifact completeness. | All assertions can still run, but full-suite-plus-coverage-in-one-pass wording needs proposal/review. No baseline tracing multiplier measured: do not implement first. |
| **Fewer simultaneous CI runs / batch compatible changes / cancel superseded heads** | Cancel one obsolete full coverage run early: up to **35.7 runner-min** freed; ten changes proven together could amortize a full gate to one tenth, but merge/tree interactions can erase that gain. Per-change wall may increase. | Medium/high operational change. | Keep a full final-tree gate and live-world checks. Existing concurrency cancellation must be inspected before claiming novelty. Changing per-commit proof or release semantics needs proposal. |
| **Move all coverage to hosted runners, buy more hardware, or lower coverage thresholds** | No new measured benefit here. Brief's hosted single-worker result is 62 min, not comparable to twelve current workers. More hardware changes capacity, not repeated-work cost; lower thresholds have no quantified speed benefit. | Medium to high / financial cost. | Not preferred: current maintainer placement ruling keeps coverage on k3s. Lowering 100% line/branch coverage needs explicit spec change and removes a known UID safeguard. |

##### Why partitioning before collection is the best unconventional experiment

Current shape: four pods × three xdist workers; each worker imports/collects approximately 366 files before it receives tests to execute. Alternative: **the same four pods each supervise three independent, disjoint file batches**, with each pytest process collecting approximately 122 files. Keep exactly twelve test processes. Combine all twelve uniquely named branch-data files and propagate every exit status.

Let C be the observed pre-banner time and let f be its file-proportional, avoidably repeated fraction. Dividing collection among three processes instead of repeating it saves approximately `C × f × (1 − 1/3)` per pod. For shard 4, C = 315 s; f = 0.5–1 gives **105–210 s**. Across pods, C sums to 1,250 s; the corresponding occupancy saving is **417–833 s = 7–14 runner-minutes**. Those are sensitivity estimates, not measured forecasts. Shared heavy imports, disk contention, badly balanced files or session-fixture replication could reduce or reverse the gain.

This design avoids implementing a fragile “serialize pytest's collected objects” scheduler: each ordinary pytest invocation gets explicit files. Preserve the full manifest and fail closed on missing batches. First evaluate this against current xdist on the same runner class and budget. If import cost is mainly shared fixed initialization, prefer fixing those imports or a valid bytecode cache instead.

##### What test reduction must preserve

A kill matrix is stronger evidence than a mutation score. It still is not a proof that a test has no purpose. A test can uniquely cover a historical production bug, protocol response, invalid-input distinction, or specification scenario which the current mutation operators never generate.

The existing plan's “every kill is shared” criterion also needs **set-wise** handling. If two tests kill exactly the same mutants, each has no unique kill when viewed separately; deleting both loses every kill. Use a cost-weighted set-cover or incremental removal algorithm over the surviving suite, then verify the **same killed-mutant set**, line/branch obligations and regression/scenario inventory. Prefer measured CPU/fixture/import cost to test-count reduction as the objective. Equivalent-mutant analysis and a fixed mutant population matter when comparing scores.

For generators, distinguish **fewer Python test definitions** from **fewer executions**. Hypothesis can reduce source duplication and collection cost while increasing execution. Keep important regression values as explicit examples; [Hypothesis documents explicit examples](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.example) as running alongside generated cases. A scheduled exploratory fuzzer should feed minimized deterministic regression cases into normal CI; it does not by itself replace them.

##### Selection and caching: the tempting shortcut needs a different evidence contract

[testmon's own documentation](https://www.testmon.org/) says its dependency tracking does not track static assets or external services, and that collection under coverage has special behavior. This repository tests workflow bodies, shell scripts, configuration, spec files, git state and other non-Python inputs. Selecting on imported Python modules alone is particularly unsafe here.

A credible reuse key would include first-party code, tests/conftest/fixtures, scripts and workflow/config inputs, lockfiles and tooling, coverage/exclusion configuration, Python/runtime image, UID/environment variant and the test/file manifest. Live ledger/forge/world-reading checks must still run. Store the successful test verdict and branch-data provenance together; reject partial artifacts and mismatched trees. Keep isolated trust domains for PR-provided cache content. Readonly input manifests or content-addressed compiled AST/bytecode caches are a much lower-risk first step than caching pass/fail judgments.

Do not claim parity permits a subset automatically. For a generic affected-test or cached-evidence gate, first revise the full-suite/evidence contract, then apply it identically on PR and master. The approved config-value class is the immediate exception already available.

#### 4. Ranked recommendation and the measurements that decide it

**First — remove work whose redundancy is already proven.** For fleet impact, finish the dev-tooling receipt transport through its existing carrier; the measured duplicate is 25 minutes. For the orchestrator, implement the ratified test-module omit rule through its existing carrier, and consider co-locating the one-second aggregate verdict with combine. Keep 100% first-party branch coverage and all test execution. These have the best evidence-to-effort ratio and need no new reduction in the gate's meaning.

Before accepting them: compare the same source-file inventory and first-party missing-line/branch sets; prove an intentionally uncovered first-party branch still fails, including from a temporary-directory subprocess; prove missing/mismatched receipts do not get reused; verify collected cases and skips remain unchanged. The omit rule must not accidentally match product code because an absolute path happens to contain `tests`.

**Second — make collection partitioned work instead of repeated work, at fixed capacity.** This is the highest-upside unconventional experiment supported by today's phase distribution. Compare four pods × three xdist workers against four pods × three disjoint ordinary pytest processes. In parallel with that experiment, collect complete file/phase durations and use weighted partitions. Do not simply increase workers or pods and attribute more resources to better efficiency.

Before committing: obtain per-worker import/collection timestamps, CPU usage, cgroup throttling and filesystem wait; sample `-X importtime` and assertion-rewrite timing on representative large modules, without a new shared-host full-suite campaign. Then use one bounded controlled CI comparison with the same tree/image/node class. Verify the collected-node-ID union, duplicates, skipped counts, all partition exits, source/arc inventory and unchanged failure behavior. A missed partition must fail even if the remaining data happens to report 100%.

**Third — reduce the named expensive harness work and allocate CPU from the node budget.** Start with repeated whole-tree scans and the Honeycomb provisioner test family; distinguish immutable input reuse from mutable fixture sharing. Preserve at least the integration cases whose subject is a real process/CLI/timeout boundary. Use the existing node-budget work to choose worker counts rather than lifting the cap by intuition.

The fresh comments on **“Derive per-node CI workers from a CPU budget” (`livespec-dev-tooling-6e5pyj`)**, 2026-11-05 06:59 UTC, measured busy CI jobs at W=3 using mean 2.70 cores on poweredge (n=205) and 2.69 on gmktec (n=79), with occasional larger bursts from steps that ignore W. Node idle minima were 4.2% and 1.3%. This is evidence against treating spare cores as a stable entitlement. The source is an existing measurement, not a fresh host probe by this investigation.

For every accepted optimization report both (a) coverage-chain median/p90 wall time and (b) runner-minutes and actual CPU-seconds, with job queue and node class separated. First use a controlled same-tree comparison, then at least twenty ordinary successful runs for the operational result; retain failures/cancellations separately rather than silently dropping them. The older [runner-minute baseline](/data/projects/livespec-dev-tooling/plan/ci-runtime-and-cost/research/004-pr-runner-minutes-baseline-2026-11-05.md) is 32.98 median runner-minutes across all PR jobs. Today's one-run 44.00 is not evidence that the plan's median target is met.

Resume mutation-guided reduction after establishing a trustworthy small pilot, not a giant fleet-wide matrix first. Keep its expensive analysis on demand as commissioned. Do not promise a percentage reduction until the pilot preserves all prior kills and regression obligations and shows an actual runtime improvement.

#### 5. What happened to the unfinished fuzzing work

**The strongest match is mutation-guided test reduction, not an unfinished general Python fuzzer.** I found the maintainer's original instruction and its recorded destination:

- Claude session **`gitops-fleet-capacity-monitoring`**, ID **`229eb13f-213e-4fe7-aa19-aad6b9475029`**, transcript [line 9820](/home/ubuntu/.claude/projects/-data-projects-livespec-dev-tooling/229eb13f-213e-4fe7-aa19-aad6b9475029.jsonl:9820), **2026-10-27 23:00:18 UTC**: the maintainer objected to 10,000 tests and asked for a fleet plan using existing mutation testing and Rule 26, with an on-demand recipe and reports for every repository.
- The same session's [line 10241](/home/ubuntu/.claude/projects/-data-projects-livespec-dev-tooling/229eb13f-213e-4fe7-aa19-aad6b9475029.jsonl:10241), **23:25:43 UTC**, explicitly reports that **`fleet-mutation-testing-rule-26` was filed, epic `livespec-dev-tooling-oi2two`, PR #2923 merged**. That is the track's identity, rather than a guessed name based on “fuzz.”
- The durable [plan research](/data/projects/livespec-dev-tooling/plan/fleet-mutation-testing-rule-26/research/001-rule-26-survey-and-baseline-2026-10-28.md) requires per-test/per-mutant kill matrices, an on-demand `just mutation-kill-matrix`, removal of redundant tests while preserving prior kills, and exact before/after counts and runtimes across twelve repos. The recipe must remain outside required per-PR/commit gates.
- Fresh ledger read: **“Fleet-wide rule-26 mutation testing and test-suite shrink” (`livespec-dev-tooling-oi2two`) is `backlog`, last updated 2026-10-27 23:12:13 UTC, with zero comments**. Its on-disk research still contains a proposed carrier map. The inspected dev-tooling justfile has no `mutation-kill-matrix` recipe. This supports unfinished implementation; it is not a claim that every possible external artifact was exhaustively searched.
- The current runtime request is in **`ci-runtime-and-cost`**, session **`721810d4-1da0-402d-97f2-44f7e377aafe`**; its transcript records the request in queue-operation lines 1587/1598 and an attachment at 1600. `/home/ubuntu/.claude/history.jsonl:30676` preserves the same request. It names “fuzzing” and an unnamed track, but does not explicitly say it means the Rule-26 plan. **High-confidence match, not certainty about the maintainer's intended referent.**

Three related strands explain the confusion:

| Strand | Current evidence | Meaning for the runtime decision |
|---|---|---|
| **Functional Python mutation testing**, `livespec-mutreal` and **“Fix mutmut nested-layout mapping and capture a real baseline” (`livespec-mutreal.1`)** | Both backlog in fresh livespec ledger reads. [mutation-testing-keystone handoff](/data/projects/livespec-dev-tooling/plan/mutation-testing-keystone/handoff.md) points cross-tenant to them. Livespec and dev-tooling still have committed 0/0 baseline files; livespec's pure trees remain unarmed. | Older foundational work was not finished. It needs usable nonzero mutants before a kill matrix can support pruning. |
| **Orchestrator property testing of pure modules**, **“Carve and declare the pure subtree so the PBT gate scans it” (`bd-ib-6qb2mc`)** | Fresh ledger status `blocked`; original scope reserves the pure-layer architectural choice for the maintainer. Current `pure_trees = { unarmed_until = "bd-ib-6qb2mc" }`. Eleven tracked test files contain `@given`, so some properties already exist. | Property testing is neither absent nor systematically enforced. Arming the gate is quality work; it does not itself make the suite smaller/faster. |
| **Rust console fuzzing and mutation adequacy** | [Archived test-adequacy plan](/data/projects/livespec-console-beads-fabro/plan/archive/test-adequacy-gates/research/001-charter-and-sequencing.md); fresh ledger shows **“CI merge-gate fuzz job” (`livespec-console-beads-fabro-txtzn5.9`)**, **“Nightly fuzz + mutation soak” (`livespec-console-beads-fabro-topr34.2`)**, and **“Nightly soak driver” (`livespec-console-beads-fabro-547r5w`)** closed. Cache research records an actual fuzz job falling 316→224 s, with a 180-second fuzz budget. | This is largely shipped historical work, not a direct method for removing Python coverage tests. I did not execute a fresh console fuzz run. |

**A correction to old research is necessary:** the keystone handoff and the October survey describe an armed zero-mutant result passing. The current `livespec_dev_tooling/checks/check_mutation.py` explicitly rejects an armed run enumerating zero mutants and refuses a zero-mutant baseline write. That failure-handling defect has been repaired. The current unfinished state is configuration/arming, real baselines, per-test kill attribution and validated pruning—not necessarily that old zero-count-pass bug. Do not reopen it from the stale handoff alone.

**Search scope and limits:** searched `plan/` including `plan/archive/` under all `/data/projects/livespec*` roots for fuzzing, property-based testing, Hypothesis testing, Atheris, reduction and kill matrices; read the four requested dev-tooling plans. Queried all eleven available livespec-family `.beads/config.yaml` tenants using the public guard and credential wrapper with `bd list --status all --limit 0 --json`, then directly read relevant issues and comments. Their returned populations were livespec 934, console 470, dev-tooling 1,193, driver-claude 90, driver-codex 64, driver-pi 35, orchestrator-beads-fabro 2,024, git-jsonl 49, overseer 1,327, runtime 114 and tdd-proof 6. These are query-time populations, not fleet invariants.

For sessions, enumerated 9,046 Claude JSONL files and began a recent-modification scan (8,419 files since October 20). The broad content scan was too noisy and was stopped; a second direct dev-tooling transcript scan was also stopped after narrowing to the original source. Used the small complete Claude input-history file to locate the original instruction, then read its exact transcript and coordinator reply. Searched Codex active/archive JSONL paths with an 80 MB per-file cap and inspected selected matches; that search was bounded and not an exhaustive exclusion of an independently named fuzzing track. Current-task prompts and copied research are not independent corroboration. No session was contacted.

#### 6. Evidence still needed, without inventing measurements

The largest remaining unknowns are: the current import-versus-rewrite-versus-contention split; full uncensored per-file phase times; per-worker idle timelines; actual subprocess counts and cost; traced/untraced CPU ratio; same-capacity disjoint-collection behavior; cache hit rate under complete input keys; and the fraction of changes eligible for the already-approved config-value path.

Those unknowns are why **cheap conformance and proven duplicate-work removal rank first**, **partitioned collection ranks as the first experiment**, and **general selection/caching or mutation-led pruning do not rank as immediate replacements for today's merge gate**. The recommendation retains the intended evidence and first removes the cost of obtaining it repeatedly.
