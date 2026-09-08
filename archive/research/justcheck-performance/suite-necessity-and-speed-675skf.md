# dev-tooling suite audit — necessity, evidence, and faster full-coverage execution

Work-item: **livespec-dev-tooling-675skf** (child of epic
`livespec-dev-tooling-7us`, "Agent-loop + enforcement-suite performance").
Measured 2026-09-08. This note is the audit artifact acceptance criterion 1
requires. The machine-readable datasets it summarises sit beside it:

- **`675skf-classification.json`** — the rule, the evidence sources, the tally,
  and the per-FILE rollup for all 272 test files.
- **`675skf-classification.jsonl`** — one record per COLLECTED TEST, 3,421
  lines, each carrying that test's cost, cost band, coverage arcs, solo arcs,
  identical-footprint sibling count, real process spawns by `argv[0]` class,
  spawn seconds, classification, and the evidence sentence behind it. This is
  the artifact acceptance criterion 2 asks for.

It EXTENDS, and in three places CORRECTS, the June baseline in
`baseline-and-research.md` (work-item `livespec-dev-tooling-7us.1`) and the CI
telemetry in `ci-build-speed-telemetry-7us10.md` (`7us.10`). Read all three as
one record: 7us.1 measured the AGGREGATE and proposed six items, five of which
have since shipped; this note measures the SUITE itself, which is what is left.

## Bottom line

1. **The suite is not padded.** Of 3,245 test functions, 3,207 carry a direct
   `assert` or `pytest.raises`; 34 of the remaining 38 assert through a
   same-file helper that does; the last 4 assert by NOT raising, which is
   their stated subject (`post_span` swallows a connection error;
   `assert_coverage` passes on a complete fixture set). Zero tests are
   assertion-free. No test exists only to manufacture coverage that this
   audit could find.
2. **The suite is not evenly expensive — it is 77% one mechanism.** On the
   complete per-test census (all 3,421 nodes, 267.4 CPU-seconds), the 47 test
   files on the `subprocess_spawn_allowlist` hold **205.9s (77%)** on **890
   tests (26% of the suite)**. `tests/livespec_dev_tooling/checks/` alone is
   191.7s (72%). What those 47 files share is not a subject area but a
   MECHANISM — the process spawn.
3. **Two-thirds of the suite is already free.** **2,316 tests (67.7%) each cost
   under 5ms** and together account for **0.00 CPU-seconds** at the census's
   resolution; 733 tests (21%) carry 95.6% of the runtime. There is no "too
   many tests" problem here, and no recommendation below proposes deleting any
   test to gain speed (§3.6).
4. **Fixture lifetime is a dead end here.** Across the whole suite, pytest
   `setup` is **1.19s** and `teardown` **0.16s** against **266.0s** of `call`.
   Session/module-scoping fixtures cannot pay: there is nothing in setup to
   amortise. The cost is inside test bodies, and it is process spawns.
5. **`-n auto` is actively harmful in a Fabro sandbox, and the reason is not
   host load.** This sandbox's cgroup grants **4 CPUs** (`cpu.max` =
   `400000 100000`) while `nproc`, `os.cpu_count()` and `sched_getaffinity`
   all report **16**. Every worker-count heuristic in the repo — the justfile's
   `nproc / 4` and xdist's `-n auto` alike — is blind to the quota that
   actually binds. Measured back-to-back on a quiet sandbox: doubling workers
   past the quota multiplies THROTTLED time **28×** and burns 7% more CPU for
   identical work. Raising workers above the quota never made the suite faster
   in any measurement here — it ranged from neutral to 1.46× worse (§3.4).
6. **Two tests spend 12.02s in real `time.sleep` — 4.5% of all suite CPU.**
   `preflight_credential` takes an injected `sleep` seam that `main()` does not
   thread through, so each test exercising the unusable-credential path burns
   the full 2s + 4s backoff. `test_fleet_conformance_admin.py` is the starkest
   case in the suite: the file costs 6.01s and its other ten tests cost 0.00s
   between them. `test_fleet_conformance.py` ALREADY defines the
   `_no_sleep_preflight` helper that fixes this and uses it for a neighbouring
   test.
7. **100% line+branch coverage is real but not sufficient.** A bounded mutation
   experiment against three modules that sit at 100% (§4.3) kills most but not
   all mutants; the survivors name the specific assertions the coverage number
   conceals. The repo's own mutation lane is inert here
   (`.mutmut-baseline.json` is the `0/0` placeholder and `check_mutation`
   treats `total == 0` as a pass) — that defect is already owned cross-tenant
   by `livespec-mutreal.1`, so this note contributes evidence to it rather
   than re-filing it.

## 1. Measurement context — read before trusting any number

### 1.1 Baseline

| item | value |
|---|---|
| repo | `livespec-dev-tooling` |
| baseline commit | `555fee008366933f85badc05e143c56055dfec56` (2026-09-08 07:54:31 +0000, "chore(deps): bump livespec-dev-tooling pin to v1.61.0") |
| tree state | clean at baseline; all measurements taken before any change in this work-item's branch |
| collected tests | **3,421** (`pytest --collect-only -q`, 11.7s) |
| test files | 279 `.py` under `tests/`, 86,445 lines |
| product files | 52,929 lines under `livespec_dev_tooling/` (excluding `_vendor/`) |
| check targets in `just check` | 73 (`check-targets.txt`) |
| Python | 3.10.16 (`.python-version`; `requires-python = ">=3.10.16"`) |
| pytest / xdist / pytest-cov / coverage | 8.3.4 / 3.8.0 / 6.0.0 / 7.14.0 |

**The work-item's title says 2,569 tests. The suite is 3,421 today** — it grew
33% between the item's filing (2026-08-03) and this measurement, and 4.6× since
the 744 tests of the June 7us.1 baseline. Any number in this note is a
2026-09-08 number.

### 1.2 Host, and the quota that actually binds

| item | value |
|---|---|
| CPU | AMD Ryzen 7 4700G, `nproc` = 16 |
| RAM | 30 GiB total, ~24 GiB available |
| OS / kernel | Ubuntu 24.04.4 LTS, Linux 7.0.0-29-generic |
| **cgroup `cpu.max`** | **`400000 100000` → a hard 4-CPU quota** |
| `os.cpu_count()` / `len(os.sched_getaffinity(0))` | **16 / 16 — both blind to the quota** |
| host load average during the session | 4.3 – 21.8, recorded per run in the tables below |
| execution context | Fabro dispatch sandbox on a shared host; other sandboxes were active throughout |

Two consequences, and they are the most load-bearing facts in this note:

- **`/proc/loadavg` is host-wide, not sandbox-scoped.** The load figures beside
  every row below include work belonging to other sandboxes. They are context,
  not a controlled variable. The June baseline recorded load the same way and
  drew the same caveat; the cgroup quota is the part it did not have.
- **`cpu.stat` IS sandbox-scoped, and it is the honest discriminator.** Phase-2
  rows carry `throttled_usec`, which separates "this setting oversubscribed the
  quota" from "the host was busy". Phase-1 rows predate that instrumentation
  and are reported as an independent replicate, not as the primary evidence.

Repeatability under these conditions is poor and is stated rather than hidden:
two identical `pytest -n 4` runs eleven minutes apart measured **60.67s and
87.10s** — a 43% swing on an unchanged tree. Treat any single figure as ±30%
and any conclusion resting on a single pair of runs as unproven. The
conclusions below rest on monotone trends across five or more settings, not on
individual deltas.

### 1.3 Reproduction

Every number in this note comes from the commands below. The harness scripts
are deliberately NOT checked in — they are measurement scratch, not product
code — so the invocations are reproduced here in full and the two datasets they
produced ARE checked in beside this note.

```bash
# 0. Aggregate-faithful environment: one up-front sync, then UV_NO_SYNC=1, and
#    invoke through `uv run` exactly as scripts/just/check.sh does.
uv sync --all-groups
export UV_NO_SYNC=1

# 1. Inventory.
uv run pytest --collect-only -q > collect.txt

# 2. Wall-clock, per worker count, with and without coverage. Wrap each run
#    with date +%s.%N and record /proc/loadavg plus the cgroup deltas of
#    usage_usec and throttled_usec from /sys/fs/cgroup/cpu.stat.
uv run pytest -n <N> -q                                          # no coverage
uv run pytest -n <N> --cov --cov-branch \
    --cov-config=pyproject.toml --cov-report= -q                 # gate shape

# 3. COMPLETE per-test cost census. --durations-min=0 is load-bearing: the
#    default 0.005s floor hides 69% of this suite.
uv run pytest -n 4 -q --durations=0 --durations-min=0

# 4. Per-test coverage footprint (the necessity evidence). An EXPLICIT
#    COVERAGE_FILE under tmp/ so this can never collide with the gate's own
#    repo-root .coverage. Costs ~3.5x a plain coverage run.
COVERAGE_FILE=$PWD/ctx.coverage uv run pytest -n 4 --cov --cov-branch \
    --cov-config=pyproject.toml --cov-context=test --cov-report= -q

# 5. Real process spawns per test, classified and TIMED by argv[0]: a
#    subprocess.Popen wrapper installed as a pytest plugin. Each xdist worker
#    writes its own shard, merged by the caller.
PYTHONPATH=$PWD/tmp/audit uv run pytest -n 4 -q -p spawn_census_plugin

# 6. Worker-cap experiment (§3.4). Wall-clock alone cannot separate
#    oversubscription from host load; the cgroup delta can. Verify the sandbox
#    is quiet FIRST — `ps aux | grep '[p]ytest'` MUST read 0 (see the traps).
for n in 4 8; do
    grep -E 'usage_usec|throttled_usec|nr_throttled' /sys/fs/cgroup/cpu.stat
    uv run pytest -n "$n" --cov --cov-branch \
        --cov-config=pyproject.toml --cov-report= -q
    grep -E 'usage_usec|throttled_usec|nr_throttled' /sys/fs/cgroup/cpu.stat
done

# 7. Bounded mutation experiment (§4.3): one AST edit at a time against a
#    module at 100% line+branch, replayed against its PAIRED test file only,
#    module restored in a finally block.
uv run python tmp/audit/mutate.py <module.py> <paired_test.py> 20
```

Four traps this harness hit, recorded so the next run does not:

- **Invoke through `uv run`, not `.venv/bin/python -m pytest`.** Four
  `test_no_except_outside_io` tests shell out to `ruff` and resolve it from
  `PATH`; `uv run` puts `.venv/bin` on `PATH` and a bare venv-python invocation
  does not. Under the bare form those four FAIL with a diagnostic
  (`ruff-not-run`) that reads like a product defect and is not one. That
  environment coupling is itself a finding — see F7 in §5.
- **`--durations=0` alone is not "all durations".** pytest still applies
  `--durations-min` (default 0.005s). The first census reported 1,057 nodes
  and looked like a complete inventory of a 3,421-test suite; it was a
  31% sample. Worse than being partial, it is BIASED: it drops precisely the
  cheap tests, so any per-test average taken over "the tests it lists" divides
  a whole file's cost by a fraction of its tests. That inflated
  `test_fleet_conformance.py` from a true 169ms/test to an apparent 42ms/test
  and nearly exempted a file from §5's conversion list (§3.3).
- **Check that no PREVIOUS benchmark is still running before starting one, and
  do it by inspecting processes rather than by assuming.** The single worst
  measurement error in this audit: a benchmark script launched by an earlier
  session survived that session's end and kept running a full coverage suite
  inside the SAME 4-CPU quota for over half an hour, while a second benchmark
  chain measured beside it. Every wall-time taken in that window was measuring
  TWO suites sharing four CPUs, not one — which is what produced this note's
  one nonsensical row, a `-n 2` coverage run at **594.74s** against a `-n 4`
  run at 118.55s, and the session's only sub-100% coverage report (99.94%).
  Neither is a fact about worker counts; both are the artifact. Nothing errored
  and nothing looked wrong from inside either run. `ps aux | grep '[p]ytest'`
  must read **0** before a timing row is started, and the count belongs in the
  results file beside the row — this note's final sweep records it. Timing rows
  are the casualty; DATASETS (coverage contexts, spawn counts, mutation
  verdicts) are unaffected by contention, so those survived the contamination
  and are reported normally.
- **A pytest node id can contain SPACES, and the obvious duration-log regex
  silently drops those rows.** Parametrized ids like
  `test_matched_gate_recognizes_gate_commands[just check-just check]` embed the
  parameter verbatim. A line pattern ending `\s+(\S+)$` matches the line but
  captures a truncated id, so the row is misfiled rather than rejected — the
  first pass of this analysis lost **83 of 3,421 nodes (2.4%)** and reported a
  clean-looking total that was 6.8s light. Anchor the id group as `(tests/.+)$`.
  The tell is a `collected` count that exceeds the `timed` count when
  `--durations-min=0` was passed, which should be impossible; assert those two
  are equal before trusting any total.

### 1.4 What is NOT measured here

- Idle-host numbers. Nothing in this session ran on an idle host, and the
  sandbox's 4-CPU quota means an "idle host" would not change the quota anyway.
  This is the standing caveat on `7us.7` and §6 rules on it explicitly.
- GitHub-hosted CI wall-times (`7us.10` covers those; nothing here supersedes
  them).
- The self-hosted k3s runner pods' effective CPU bound. Their ARC values files
  declare no `cpu` limit — admission is governed by the `ci-runner.io/churn-slot`
  extended resource — so `nproc / 4` on that lane resolves against the NODE's
  core count. Whether that is right is a question for the churn-slot capacity
  model in `.ai/ci-node-capacity-reads.md`, not something this audit measured.
- Network-cold `uv sync`.

## 2. What has already shipped since the June baseline

`baseline-and-research.md` proposed six items. Verified in tree at the baseline
commit, **five of the six have shipped**, which is why this audit does not
re-propose any of them:

| 7us.1 item | status at `555fee00` | evidence |
|---|---|---|
| 1. Parallel check-aggregate dispatcher | **shipped** | `livespec_dev_tooling/parallel_check_dispatcher.py`, wired from `scripts/just/check.sh` |
| 2. Pre-push green-token short-circuit | **shipped** | `livespec_dev_tooling/green_token.py`, consumed by `scripts/just/check-pre-push.sh` |
| 3. Port the `UV_NO_SYNC` up-front-sync pattern | **n/a here** | this repo was the pattern's origin; `check.sh` syncs once then exports `UV_NO_SYNC=1` |
| 4. Scope the Red leg by staged-path class | **shipped** | `livespec_dev_tooling/red_leg_scope.py`, wired from `check-pre-commit.sh` |
| 5. Cap pytest-xdist workers for coverage runs | **partially shipped, still open as `7us.7`** | justfile `test_nprocs` = `nproc / 4` on the local lane, `auto` on `hosted`; the "verify idle-host first" caveat was never discharged |
| 6. Per-target wall-time instrumentation | **shipped** | the dispatcher emits per-target structlog timing events on stderr |

Two structural improvements landed beyond that list and change what "the
duplicated full-coverage lane" means today:

- **The full suite now runs ONCE per aggregate, not twice.** `check-coverage`
  consumes the `.coverage` that `check-per-file-coverage` produces
  (`livespec-dev-tooling-yilyxr.1`), gated on a provenance marker
  (`livespec-dev-tooling-sc0z`). CI does the same across a job boundary via an
  artifact upload/download. The duplication the work-item's brief names has
  already been removed on both lanes.
- **What remains is a strict serial chain, and it IS the critical path.**
  `_COVERAGE_CONSUMERS` in the dispatcher makes `check-coverage` a genuine
  read-after-write consumer of `check-per-file-coverage`, so the two cannot
  overlap. The aggregate's floor is therefore
  `suite-under-coverage + coverage-report-read`, with all 71 other targets
  running inside that shadow. See §3.5.

## 3. Baseline matrix

### 3.1 Suite wall-clock, phase 1

All rows: `uv run pytest` at the baseline commit, `UV_NO_SYNC=1` after one
up-front `uv sync --all-groups`, `--cov-report=` suppressed so the row measures
the suite and not the report. `rc=0` and 3,421 passed on every row. Load is the
HOST 1/5/15-minute average at the instant the row started and finished; it is
context, not a controlled variable (§1.2).

| run | workers | coverage | wall (s) | load before → after |
|---|---:|---|---:|---|
| nocov-n4-cold | 4 | no | **60.67** | 4.72 → 5.04 |
| nocov-n4-warm | 4 | no | **87.10** | 5.04 → 11.74 |
| nocov-n8 | 8 | no | 96.48 | 11.74 → 13.23 |
| nocov-n16 (`-n auto` here) | 16 | no | 105.38 | 13.23 → 20.30 |
| cov-n4-cold | 4 | yes | **118.55** | 20.30 → 6.92 |
| cov-n4-warm | 4 | yes | **133.60** | 6.92 → 7.82 |
| cov-n8 | 8 | yes | 173.37 | 7.82 → 9.49 |
| cov-n12 | 12 | yes | 209.33 | 14.45 → 7.27 |
| cov-n16 (`-n auto` here) | 16 | yes | 212.01 | 9.49 → 14.45 |
| nocov-serial (`-p no:xdist`) | 1 | no | **254.65** | 7.27 → 11.74 |

**Parallel efficiency.** Against the 254.65s single-process run, `-n 4` cold is
a **4.20× speedup on a 4-CPU quota** — apparently super-linear, and the reason
matters (§3.4 measures the same `-n 4` shape consuming only 75% of the quota,
so read this paragraph's "saturates" claim as corrected there): 14.1s of the serial run is `time.sleep` (§3.3) and much of the rest is
a worker blocked in `fork`/`exec`/`read` on a child process, and neither
consumes quota. Net of the sleeps (254.65 − 14.1 = 240.6s of quota-consuming
work) the cold figure is **3.97×**, i.e. ~99% of the quota; the warm figure
(87.10s) is 2.76×, i.e. 69%. **The suite already saturates its quota at 4
workers.** That is the whole reason more workers cannot help.

Three readings:

- **Cold vs warm is noise, not a cache effect.** The cold row beat the warm row
  in both pairs. `.pytest_cache` and `.ruff_cache` move nothing measurable here,
  exactly as 7us.1 found. The 27s (nocov) and 15s (cov) gaps are host variance.
- **Coverage instrumentation costs ~1.95×**, not the ~2.8× 7us.1 measured
  (118.55 / 60.67 = 1.95; 133.60 / 87.10 = 1.53 on the noisier pair). The
  suite has changed shape since June — it is now dominated by subprocess-heavy
  tests whose child-process cost coverage inflates differently from in-process
  bytecode tracing — so this is a re-measurement, not a contradiction.
- **Adding workers never gains time**, under coverage and without it. This
  sweep shows a monotone LOSS; the controlled pair in §3.4 shows the same
  settings tying on wall-clock at a higher host load while paying 28× the
  throttling. The penalty's SIZE depends on host contention; its sign does not.
  §3.4 is the mechanism, and it is not host load.

### 3.2 Where the CPU actually goes

From the COMPLETE per-test census — `pytest -n 4 --durations=0
--durations-min=0`, every one of the 3,421 collected nodes reported, wall
80.09s. (The band distribution behind these totals is §3.6; the ≥5ms sample
taken from an earlier, faster run is reconciled against it there.)

| phase | CPU-seconds | share |
|---|---:|---:|
| `call` | 266.02 | **99.5%** |
| `setup` | 1.19 | 0.4% |
| `teardown` | 0.16 | 0.1% |
| **total** | **267.37** | |

**This single table rules out an entire class of optimization.** Fixture
lifetime, session-scoped fixtures, `tmp_path_factory` sharing, autouse-fixture
pruning — every one of them targets `setup`, and `setup` is 0.6% of the cost.
The brief asks the audit to evaluate "fixture lifetime"; the measured answer is
that there is nothing there to win, and any proposal in that direction should
be refused with this number.

Concentration, on the same complete census (272 of the 279 test files contain
at least one test):

| slice | CPU-seconds | share |
|---|---:|---:|
| top 10 test files | 130.2 | 49% |
| top 25 test files | 197.1 | 74% |
| top 50 test files | 248.1 | 93% |
| `tests/livespec_dev_tooling/checks/` (1,412 tests) | 191.7 | **72%** |
| the 47 `subprocess_spawn_allowlist` files (890 tests) | 205.9 | **77%** |
| everything else (225 files, 2,531 tests) | 61.4 | 23% |

The allowlist slice is the single most useful line in this note: **47 of 279
test files hold 77% of the suite's CPU on 26% of its tests**, and what they
have in common is not a subject area — it is a mechanism, the process spawn.
That is what makes §5's conversion the lever and everything else a rounding
error.

### 3.3 Per-file and per-test long poles

Top 14 files by CPU-seconds on the complete census, with whether the file sits
on the `subprocess_spawn_allowlist`:

| CPU-s | tests | ms/test | allowlisted | file |
|---:|---:|---:|---|---|
| 41.15 | 85 | 484 | yes | `checks/test_red_green_replay.py` |
| 14.22 | 36 | 395 | yes | `fleet/test_fleet_conformance.py` |
| 13.40 | 49 | 273 | yes | `checks/test_no_except_outside_io.py` |
| 11.19 | 42 | 266 | yes | `checks/test_heading_coverage.py` |
| 10.69 | 26 | 411 | yes | `checks/test_check_coverage_incremental.py` |
| 9.10 | 27 | 337 | no | `workflow_checks/test_no_stale_revise_branches.py` |
| 8.12 | 23 | 353 | yes | `checks/test_master_ci_green.py` |
| 7.96 | 34 | 234 | yes | `checks/test_primary_checkout_commit_refuse_hook_installed.py` |
| 7.60 | 17 | 447 | yes | `checks/test_config_driven_checks.py` |
| 6.79 | 28 | 243 | yes | `checks/test_ci_matrix_completeness.py` |
| 6.37 | 17 | 375 | yes | `checks/test_commit_pairs_source_and_test.py` |
| 6.15 | 20 | 308 | no | `checks/test_aggregate_completeness.py` |
| 6.06 | 10 | 606 | no | `fleet/test_read_cause_reporting.py` |
| 6.01 | 11 | 546 | no | `fleet/test_fleet_conformance_admin.py` |

Top individual tests:

| seconds | test |
|---:|---|
| 9.01 | `checks/test_check_coverage_incremental.py::test_main_passes_against_fully_covered_real_repo_pair` |
| 6.01 | `fleet/test_fleet_conformance.py::test_main_unusable_credential_fails_before_any_row_runs` |
| 6.01 | `fleet/test_fleet_conformance_admin.py::test_admin_lane_unusable_credential_fails_before_any_row_runs` |
| 2.48 | `fleet/test_fleet_conformance.py::test_central_lane_never_spends_an_api_read_on_an_admin_row` |
| 2.07 | `checks/test_no_shadow_ledger_body_typechecks.py::test_passes_on_clean_canonical_body` |
| 1.94 | `checks/test_red_green_replay.py::test_red_green_cycles_route_correctly_in_sequence` |
| 1.70 | `checks/test_master_ci_green.py::test_real_repo_passes` |
| 1.45 | `checks/test_red_green_replay.py::test_chore_with_passing_tests_only_staged_takes_suite_green_leg` |
| 1.38 | `checks/test_red_green_replay.py::test_chore_with_failing_test_staged_alone_authors_a_red` |
| 1.35 | `checks/test_config_driven_checks.py::test_declared_absent_role_keys_are_sanctioned_opt_outs` |

`test_check_coverage_incremental.py::test_main_passes_against_fully_covered_real_repo_pair`
is the suite's single most expensive test at **9.01s**, and it is `required`
and must stay: it builds a real repo pair and spawns a real `pytest --cov`,
which IS the check's subject (§5.2). It is named here so nobody mistakes it for
a conversion candidate — it is the clearest case in the suite of a test that
legitimately costs what it costs.

**The two 6.01s tests are pure `time.sleep`, and the arithmetic proves it.**
`livespec_dev_tooling/fleet/_credential_preflight.py` retries a rejected
credential on a `_BACKOFF_SECONDS = (2.0, 4.0)` schedule bounded by
`_MAX_ATTEMPTS = 3`, and it takes the delay as an INJECTED `sleep: Sleeper`
seam precisely so tests need not wait. `main()` does not thread an override
through, so a test that drives the unusable-credential path through `main()`
sleeps 2.0 + 4.0 = **exactly the 6.0s measured, twice**.
`test_fleet_conformance.py` already defines `_no_sleep_preflight` (line 1185)
and uses it for the transient case at line 1179; the two unusable-credential
tests do not. This is **12.02s — 4.5% of all suite CPU** — bought for nothing,
and the remedy is a pattern already present in one of the two files.

`fleet/test_fleet_conformance_admin.py` is the starkest case in the suite:
**the file costs 6.01s and its other ten tests cost 0.00s between them.** One
sleeping test is 100% of that file's runtime.

Two honesty corrections against the earlier ≥5ms sample, both of which changed
a conclusion:

- `test_central_lane_never_spends_an_api_read_on_an_admin_row` measures **2.48s**
  here (2.14s in the sample). It does NOT route through `preflight_credential`,
  so it is not folded into the 12.02s claim; its cost stays unexplained and it
  is classified `investigate`.
- **`fleet/test_fleet_conformance.py` is NOT otherwise cheap, and the sample
  said it was.** Net of the 6.01s sleep and the 2.48s outlier its remaining 34
  tests cost 5.73s — **169ms each**, not the 42ms the ≥5ms sample implied. The
  sample only counted 25 of the file's 36 tests, so dividing its total by its
  visible tests understated the per-test cost by 4×. This is exactly the trap
  §3.6 exists to close, and it is why the per-file tables above were re-derived
  on the complete census rather than carried over.

### 3.4 The worker-cap experiment — what the throttle counters actually say

Phase 1's sweep (§3.1) measured wall-clock only, and wall-clock on a shared
host cannot distinguish "this setting oversubscribed my quota" from "the host
was busy". `cpu.stat` is cgroup-scoped and can. Two runs, back-to-back, on a
sandbox verified quiet (`ps aux | grep '[p]ytest'` = 0 at start), identical in
every respect but the worker count:

| workers | wall (s) | CPU used (s) | **throttled (s)** | throttle events | coverage | result |
|---:|---:|---:|---:|---:|---|---|
| **4** (= the quota) | 193.76 | 583.13 | **16.52** | 789 | 100.00% | 3421 passed |
| **8** (2× the quota) | 192.09 | 626.26 | **467.52** | 1,363 | 100.00% | 3421 passed |

**The mechanism is now measured, and it is oversubscription.** Doubling workers
past the quota multiplies throttled time **28×** (16.5s → 467.5s) and throttle
events 1.7×, and burns **7% more CPU (583s → 626s) to do identical work** —
same 3,421 tests, same 100.00% coverage. At `-n 8` the workers are throttled
for 243% of the run's wall-clock summed across them, against 8.5% at `-n 4`.
Nothing about that is host load: `throttled_usec` counts only this cgroup being
held off after exhausting ITS quota.

**And here is the correction this experiment forces.** These two runs finished
in the SAME wall-clock — 193.76s vs 192.09s, a 0.9% difference that is noise.
Phase 1, at a much lower host load, measured `-n 8` as **1.46× SLOWER** than
`-n 4` under coverage (173.37s vs 118.55s). Both measurements are sound; they
disagree because the wall-clock PENALTY for oversubscription depends on how
contended the host already is. So the note's earlier "more workers
monotonically slower" is too strong, and is withdrawn. What survives across
both is the claim that actually matters for `7us.7`:

> **Raising the worker count above the quota never made the suite faster in any
> measurement taken here. It ranged from neutral to 1.46× worse, and it always
> cost more CPU and dramatically more throttling.**

That is a weaker headline than "1.8× slower" and a much more defensible one. It
is also sufficient: a setting that cannot win and can lose 46% is the wrong
default, whatever the host is doing.

Two further readings:

- **Even at `-n 4` the suite does not saturate its quota**, and this is a
  correction to §3.1's "~99% of the quota" reading. 583.13 CPU-seconds over
  193.76s of wall is **3.01 CPUs of a 4-CPU grant — 75%**. The missing quarter
  is the suite waiting on child processes (§4.1.2), which consumes wall-clock
  without consuming quota. That is ANOTHER reason the spawn conversion is the
  lever: it removes the very work that is stopping the quota from being used.
- **Coverage held at 100.00% at both worker counts**, which is the direct
  refutation of the worry raised by the contaminated `-n 2` row (§1.3). The
  gate's verdict does not depend on the worker count; that row was an artifact.

### 3.5 The critical path, per lane

The suite runs inside five distinct lanes, and a saving does not land in all of
them. Every recommendation in §6 states which lanes it touches, against this
map.

| lane | what runs | how many full suite runs | worker count |
|---|---|---:|---|
| **local `just check`** | 73 targets via `parallel_check_dispatcher` at ≤8 concurrent | **1** | `test_nprocs` = `nproc / 4` |
| **pre-commit, Red shape** (1 staged test file, 0 impl) | `red_leg_scope` skips the two coverage targets | **0** | — |
| **pre-commit, Green amend / any other `.py`** | full aggregate, `hook_gate=1` | **1** | `nproc / 4` |
| **pre-push** | green token matches a byte-identical tree → skip; otherwise full aggregate | **0 or 1** | `nproc / 4` |
| **CI** | `check-per-file-coverage` job runs the suite and uploads `.coverage`; `check-coverage` downloads and reads it; `check-check-coverage-incremental` runs a PATH-SCOPED second pytest | **1 full + 1 scoped** | `auto` on hosted, `nproc / 4` on self-hosted |

**The aggregate's floor is a two-node serial chain.** `_COVERAGE_CONSUMERS` in
`parallel_check_dispatcher.py` records `check-coverage → check-per-file-coverage`
as a genuine read-after-write data dependency: the consumer reads the `.coverage`
the producer wrote. The dispatcher blocks the consumer on the producer's future,
so the two cannot overlap, and all 71 other targets run inside the producer's
shadow. The aggregate therefore cannot finish faster than

> `pytest -n <test_nprocs> --cov --cov-branch` + `coverage report --fail-under=100`

which at the measured `cov-n4` figures is **~119–134s + ~6–9s ≈ 125–143s**.
Nothing in this audit changes that structure, and nothing should: the
serialization is a real data dependency, not the collision-avoidance edge it
briefly was (work-item `livespec-dev-tooling-cmn` retired those).

**So every second removed from the suite is a second off the aggregate**, on
every lane that runs the aggregate at all. That is the single most useful
consequence of the dispatcher having already shipped, and it is why this audit
targets the suite rather than the target set.

Two lane-specific notes:

- **The Red leg is already free of the suite.** `red_leg_scope` skips
  `check-coverage` and `check-per-file-coverage` at Red, and the commit-msg
  replay hook runs pytest only on the single staged test file. No suite-level
  optimization moves the Red leg; proposals aimed at it are aimed at the wrong
  lane.
- **`check-check-coverage-incremental` is the only remaining duplicate suite
  run, and it is scoped, not full.** With no `--paths` it derives the changed
  impl `.py` set from `git diff --name-only origin/master...HEAD`, resolves the
  mirror-paired tests, and runs pytest with full `--cov` over just those. On a
  one-file change that is a few seconds; on a branch touching many impl files it
  approaches a second full run. It has its own coverage namespace in the
  dispatcher, so it runs concurrently with the producer rather than extending
  the chain — it costs CPU inside the quota, not wall-clock on the critical
  path, unless the quota is already saturated (which §3.4 shows it is).

### 3.6 The complete cost distribution — and the two-thirds of the suite that is free

`pytest -n 4 --durations=0 --durations-min=0`, all 3,421 collected nodes,
per-test totals (setup + call + teardown). This is the census every other table
in §3 is derived from.

| per-test cost band | tests | share of suite | CPU-seconds | share of CPU |
|---|---:|---:|---:|---:|
| ≥ 0.5s | 63 | 1.8% | 77.14 | **28.9%** |
| 0.1 – 0.5s | 670 | 19.6% | 178.43 | **66.7%** |
| 0.02 – 0.1s | 276 | 8.1% | 10.84 | 4.1% |
| 0.005 – 0.02s | 96 | 2.8% | 0.96 | 0.4% |
| **< 0.005s** | **2,316** | **67.7%** | **0.00** | **0.0%** |

Cumulative, by test rank: the top 10 tests are 12% of suite CPU, the top 100 are
35%, the top 250 are 54%, the top 500 are 79%, and the top 1,000 are 99.7%.

**Two-thirds of this suite is already free.** 2,316 tests — 67.7% of everything
collected — each land below pytest's 5ms reporting floor and together account
for **0.00 CPU-seconds** at the census's resolution. This single row settles
several questions the brief asks:

- **There is no "too many tests" problem.** Test COUNT is not the cost driver;
  733 tests (21%) carry 95.6% of the runtime. Deleting or merging anything in
  the free two-thirds cannot make the suite measurably faster, so no
  recommendation in §7 proposes it — and any future proposal framed as "the
  suite has grown to N tests, we should prune" should be answered with this row.
- **The suite grew 4.6× since June without a proportional cost.** Growth landed
  overwhelmingly in the free band, which is what a healthy in-process unit-test
  population looks like.
- **The whole optimisation target is 733 tests**, and §3.2 already showed 890 of
  them are concentrated on 47 allowlisted files by a single shared mechanism.

**Reconciling with the ≥5ms sample.** The earlier sample (wall 60.67s) reported
202.6 CPU-seconds over 1,057 nodes; this complete census (wall 80.09s) reports
267.37 over 3,421. The gap is NOT the sub-5ms tail — that tail is 0.00s. It is
run-to-run host variance of the same order as the 43% swing §1.2 records on two
identical runs. **The shares are stable across both runs and the absolutes are
not**, which is why every conclusion in this note is stated as a share or a
ratio, and why the ±30% caveat rides on every absolute second quoted.

## 4. Necessity — how every test was classified, and on what evidence

The brief is explicit that "coverage alone is not accepted as proof of
necessity". Four independent mechanical signals were collected for every one of
the 3,421 collected tests. None of them is a line-overlap guess.

| signal | how obtained | what it can and cannot say |
|---|---|---|
| **cost** | `pytest -n 4 --durations=0 --durations-min=0` | says what a test is worth removing; says nothing about whether it may be |
| **coverage footprint** | `pytest --cov-context=test`, per-context arc sets read out of the SQLite data file | identifies arcs no OTHER test reaches (`solo_arcs`) and tests whose arc set is byte-identical to another's |
| **process spawns** | a `subprocess.Popen` wrapper installed as a pytest plugin, counting real spawns per test node and classifying `argv[0]` | separates "expensive because it exercises a process boundary" from "expensive by accident" |
| **mutation survival** | hand-rolled AST mutation of three 100%-covered modules, each replayed against only its own paired test file | the only signal that answers "would this test NOTICE a behaviour change" |

Arcs executed at IMPORT time (coverage's empty context) are excluded from the
ownership tally, so `solo_arcs` means solo **among tests**: an arc reached at
import and by exactly one test still counts as that test's.

### 4.1 The classification rule

Applied mechanically to every collected test; the result is one record per test
in `675skf-classification.jsonl`, rolled up per file in
`675skf-classification.json`.

- **required** — contributes at least one arc no other test contributes, OR is
  the only member of its identical-footprint cluster. Deleting it provably
  loses coverage or provably loses the only witness of a distinct path.
- **consolidate** — contributes zero solo arcs AND its arc set is byte-identical
  to at least one other test's. These are the only tests for which mechanical
  evidence of duplication exists. **Identical footprint is NOT proof of
  redundancy** — two tests can walk the same lines and assert different things
  about the result — so this class is a *candidate list for a human read*, and
  the recommendation attached to it (§6) is parametrization, not deletion.
- **investigate** — zero solo arcs but a footprint that is a strict subset of
  some union rather than a duplicate of any single test. Neither provably
  needed nor provably redundant. Left alone unless expensive.

**The rule deliberately cannot conclude "delete".** A test with zero solo arcs
and an identical footprint may still be the only test asserting the *value* a
shared path returns; the mutation experiment in §4.3 is what would settle that,
and running it per-test across 3,421 tests is out of this audit's budget. §6
therefore proposes no deletions at all — only consolidation, seam changes, and
a sleep fix. That is a deliberate, stated limit, not an omission.

### 4.1.1 The result — and why necessity-pruning is NOT a speed lever

Applied to all 3,421 collected tests. The full per-test dataset is
`675skf-classification.jsonl` beside this note; the rollup:

| class | tests | share | CPU-seconds | share of CPU | mean |
|---|---:|---:|---:|---:|---:|
| **required** | 3,215 | 94.0% | 258.11 | 96.5% | 80ms |
| **consolidate** | 157 | 4.6% | 9.26 | 3.5% | 59ms |
| **investigate** | 49 | 1.4% | **0.00** | **0.0%** | 0ms |

**This table ends the "is the suite padded?" question in the direction the
brief did not assume.** 94% of tests are mechanically provable as required —
each contributes at least one arc no other test reaches. And the entire
non-required population, all 206 tests of it, holds **9.26 seconds**. Of that,
**8.49s sits in a single file** (`checks/test_red_green_replay.py`, 26 tests);
the other 15 files holding `consolidate` tests contribute **0.77s between
them**, and all 49 `investigate` tests are free.

The consequence is decisive and worth stating flatly: **even a maximally
aggressive prune — deleting every test this audit could not prove necessary —
would save under 10 seconds of a 267-second suite, and 92% of that saving
would come from one file that must stay for other reasons (§5.2).** Necessity
and speed are ORTHOGONAL in this suite. The speed lever is the mechanism
(§4.1.2), not the test count.

That is also why §7 proposes no deletions. It is not caution about the
evidence — it is that the evidence says deletion would not pay.

### 4.1.2 Where the time actually is: 91% of suite CPU is inside `Popen`

The runtime spawn census (a `subprocess.Popen` wrapper installed as a pytest
plugin, counting and TIMING real spawns per test node) measured **4,272 real
process spawns** across the suite, and the time spent inside them:

| measure | value |
|---|---:|
| tests performing ≥ 1 real spawn | **1,028 (30% of the suite)** |
| CPU held by those 1,028 tests | **252.28s (94%)** |
| time measured INSIDE `Popen` calls | **242.19s (91% of suite CPU)** |

**Nine-tenths of this suite's runtime is not Python under test — it is the
suite waiting on child processes.** (The spawn census and the duration census
are two different runs of the same suite at the same commit, ~80s wall each,
so the ratio is sound to within the ±30% of §1.2; it is quoted as a share for
that reason.)

Splitting that cost by what is being spawned settles the priority of every
recommendation in §7. Using only the nodes whose spawns are EXCLUSIVELY one
class, so no attribution is guessed:

| spawn class | measured from | spawns | **ms per spawn** |
|---|---|---:|---:|
| `git` | 259 git-only tests | 1,436 | **6.2** |
| Python interpreter | 330 python-only tests | 331 | **279.4** |

**A Python interpreter start costs 45× a `git` spawn.** Applying those unit
costs to the suite's full spawn population (3,419 `git`, 643 Python, 210
other):

| class | spawns | implied CPU |
|---|---:|---:|
| Python interpreter starts | 643 | **~180s** |
| `git` invocations | 3,419 | **~21s** |

So `git` dominates the spawn COUNT (80% of all spawns) while Python dominates
the spawn COST (~74% of all suite CPU). **Optimising for the visible number —
the 3,419 git calls — would chase 21 seconds and miss 180.** This is the
single most important ordering fact in the audit: it is why N3 (convert the
Python spawns) is first and N5 (reduce the git-fixture cost) is last, and it
is measured rather than assumed.

### 4.2 Literal-only shape clusters, and why they are NOT a speed lever

An independent, purely static clustering reduced every test function to a
literal-insensitive signature (the sequence of called names, the fixture
parameter list, the assertion count) and grouped matches within each file:

| metric | value |
|---|---:|
| test functions scanned | 3,245 |
| functions whose shape matches at least one sibling in the same file | **1,303 (40%)** |
| files containing at least one such cluster | 168 |
| largest single cluster | **33**, in `checks/test_no_except_outside_io.py` |

The next largest: 21 in `test_config.py`, 19 in `checks/test_no_expected_failure_mode.py`,
10 in `checks/test_master_ci_green.py`, 9 in `checks/test_self_hosted_routing.py`,
9 in `checks/test_plugin_resolution.py`.

**Consolidating these saves approximately zero wall-clock.** A 33-case
`@pytest.mark.parametrize` runs 33 test cases exactly as 33 functions do; the
only cost it removes is per-function collection, which the whole-suite
collection measurement bounds at 11.7s for 3,421 tests (~3.4ms/test, and a
parametrized case still pays most of it). Parametrization here is a
maintainability and review-surface win, and it is reported as one. **A
recommendation that sells it as a speed win is wrong**, and this note says so
explicitly so a later reader does not re-derive it as one.

Where a cluster IS a speed lever is where its shared helper does something
expensive — and in this suite that shared helper is almost always a process
spawn. That is the py9 lever (§6), and it is reached by changing the helper
once, not by merging the tests.

### 4.3 The mutation experiment — what 100% coverage conceals

Coverage says a line RAN. It never says a test would NOTICE that line changing.
Three modules that sit at 100% line+branch were mutated one edit at a time,
each replayed against ONLY its paired test file, module restored in a `finally`
block. Operators: comparison swaps, boolean flips, and/or swaps, integer
perturbation.

| module | paired test file | sites | mutants run | killed | **survived** | kill rate |
|---|---|---:|---:|---:|---:|---:|
| `otel_cargo_phase.py` | `test_otel_cargo_phase.py` | 53 | 27 | 25 | 2 | **92.6%** |
| `red_leg_scope.py` | `test_red_leg_scope.py` | 15 | 15 | 11 | 4 | **73.3%** |
| `checks/file_lloc.py` | `checks/test_file_lloc.py` | 22 | 22 | 10 | **12** | **45.5%** |
| **aggregate** | | **90** | **64** | **46** | **18** | **71.9%** |

**Three modules at 100% line and branch coverage let 28% of behaviour-changing
edits through.** The number is not uniform, and the spread is the finding:
`otel_cargo_phase` is genuinely well-asserted at 92.6%, while `file_lloc` — at
the same 100% coverage — misses more than half.

#### The named missing assertions

`file_lloc.py` is the check that enforces THIS repository's own size-refactor
discipline: the 250-LLOC hard ceiling and the 201–250 soft band that
`CLAUDE.md` instructs every agent to decompose against. Three survivors say its
thresholds are not pinned:

| survivor | what it means |
|---|---|
| `_LLOC_SOFT_CEILING = 200` → `201` | survives |
| `_LLOC_HARD_CEILING = 250` → `251` | survives |
| `if lloc <= _LLOC_SOFT_CEILING` → `<` | survives |

The cause is visible in the test file and is a textbook boundary gap. The suite
builds fixture files at **50**, **220**, **250** and **300** LLOC. Of the four
boundary points that define the contract, it pins exactly one:

| boundary | asserted? | why the mutant lives |
|---|---|---|
| 250 passes (top of soft band) | **yes** (`n_statements=248`) | — |
| **251 hard-fails** | **no** | the hard-offender fixture is 300 LLOC, which still fails when the ceiling is 251 |
| **201 warns** (bottom of soft band) | **no** | the soft-band fixture is 220 LLOC, which still warns when the ceiling is 201 |
| **200 passes silently** | **no** | the below-soft fixture is 50 LLOC, unaffected by `<=` → `<` |

So the hard ceiling could drift from 250 to 251, or the soft ceiling from 200
to 201, and **every test in this repository would still pass** — on a check
whose exact numbers are quoted as policy to every agent that touches the repo.
Adding three fixtures at exactly 200, 201 and 251 LLOC closes all three
survivors and costs ~60ms (§7, N7).

The remaining survivors are lower value and are reported rather than dressed
up: `red_leg_scope.py`'s four are the `sys.path` vendor guard (excluded from
coverage anyway) and the `check=False` / `text=True` keywords on a
`subprocess.run`; `otel_cargo_phase.py`'s two are a `True` default and an HTTP
`200` literal.

**Scope limit, stated plainly.** This is 64 mutants against 3 of 230 product
modules — a sample designed to answer "does 100% coverage imply mutation
resistance here?" (it does not), NOT to score the suite. It is not a substitute
for a real mutation lane, and it is not offered as one; the inert-mutmut defect
is owned cross-tenant by `livespec-mutreal.1` (§6.4), and this section is
evidence contributed to that item.

## 5. Which tests must stay real, and which may move to a cheaper seam

### 5.1 The spawn census

Static AST census of every `subprocess.run` / `Popen` / `call` /
`check_output` / `check_call` under `tests/`, classified by `argv[0]`:

| `argv[0]` class | call sites |
|---|---:|
| `git` | 177 |
| `sys.executable` / `python` / `python3` (not `-m` first-party) | 151 |
| `sys.executable -m livespec_dev_tooling.*` | 9 |
| dynamic (`argv[0]` not a literal) | 8 |
| `bash` / `sh` | 12 |
| `node`, `gpg`, `gpgconf`, `mise`, `./dev-tooling/branch-protection.sh` | 5 |
| **total** | **362 sites across 89 files** |

**160 of those are Python spawns, not the "~198" the `py9` item records.** The
count has fallen 19% as earlier conversions landed; any estimate that still
quotes 198 is stale.

**The static census counts SITES; the runtime census (§4.1.2) counts
EXECUTIONS, and they answer different questions.** 362 static sites become
4,272 real spawns at runtime, because a site inside a helper fires once per
test that calls it. The runtime split is what prices the work:

| | static sites | real spawns | ms each | implied CPU |
|---|---:|---:|---:|---:|
| `git` | 177 | 3,419 | 6.2 | ~21s |
| Python interpreter | 160 | 643 | **279.4** | **~180s** |

`git` is 80% of the spawns and 10% of their cost. **Counting spawn sites — the
number `py9` is scoped by — ranks the work almost exactly backwards.**

**The conversion unit is the HELPER, not the call site.** 32 of the 160 Python
spawn sites live inside a named non-test helper — typically a single `_run` /
`_run_check` that every test in the file calls — so converting one file is one
edit, not N. The rest are inline per-test spawns and convert one at a time.
Files with a single helper covering the whole file (`test_heading_coverage.py`,
`test_ci_matrix_completeness.py`, `test_no_except_outside_io.py`,
`test_commit_pairs_source_and_test.py`, …) are therefore far better value per
edit than the raw site count suggests, and that is how §6 orders the work.

### 5.2 The dividing line, and it is NOT the process boundary

The repo's own ratified definition settles this. `SPECIFICATION/non-functional-requirements.md`
§"Scenario heading coverage" defines the integration tier as

> a consumer-style check-runner test that **imports a check from
> `livespec_dev_tooling.checks.*` and runs it against a fixture mini-project
> under `tmp_path`** with deliberately-injected violations, asserting that the
> expected diagnostic fires

— an **in-process** description. Nothing in the tier requirement asks for a
subprocess. Converting a gratuitous spawn to `monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()` therefore does not demote a test's tier, and
`tests_no_subprocess_spawn.py` already names that pattern as the default
authors are steered to. The allowlist's own docstring says it "is the HONEST
current state, not an endorsement".

The real dividing line is **what the test's contract is about**:

**Must stay a real subprocess / real repository test** — the process, the git
object store, or the shipped artifact IS the subject:

| file | why it must stay |
|---|---|
| `checks/test_red_green_replay.py` | the check's subject is a git commit-msg hook reading a staged tree and re-running pytest; 84 real `git` spawns build the histories it decides on |
| `checks/test_primary_checkout_commit_refuse_hook_installed.py` | asserts hook files installed in a real `.git`, incl. `core.bare` and worktree-common-dir probes |
| `test_green_token.py` / `test_tdd_commit.py` | the token IS a git tree hash; the commit ritual IS git |
| `checks/test_check_coverage_incremental.py` | spawns a real `pytest --cov`; that is the thing under test |
| `checks/test_check_mutation.py` | drives real `mutmut` invocation shapes |
| `checks/test_master_ci_green.py`, `checks/test_branch_protection_alignment.py` | drive a real `gh` CLI contract |
| `test_parallel_check_dispatcher.py` | spawns real `just` targets; concurrency and namespacing are the subject |
| `tests/consumer/**` | the consumer tier's whole point is exercising the SHIPPED package the way a downstream repo does |
| `worktree_pack/**`, `test_install_worktree_pack*.py` | real worktrees, real `bash` pack scripts |
| `agent_hooks/**` | hook entry points invoked as processes with real stdin |

**Gratuitous — the contract is `main() -> int` plus a structlog diagnostic on
stderr, and a subprocess buys nothing** (these are the py9 population):

`checks/test_no_except_outside_io.py`, `test_heading_coverage.py`,
`test_ci_matrix_completeness.py`, `test_config_driven_checks.py`,
`test_commit_pairs_source_and_test.py`, `test_keyword_only_args.py`,
`test_tests_mirror_pairing.py`, `test_newtype_domain_primitives.py`,
`test_no_raise_outside_io.py`, `test_public_api_result_typed.py`,
`test_no_write_direct.py`, `test_vendor_manifest.py`, `test_no_fmt_directives.py`,
`test_wrapper_shape.py`, `test_all_declared.py`, `test_private_calls.py`,
`test_per_file_coverage.py`, `test_supervisor_discipline.py`,
`test_match_keyword_only.py`, `test_pbt_coverage_pure_modules.py`,
`test_assert_never_exhaustiveness.py`, `test_rop_pipeline_shape.py`,
`test_comment_line_anchors.py`, `test_check_tools.py`,
`test_claude_md_coverage.py`, `test_no_direct_tool_invocation.py`,
`test_canonical_checks.py`, `cross_repo/test_pin_autodiscovery.py`,
`test_vendor_update.py`, `test_fabro_image_pin_lockstep.py`.

On the complete census this population is **435 tests costing 99.33s — 37% of
the whole suite**, at a uniform 240–275ms per test, which is the cost of one
Python interpreter start plus one module import, repeated once per test. The
measured unit cost of that start is **279.4ms** (§4.1.2).

### 5.2.1 The conversion is already priced — by this repo, in this repo

The `py9` conversion has ALREADY been applied to four check-test files
(`test_file_lloc.py`, `test_no_lloc_soft_warnings.py`, `test_main_guard.py`,
`test_no_todo_registry.py` each say so in their module docstring, naming
`livespec-dev-tooling-py9`). They are a natural experiment against the
unconverted files beside them, running in the same session, on the same host,
under the same quota — which is stronger evidence than any synthetic
micro-benchmark:

| file | pattern | tests | CPU-s | **ms/test** |
|---|---|---:|---:|---:|
| `checks/test_no_except_outside_io.py` | subprocess | 49 | 13.40 | **273** |
| `checks/test_heading_coverage.py` | subprocess | 42 | 11.19 | **266** |
| `checks/test_ci_matrix_completeness.py` | subprocess | 28 | 6.79 | **243** |
| | | **119** | **31.38** | **264** |
| `checks/test_file_lloc.py` | **in-process `main()`** | 18 | 0.73 | **41** |
| `checks/test_no_lloc_soft_warnings.py` | **in-process `main()`** | 18 | 0.36 | **20** |
| `checks/test_main_guard.py` | **in-process `main()`** | 6 | 0.12 | **20** |
| `checks/test_no_todo_registry.py` | **in-process `main()`** | 16 | 0.03 | **2** |
| | | **58** | **1.24** | **21** |

**A measured 12.3× per test — 264ms to 21ms — and the converted files still do
their `git init` + `git add -A`.** The residual git work is therefore worth
~21ms/test at most, not the ~240ms the spawn costs. That ordering is what makes
the in-process conversion the lever and the git-fixture work a distant second
(§7 N5).

The gratuitous population named above is **435 tests costing 99.33s — 37% of
the whole suite**. Re-priced at the converted files' measured 21ms/test it
would cost 9.3s, so the conversion removes **~90s of suite CPU, 34% of the
suite** — with the caveats in §7 N3.

**Why this is a floor rather than a ceiling.** Every figure here is measured
WITHOUT coverage. Under `--cov` a spawned child additionally self-instruments
via `COVERAGE_PROCESS_START` and writes its own data file for the parent to
combine — a cost the in-process form does not pay at all. The gate runs under
coverage, so the saving on the lane that matters is larger than 90s; this audit
did not measure how much larger, because the phase-3 run that would have priced
it (`durations-all-cov.log`) was cut short. That gap is stated rather than
estimated.

**Three of them keep a residual real `git` call after conversion** — the checks
whose universe comes from `git ls-files` need a real index, so `git init` +
`git add -A` stays even when the check itself moves in-process. That residue is
priced separately in §6 (follow-up N4).

### 5.3 Missing assertions that 100% coverage conceals

100% line+branch is a real number here — `check-per-file-coverage` and
`check-coverage` both enforce `fail_under = 100`, and every measured run in this
session reported `Total coverage: 100.00%`. Two things it does not mean:

- **It is 100% of the NON-EXCLUDED set.** `[tool.coverage.report].exclude_also`
  carries seven patterns, and a static scan of the 230 first-party product
  files finds **293 lines matching them**: 155 `sys.path.insert`, 103
  `if __name__ == "__main__":`, 24 `if TYPE_CHECKING:`, 11 `case _:`. Because
  `exclude_also` excludes the whole BLOCK a matching line opens, the excluded
  statement count is higher than 293. Each exclusion is individually justified
  in the config and none looks abusive; the number is recorded so nobody reads
  "100%" as "everything".
- **Coverage says a line RAN, never that a test would notice it changing.**
  §4.3 is the measured version of that statement, and it is not abstract here:
  three modules at 100% line+branch let **28% of behaviour-changing edits
  through**, and on `checks/file_lloc.py` the figure is 55%. The concrete hole
  §4.3 names — nothing in the suite pins the 250-LLOC hard ceiling or the
  200-LLOC soft ceiling from above, so either could drift by one undetected —
  is the clearest example in this repo of a high-value assertion that 100%
  coverage conceals. N7 closes it.

**This is the answer to the brief's "identify missing high-value behavioral
assertions that raw 100% coverage may conceal".** The audit found the hole by
mutating, not by reading, which is why it is stated as a measurement and not as
a code-review opinion.

## 6. Reconciliation with the existing items

### 6.1 `livespec-dev-tooling-7us.1` (research, closed) — five of six shipped

Verified in tree at the baseline commit; the table is in §2. Item 5
(worker cap) is the only one still open, as `7us.7`. **`baseline-and-research.md`
should be read as a historical record, not a live list** — the
`performance-improvements-01` sweep already warned of this, and this audit
confirms it against the tree.

Three of its measured claims no longer hold and are corrected here rather than
re-derived later:

| 7us.1 claim | today |
|---|---|
| coverage instrumentation is **~2.8×** | **~1.95×** (§3.1); the suite's shape changed |
| the pytest target is **60–69%** of the aggregate | still the critical path, but the aggregate now runs it ONCE and 71 targets hide inside its shadow (§3.5) |
| **`-n 8` beats `-n auto`** (=18 there) | direction confirmed, magnitude and REASON different: under a 4-CPU cgroup quota the optimum is at or below the quota. `-n auto` measured 1.8× slower than `-n 4` at low host load (§3.1); a controlled pair at high host load tied on wall while the oversubscribed setting paid 28× the throttling (§3.4). The magnitude is contention-dependent; the sign is not |

### 6.2 `livespec-dev-tooling-py9` — KEEP, re-scope and re-price

> *"Convert ~198 gratuitous test-spawned check subprocesses to in-process
> `main()` (4i5 perf win, deferred; file-by-file, coverage-fragile)"*

**Disposition: keep the item, supersede its scope statement with §5 of this
note.** It is the single largest remaining lever in the suite and it is not a
duplicate of anything. What changes:

- **The count is stale.** 160 Python spawn sites remain, not ~198 (§5.1).
- **The item is scoped by the WRONG NUMBER, and this is the substantive
  correction.** "~198 gratuitous subprocesses" counts SPAWN SITES. At runtime
  the suite performs 4,272 spawns, of which 3,419 are `git` and only 643 are
  Python — but a Python start costs **279.4ms against git's 6.2ms, 45×**
  (§4.1.2). Ranked by site count the work looks git-shaped; ranked by measured
  cost it is ~180s Python against ~21s git. The item should be re-scoped to
  the ~180s, and its success measured in suite CPU rather than in sites closed.
- **The unit is the helper, not the site.** 32 sites sit inside per-file `_run`
  helpers; those files convert in one edit each (§5.1).
- **The tier objection is answered.** The ratified integration-tier definition
  is import-and-run against a fixture project, which is the in-process pattern
  (§5.2). Conversion does not demote a scenario-mapped test.
- **The population is bounded and named** (§5.2), rather than "file-by-file"
  over an unbounded set. The must-stay list is explicit, so the item can be
  closed rather than drained indefinitely.
- **"Coverage-fragile" is the real risk and it is now nameable.** An in-process
  `main()` is measured directly instead of via a `COVERAGE_PROCESS_START`
  child, so a module's own `if __name__` and import-time guard lines change
  coverage class. That is exactly why the per-file 100% gate must run on every
  converted file before the edit lands, and why this audit ships no conversion
  itself.

### 6.3 `livespec-dev-tooling-7us.7` — SUPERSEDE the framing, keep the item

> *"Tune pytest-xdist worker cap for coverage runs (verify idle-host first)"*

**Disposition: keep the item; replace its premise.** Its blocking caveat —
"verify idle-host first" — is why it has sat undispatched through three triage
batches (`005-triage-batch-3.md` excludes it "regardless of readiness" for
exactly this reason). This audit's measurement dissolves the caveat rather than
satisfying it:

**The question is not what N suits an idle host. It is that N is derived from
the wrong number.** `nproc`, `os.cpu_count()` and `sched_getaffinity` all report
16 in this sandbox while `cpu.max` grants 4. Both worker heuristics in the repo
read the wrong one:

- `test_nprocs` = `nproc / 4` — lands on 4 here **by coincidence**. On a
  16-core host with a 16-CPU quota it under-uses by 4×; on a 64-core host with a
  4-CPU quota it over-subscribes by 4×.
- `-n auto` on the `hosted` lane — correct on a GitHub-hosted runner (small,
  dedicated, no quota), wrong anywhere a quota binds.

An idle-host measurement would not have found this, because host idleness is not
what binds. A quota-aware resolver (`cpu.max` when present, else
`sched_getaffinity`, else `os.cpu_count`) is correct on an idle host, a loaded
host, a sandbox and a CI pod alike, and it needs no per-host tuning constant.

**§3.4 also supplies the measurement discipline the item's caveat was reaching
for, and shows why wall-clock was the wrong instrument.** The controlled `-n 4`
vs `-n 8` pair TIED on wall-clock while the oversubscribed run paid 28× the
throttled time and 7% more CPU for identical work. An experiment scored on
wall-clock alone — which is what "verify idle-host first" implies — would have
concluded the two settings were equivalent and closed the item as a no-op. The
cgroup counters are what make the difference visible, and they are cheap,
sandbox-scoped, and available on every lane this fleet runs. **Re-scope the
item to require a `throttled_usec` delta beside every row**, and it becomes
decidable on a loaded host — which is the only kind this fleet has.

### 6.4 Items deliberately NOT filed

- **A mutation-testing item.** `.mutmut-baseline.json` here is the `0/0`
  placeholder and `check_mutation` treats `total == 0` as a pass, so the
  mutation lane is inert in this repo. That is a REAL defect and it is
  **already owned**, cross-tenant, by `livespec-mutreal.1` (see
  `plan/mutation-testing-keystone/handoff.md`, which also records that the
  thread is housed in this repo only as a landability workaround). §4.3
  contributes measured evidence to that item; filing anything here would
  duplicate it.
- **A `just check` target-set item.** The parallel dispatcher, the green token,
  the Red-leg scope and the per-target timing instrumentation have all shipped
  (§2). The aggregate is already bounded by the suite (§3.5), so there is no
  target-level work left worth proposing.
- **Anything about fixture scope or lifetime.** §3.2 measures setup at 0.6% of
  suite CPU. Refused with a number rather than left unmentioned.
- **Any deletion.** §4.1 states why the evidence collected here can identify
  duplicate coverage footprints but cannot license removal.

## 7. Prioritised follow-ups

Ordered by measured saving per unit of risk. Each is independently
implementable — none depends on another landing first, except where stated.
"Lanes" uses the map in §3.5.

| # | item | suite CPU | risk | do it |
|---|---|---:|---|---|
| **N1** | stub the credential backoff in 2 tests | **−12.02s** | none identified | **first** — 3 lines, largest saving per unit of effort in the audit |
| **N7** | pin the `file_lloc` ceilings (200 / 201 / 251) | +0.06s | none (additive) | **before N3** — closes a real hole in the repo's own enforcement floor |
| **N3** | convert the gratuitous Python spawns to in-process `main()` | **−~90s** | medium, named | **the lever** — one file per commit, ordered by cost |
| **N2** | derive the xdist worker count from the cgroup quota | 0 here | low | any time — claim the throttling/CPU win, not a wall-clock number |
| **N5** | reduce the residual git-fixture cost | −~21s ceiling | low | **strictly after N3** — invisible behind a 279ms spawn until then |
| **N6** | remove the `ruff`-on-`PATH` coupling | 0 | low | any time — diagnosability only |
| **N4** | consolidate literal-only shape clusters | **≈ 0** | medium | last, if at all — **not a speed item** |

**Non-duplication.** N3 absorbs `py9` (§6.2) and N2 supersedes `7us.7`'s
premise (§6.3); neither is re-filed. N1, N5, N6 and N7 are new and are not
covered by any existing item. Nothing here re-proposes any of the five 7us.1
items already shipped (§2), and no mutation-lane item is filed because
`livespec-mutreal.1` owns it (§6.4).

**The two numbers that set this ordering.** N1 + N3 are 38% of suite CPU
between them and everything else rounds to zero; and the split inside the spawn
cost — Python 279.4ms against git 6.2ms (§4.1.2) — is what puts N3 third-listed
but first in value, and N5 near the bottom despite `git` being 80% of all
spawns.

### N1 — Stub the credential backoff in the two unusable-credential tests

| field | value |
|---|---|
| **change** | in `fleet/test_fleet_conformance.py::test_main_unusable_credential_fails_before_any_row_runs` and `fleet/test_fleet_conformance_admin.py::test_admin_lane_unusable_credential_fails_before_any_row_runs`, monkeypatch the module-level `preflight_credential` to the no-sleep wrapper — the pattern the SAME file already uses at `test_fleet_conformance.py:1179` (`_no_sleep_preflight`, defined at line 1185). NOTE: `test_fleet_conformance_admin.py` has NO such helper today (verified by grep), so that file needs the three-line wrapper added, not just referenced |
| **expected saving** | **12.02s of suite CPU (4.5%)**; two 6.01s serialized blocks leave the critical path, worth up to ~6s of wall at any worker count, since a single test cannot be split across xdist workers and therefore sets a hard floor on its worker's completion |
| **confidence** | **very high** — the measurement (6.01s, 6.01s) equals the schedule arithmetic (`_BACKOFF_SECONDS = (2.0, 4.0)`, `_MAX_ATTEMPTS = 3`, so 2.0 + 4.0) exactly, and the remedy already exists in one of the two files |
| **correctness risk** | **none identified** — test-only; the asserted behaviour (`main() == 1` on a persistently-rejected credential) is untouched, and the retry SCHEDULE keeps its own direct coverage in `_credential_preflight`'s tests |
| **validation** | `uv run pytest tests/livespec_dev_tooling/fleet/ -q` passes with the same test count; `just check-per-file-coverage` still reports 100.00%; the two tests' wall drops from ~6.0s to <0.1s in a `--durations` run |
| **lanes** | local `just check`, Green amend, pre-push, CI — every lane that runs the suite. NOT the Red leg (it runs no suite) |
| **effort / ritual** | ~3 lines across 2 test files; no product `.py`, so `chore(test):` and RGR-exempt |

### N2 — Derive the xdist worker count from the cgroup quota

| field | value |
|---|---|
| **change** | replace the justfile's `test_nprocs` heuristic (`nproc / 4` on the local lane, `auto` on `hosted`) with a resolver that reads `/sys/fs/cgroup/cpu.max` (v2) or `cpu.cfs_quota_us`/`cpu.cfs_period_us` (v1) when present, falls back to `len(os.sched_getaffinity(0))`, then `os.cpu_count()`; keep an explicit `LIVESPEC_TEST_PARALLELISM` override |
| **expected saving** | **nothing where the heuristic already matches the quota** (this sandbox: `nproc / 4` = 4 = the quota, by coincidence). Where `-n auto` meets a quota, the saving is **between 0 and 1.79×** and depends on host contention — 212.0s → 118.6s at low host load (§3.1), but a controlled back-to-back pair at high host load measured `-n 8` and `-n 4` TYING on wall while `-n 8` paid 28× the throttling (§3.4). Claim the CPU and throttling reduction, which is invariant; treat the wall-clock win as upside |
| **confidence** | **high on direction** (raising workers above the quota never won in ANY measurement here, and the throttle counters name oversubscription as the mechanism); **low on magnitude** (the wall-clock penalty ranged from 0% to 46% across two controlled sweeps, on top of §1.2's ±30%) |
| **correctness risk** | **low** — worker count cannot change a verdict. It changes FLAKE exposure, in the safe direction: the `livespec-6sxd` hypothesis-deadline flake is an oversubscription artifact, and this removes oversubscription |
| **validation** | at the resolved N, `just check-per-file-coverage` reports 3,421 passed and 100.00%; wall compared against the incumbent setting over ≥3 interleaved repetitions on the same host; `throttled_usec` delta recorded per run and required not to increase |
| **lanes** | all suite-running lanes. The `hosted` CI lane changes only where a quota actually binds (a GitHub-hosted runner has none, so `auto` stays correct there) |
| **supersedes** | `livespec-dev-tooling-7us.7`'s "verify idle-host first" premise (§6.3) |

### N3 — Convert the named gratuitous-spawn population to in-process `main()`

| field | value |
|---|---|
| **change** | for each file in §5.2's gratuitous list, replace its `subprocess.run([sys.executable, <check>.py])` helper with `monkeypatch.chdir(tmp_path)` + `capsys` + `rc = main()`, and drop that file from `subprocess_spawn_allowlist` |
| **expected saving** | **~90s of suite CPU (34% of the suite)**: the population is 435 tests costing 99.33s, re-priced at the converted files' measured 21ms/test (§5.2.1). At `-n 4` with the measured ~4× speedup that is **~22s of no-coverage wall**, and MORE under coverage, where a spawned child ALSO pays `COVERAGE_PROCESS_START` instrumentation the in-process form avoids entirely — so treat 90s as a floor |
| **confidence** | **high** — the 12.3× ratio comes from four conversions ALREADY landed in this repo, measured in the same run, on the same host, under the same quota, against three unconverted neighbours; it is a natural experiment, not a synthetic benchmark |
| **correctness risk** | **medium, and specific.** (a) COVERAGE-FRAGILE: an in-process `main()` is measured directly rather than through an instrumented child, so the module's `if __name__` and import-time guard lines change measurement class and the per-file 100% gate can move. (b) A subprocess gets env and `argv` isolation for free; in-process needs `monkeypatch.setenv` / `monkeypatch.setattr(sys, "argv", ...)` — `test_ci_matrix_completeness.py` passes a custom `env=` today and must reproduce it. (c) A check that calls `sys.exit` rather than returning must be driven through `pytest.raises(SystemExit)` |
| **validation** | per file, before the commit lands: `just check-per-file-coverage` green at 100.00%; the file's collected test count unchanged; every test's outcome unchanged; `just check-tests-no-subprocess-spawn` green with the allowlist one entry shorter |
| **lanes** | all suite-running lanes |
| **sequencing** | one file per commit, ordered by `tests × ms/test`: `test_no_except_outside_io.py` (10.6s), `test_heading_coverage.py` (8.5s), `test_ci_matrix_completeness.py` (5.9s), `test_config_driven_checks.py` (5.5s), then the rest. Files with a single `_run` helper first — one edit converts the whole file |
| **absorbs** | `livespec-dev-tooling-py9` (§6.2), whose "~198 subprocesses" scope statement this replaces |

### N4 — Consolidate literal-only shape clusters (maintainability, NOT speed)

| field | value |
|---|---|
| **change** | parametrize the 1,303 test functions that match a sibling's literal-insensitive shape, largest clusters first (33 in `test_no_except_outside_io.py`, 21 in `test_config.py`, 19 in `test_no_expected_failure_mode.py`) |
| **expected saving** | **≈ 0 wall-clock, and this item must not be sold as a speed win** (§4.2). Collection is 11.7s for 3,421 tests and a parametrized case still pays most of it |
| **confidence** | high that the clusters exist; high that they save nothing |
| **correctness risk** | medium — merging distinct behaviours behind one body is how a specific assertion silently becomes a generic one |
| **validation** | collected test count unchanged (parametrization preserves it); 100% coverage held |
| **lanes** | none materially |
| **priority** | **low.** Do it for review surface if at all, and only AFTER N3, whose conversion touches the same helpers |

### N5 — Reduce the residual git-fixture cost

| field | value |
|---|---|
| **change** | the check tests whose universe comes from `git ls-files` still run `git init` + `git add -A` per test. Evaluate `git init --template=<empty dir>` (skips copying the sample hooks) or a session-scoped template `.git` copied per test |
| **expected saving** | bounded by measurement at **~10–19ms/test** across the converted files — i.e. **a few seconds of suite CPU**, an order of magnitude under N3 |
| **confidence** | medium — the bound is measured, the achievable fraction of it is not |
| **correctness risk** | low; the index contract is unchanged |
| **validation** | as N3 |
| **lanes** | all suite-running lanes |
| **priority** | **low, and strictly after N3** — before N3 the git cost is invisible behind a 180ms spawn |

### N6 — Remove the `ruff`-on-`PATH` coupling (robustness, not speed)

| field | value |
|---|---|
| **change** | four `test_no_except_outside_io` tests fail with a `ruff-not-run` diagnostic whenever the suite is invoked without `.venv/bin` on `PATH` (e.g. `.venv/bin/python -m pytest` instead of `uv run pytest`). Resolve `ruff` from the venv explicitly, or assert the probe's absence path deliberately |
| **expected saving** | none — this is a correctness/diagnosability item, filed because the audit tripped it and lost a run to it (§1.3) |
| **confidence** | high — reproduced |
| **correctness risk** | low |
| **validation** | the four tests pass under both `uv run pytest` and a bare venv-python invocation |
| **lanes** | none today (every shipped lane goes through `uv run`); it is a trap for the next person measuring |
| **priority** | low |

### N7 — Pin the `file_lloc` ceilings with exact-boundary fixtures (correctness, not speed)

| field | value |
|---|---|
| **change** | add three fixtures to `checks/test_file_lloc.py` at exactly **200** LLOC (must pass SILENTLY), **201** LLOC (must SOFT-WARN) and **251** LLOC (must HARD-FAIL). The file today builds 50 / 220 / 250 / 300, which pins only the 250 boundary (§4.3) |
| **expected saving** | **none — this ADDS ~60ms.** It is filed because the audit's mutation experiment found a real hole, and criterion 2 requires that speedups not be bought by weakening the suite |
| **confidence** | **very high** — three separate surviving mutants (`_LLOC_SOFT_CEILING` 200→201, `_LLOC_HARD_CEILING` 250→251, `<=`→`<`) each name one of these fixtures, and the fixture values in the test file explain exactly why each survives |
| **correctness risk** | none — additive test-only change |
| **validation** | re-run `tmp/audit/mutate.py` against `checks/file_lloc.py`; the three named survivors must become kills and the module's kill rate must rise from 45.5% |
| **lanes** | all suite-running lanes (negligible cost) |
| **priority** | **medium — highest of the non-speed items.** `file_lloc`'s 250 hard ceiling and 201–250 soft band are quoted as binding policy to every agent in `CLAUDE.md`; a silent one-off drift in either constant is a defect in the repo's own enforcement floor, and today nothing would catch it |
| **do it BEFORE N3** | N3 converts this file's neighbours and will re-baseline per-file coverage; landing the assertions first means the conversion is validated against a suite that actually pins the contract |

### Combined effect, honestly bounded

N1 + N3 remove **~102s of the suite's 267.4s of measured CPU (38%)** — 12.02s
of real `time.sleep` and ~90s of Python interpreter starts. Scaling by the
measured CPU-to-wall ratio of the census run (267.4s CPU → 80.1s wall at
`-n 4`, i.e. 3.34×), that is roughly:

| lane shape | today | after N1 + N3 |
|---|---:|---:|
| `pytest -n 4`, no coverage | 80.1s | **~49s** |
| `pytest -n 4 --cov --cov-branch` (the gate's shape) | 117.4s | **~73s** |

Both figures carry the ±30% host variance of §1.2 and the CPU-to-wall ratio is
assumed to hold, which it will only approximately. The coverage row is a
CONSERVATIVE estimate for a second reason: it applies the no-coverage saving
proportionally, while the conversion additionally removes each child's
`COVERAGE_PROCESS_START` self-instrumentation, a cost that exists only in the
coverage shape (§5.2.1). The audit did not measure that increment, so it is
not claimed.

Because the aggregate's floor IS this target plus the report read (§3.5), the
same seconds come off local `just check`, the Green amend, pre-push, and the CI
producer job. N2 adds nothing on a host where the heuristic already matches the
quota, and between nothing and 1.79× where it does not (§3.4). N4–N7 are not speed items at all and
are priced at zero or slightly negative by design.

## 8. What this audit did NOT do, and why

- **It changed no product or test code.** Acceptance criterion 5 bounds the
  deliverable to the audit artifact plus at most a validating prototype, and
  every recommendation above is priced from measurements of the UNCHANGED tree
  — the four already-landed `py9` conversions (§5.2.1), the backoff arithmetic
  (§3.3), the runtime spawn census (§4.1.2), and the worker sweep (§3.4). No
  prototype needed to modify the suite, so none did. The only files this
  work-item adds are this note and its two datasets.
- **Criterion 5's coverage condition is met by construction, not by assertion.**
  Every coverage-bearing run executed the unchanged behavioural suite and
  reported `3421 passed` and `Total coverage: 100.00%`: `cov-n4-cold`,
  `cov-n4-warm`, `cov-n8`, `cov-n12`, `cov-n16`, the `--cov-context=test` run,
  and the §3.4 sweep. **One run did not, and it is reported rather than
  dropped:** the contaminated `-n 2` row (§1.3) read 99.94%. That row was taken
  while a second full coverage suite was running in the same 4-CPU quota; it is
  excluded from every table as an artifact, and the clean `-n 4` / `-n 8` rows
  in §3.4 both return 100.00%. Anyone re-running this should treat a sub-100%
  coverage report as a signal to check for a concurrent run BEFORE concluding
  the gate's verdict depends on worker count — this audit found no evidence
  that it does.
- **The §4.3 mutation experiment leaves no residue.** It mutates a module,
  replays one paired test file, and restores the module in a `finally` block.
  It is a 64-mutant sample across 3 of 230 product modules, deliberately not a
  suite-wide score.
- **It did not price the conversion in the COVERAGE shape.** The phase-3 run
  that would have measured per-test cost under `--cov` (`durations-all-cov.log`)
  was lost to the contamination above and not retried. N3's saving is therefore
  quoted from no-coverage measurements and flagged as a FLOOR (§5.2.1), not
  interpolated.
- **It proposes no deletions.** §4.1 explains the limit of the evidence
  collected: identical coverage footprints prove duplicate EXECUTION, not
  duplicate ASSERTION.
- **It did not measure an idle host, and argues that is the right call**
  (§6.3): the quota, not host idleness, is what binds in a sandbox.
- **It did not re-measure CI wall-times** (`7us.10` owns those) or the
  self-hosted runner pods' effective CPU bound (§1.4).

