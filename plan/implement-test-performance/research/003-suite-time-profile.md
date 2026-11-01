# 003 — Where the whole-suite-with-coverage wall time goes

Date: 2026-11-01. Scope: `livespec-orchestrator-beads-fabro` first, with
`livespec-dev-tooling` second. Status: research note (subagent of the plan session). Candidate
work items are recorded in the plan's pending-filing list, not filed here.

Labels: **[M]** = measured (the source is named), **[I]** = inferred.

## Sources

- Orchestrator CI run `41266553603` (master `aa39327a`, 2026-11-01 02:46Z):
  - jobs `check-per-file-coverage (nonroot)` 124730447982 and `(root)` 124730448132
  - job `check-coverage (root)` 124731420742
- Dev-tooling CI run `41266390742`:
  - job `check-per-file-coverage` 124729972940
  - job `check-coverage` 124730483788
- The orchestrator's `coverage-data-nonroot` artifact. This is the combined
  `.coverage` from CI: 14.5 MB, 2,365 files, 384,144 arc rows, coverage 7.14.1,
  `has_arcs=1`. I remapped its paths onto the local checkout, which sits at the
  same SHA, and ran `coverage report` against it locally.
- Local single-process runs on the dev host, at load 57-67 on 18 CPUs:
  - `pytest --collect-only`
  - `-X importtime`
  - an in-memory assertion-rewrite/compile timing script
  - a cProfile of `coverage report` on a subset of files

  Local CPU-seconds are inflated by host contention. Use them for ratios, not
  for absolute numbers.

## Toolchain facts [M]

- Python **3.10.16** (`.python-version`; `requires-python >=3.10.16`).
- pytest 8.3.4, pytest-cov 6.0.0, xdist 3.8.0, coverage 7.14.1 with the C tracer
  (`CTracer` importable), hypothesis 6.122.3.
- `--import-mode=importlib`, so assertion rewriting applies to every test module.
- `[tool.coverage.run] branch = true`. The run is omit-only with no `source`.
  `parallel` is not set; pytest-cov handles worker combine.
- `COVERAGE_CORE` is not set anywhere. On 3.10 the `sysmon` core does not exist.
- Two subprocess-coverage hooks are installed in the venv: `a1_coverage.pth` and
  `pytest-cov.pth`. So every Python subprocess a test spawns also starts
  coverage and writes a data file.
- Worker count is `nproc/4`. CI runner pods request only `ci-runner.io/churn-slot`
  and have no CPU limit, so `nproc` reports the node's thread count. The two
  legs of the same run therefore got different worker counts: nonroot ran
  **8 workers** (a 32-thread node) and root ran **18 workers** (a 72-thread
  node).
- Measured statements break down as follows:

  | Group | Files | Statements | Branches |
  |---|---:|---:|---:|
  | `tests/**` | 1,384 | 134,705 | 3,786 |
  | `.claude-plugin/**` | 945 | 50,164 | 12,870 |
  | other (`dev-tooling/checks`, hooks, …) | 36 | 2,969 | 928 |

  **72% of measured statements are test code.**

## Phase timeline: orchestrator `check-per-file-coverage` [M]

GitHub log timestamps. pytest's start time is derived from its `in N s` line,
and its banner is flushed only together with the `N workers [12767 items]` line.

| Phase | nonroot (8 w) | root (18 w) |
|---|---:|---:|
| Job setup, checkout, mise, `uv sync` (`uv sync` itself ≈2 s) | 9 s | 13 s |
| `chmod -R` / `chown -R` workspace step (nonroot only) | **19 s** | — |
| `uv run` up to pytest session start | 1.4 s | 3.8 s |
| xdist spawn + **per-worker collection** (cold cache) | **32 s** | **76 s** |
| Tests 0→97% | 98 s | 71 s |
| 97→99% | 8 s | 21 s |
| **Last 1% (95 tests) + combine + term-missing report** | **40 s** | **52 s** |
| *pytest total (its own `in` line)* | *175 s* | *220 s* |
| **`per_file_coverage` after pytest (json_report pass)** | **26 s** | **43 s** |
| upload `.coverage` artifact | 4 s | ~4 s |
| **Downstream `check-coverage` job** (needs per-file) | queue 13 s + 59 s job, of which **`coverage report` = 34 s** | queue 63 s + 58 s |

The wall-clock CI critical path runs from the per-file job start to the end of
`check-coverage`. That was 6 min 17 s for nonroot and 6 min 51 s for root. The
pytest run itself is about half of it.

### Same breakdown for dev-tooling [M]

- 8 workers, 5,686 tests.
- Startup and collection: 13 s.
- Tests 0→97%: 36 s.
- **97→100% plus the report: 73 s.**
- pytest total: 123 s.
- `per_file_coverage`: 11 s.
- The downstream `check-coverage` job's `coverage report` alone: **21 s**.

So dev-tooling's tail contains roughly **50 s of straggler tests** (73 s − ~21 s
for the report). The tests themselves finish 97% of their work in 36 s.

## Finding 1: coverage analysis runs three times, single-threaded [M]

The same combined data is analysed three times, once by each of:

1. pytest-cov's `--cov-report=term-missing`, inside pytest's tail.
2. `livespec_dev_tooling.checks.per_file_coverage` (`Coverage.json_report`).
3. `just check-coverage` (`coverage report --fail-under=100`).

In CI, pass 3 runs in a separate job that has to queue and set up again. Each
pass re-parses and re-analyses all 2,365 files in pure Python.

Measured costs:

- **CI:** pass 3 alone took 34 s (orchestrator) and 21 s (dev-tooling). Pass 2
  took 26 s and 43 s on the two orchestrator legs. Pass 1 is inferred to be most
  of the 40 s / 52 s "last 1%" (≈34 s report plus ≈6-18 s of straggler tests and
  combine).
- **Local:** `coverage report` on the CI data took **141 CPU-s (4 min 20 s
  wall)** on the loaded dev host.

cProfile of `coverage report` over a 532-file subset showed where the time goes:

| Function | Share of 44.7 s |
|---|---:|
| `analysis_from_file_reporter` | 39.4 s |
| `PythonParser.parse_source` (tokenize + `ast.walk` + `compile`) | 23.2 s (52%) |
| arc analysis (`_analyze_ast`) | 9.0 s (20%) |
| sqlite `arcs`/`lines` reads | ~6.6 s |
| `sqlite3.connect` (3,963 calls) | 1.7 s |
| `exclude_also` regex matching | 1.4 s |

Cost is roughly proportional to the source lines measured.

## Finding 2: test code is 72% of what is measured and analysed [M]

There is no `source` setting, and `omit` does not exclude `tests/`, so the
analysis above and the tracer both run over 134,705 statements of test code.

The livespec NFR §"Code coverage thresholds" requires an omit-only blocklist
that excludes "vendored libraries, the project virtualenv, and **test
scaffolding**". Omitting `tests/*` would therefore conform to that rule, not
loosen it. It still needs confirmation against the orchestrator's own
spec/per-file policy. Today the orchestrator's per-file gate checks test files
too, which also catches dead test helpers.

## Finding 3: cold-cache collection per xdist worker [M + I]

- **[M]** CI checkouts are fresh, so no `__pycache__` exists. Each xdist worker
  independently imports and collects all 1,401 test files, with coverage already
  tracing. Workers start at the same moment, so none of them benefits from
  another's `.pyc` writes.
- **[M]** The phase took 32 s with 8 workers and **76 s with 18 workers**. More
  workers made it slower.
- **[M]** An in-memory timing of the 1,405 test and conftest files on the dev
  host:

  | Step | CPU-s |
  |---|---:|
  | parse | 22 |
  | **pytest assertion rewrite** | **56** |
  | compile of the rewritten AST | 13 |
  | plain compile, for comparison | 6 |

  A separate run measured rewrite + compile at 64.5 CPU-s. The 942 source files
  compile in 4.6 CPU-s. **Assertion rewriting is about 4-10× the cost of plain
  compilation**, and it dominates cold collection. The worst single file is
  `tests/.../commands/test_dispatcher.py` (272 KB), at 2.6 s.
- **[M]** `pytest --collect-only` took 85 CPU-s / 157 s wall on the first run
  (285 test `.pyc` rewritten), and **32 CPU-s / 50 s** on the next run with warm
  caches.

## Finding 4: tail imbalance [M for the shape, I for the cause]

The progress line spacing shows a straggler tail:

- Orchestrator: 99→100% took 40 s, and 97→99% took 8 s / 21 s.
- Dev-tooling: 97→100% took 73 s, with about 50 s of that not explained by the
  report.

Neither repo passes `--durations`, so the slowest tests are not named in any
log. These test-class counts across `tests/` are **[M]**; their cost share is
**[I]**:

| Pattern | Files |
|---|---:|
| subprocess calls | 139 |
| `sys.executable` | 38 |
| `git init` | 40 |
| `uv run` | 9 |
| `time.sleep` | 18 |
| hypothesis `@given` | 11 |
| HTTP servers | 2 |

`gh` and `fabro` are `/bin/sh` stubs, so they are cheap. Python subprocesses,
however, pay interpreter startup plus coverage start plus a data-file write,
because of the `.pth` hooks.

## Finding 5: a 4-CPU factory pod averages 2.1-2.5 cores [I]

Serial or near-serial segments in one run:

- `uv run` startup.
- The term-missing report: ~34 s on a CI core.
- `per_file_coverage`: ~26 s.
- When not reused, a third `coverage report`: ~34 s.

On a 4-CPU pod these segments take roughly 60-90 s of a ~180 s burst at one
core. The rest is collection and test execution at about 4 cores. That gives
(≈100 s × 4 + ≈80 s × 1) / 180 ≈ 2.7 cores, which matches the observed
2.1-2.5. The difference is the straggler tail.

## Ranked levers

The first two lines of each lever give the estimated saving and whether it is
measured or inferred.

1. **Run the coverage analysis once, and drop the separate CI `check-coverage` job.**
   - Saving: ~**60-90 s per local run**. In CI, ~**2-2.5 min of critical path**
     (34 s report + ~25 s setup + 13-63 s queue), plus ~25-35 s in-job.
   - Basis: [M] phase timings above.
   - How:
     - Run pytest with `--cov-report=` (or `--cov-report=json:coverage.json`)
       instead of term-missing.
     - Have `per_file_coverage` consume that JSON, or produce it once and print
       the missing lines itself.
     - Derive `fail_under=100` from the same totals in the same job.
   - Caution: the root/nonroot `fail_under=100` divergence argument
     (pyproject comment, bd-ib-sfa2) needs only that each leg gates at 100. It
     does not need a separate job.

2. **Omit `tests/*` from measurement** (conformance with the core NFR's "test
   scaffolding" exclusion).
   - Saving: each remaining analysis pass shrinks by ~**60-70%** (34 s → ~11 s;
     the local 141 CPU-s → ~45). Traced execution of test bodies also gets
     cheaper, guess 5-15% of test-run time.
   - Basis: [M] statement split; [I] proportional saving.
   - Needs a check that no orchestrator per-file policy deliberately covers
     `tests/`.

3. **Parallelise analysis inside `per_file_coverage`.** Use a process pool
   across files, since each file's analysis is independent.
   - Saving: 26-43 s → ~5 s at 8 processes. Combined with lever 1, the whole
     post-pytest serial segment almost disappears. This is the biggest win for
     the 4-CPU factory pod's average utilisation.
   - Basis: [I], from the cProfile showing per-file pure-Python analysis.

4. **Size the worker count from the CPU allowance, not the node's `nproc`.**
   Read the cgroup `cpu.max` quota or the pod request (the gate template already
   injects `LIVESPEC_TEST_PARALLELISM` for this reason), and set CI runner pods
   explicitly.
   - Saving: removes the 8-vs-18-worker variance. The root leg was 45 s slower
     in pytest, including 44 s more collection.
   - Basis: [M] for the two legs; [I] for the cause, since node identity and
     load for each leg were not checked.

5. **Stop paying cold assertion-rewrite per worker.** Options:
   - (a) A CI cache of `tests/**/__pycache__/*-pytest-8.3.4.pyc`, with source
     mtimes normalised, because pytest validates a rewritten `.pyc` by source
     mtime + size.
   - (b) Split `test_dispatcher.py` (272 KB) and other giant modules, which
     helps xdist import locality only marginally.
   - (c) `--assert=plain` only for the coverage-gate run. This is a policy
     call, because it costs failure diagnostics.
   - Saving: ~**15-25 s per CI leg** (collection 32 s → ~10 s), more with more
     workers.
   - Basis: [M] for the rewrite-to-compile ratio; [I] for the CI saving.

6. **Fix the straggler tail.**
   - Add `--durations=30` (cheap) to the CI per-file job so the slow tests are
     named.
   - Try `--dist worksteal` (xdist ≥3.2), or front-load known-slow tests.
   - Saving: dev-tooling up to ~40 s (its ~50 s unexplained tail);
     orchestrator ~10-20 s.
   - Basis: [M] for the tail shape; [I] for the cause.

7. **CI-only: the nonroot leg's 19 s `chmod -R a+rX /root/.config /root/.local`
   + `chown -R 1000:1000 $GITHUB_WORKSPACE` step.**
   - Saving: ~15 s on the nonroot leg, which is the shorter leg. That matters
     only if the root leg also gets faster.
   - How: narrow the paths, or check out as uid 1000.
   - Basis: [M].

8. **Subprocess coverage overhead.**
   - Each Python test subprocess starts coverage (two `.pth` hooks) and writes a
     `.coverage.*` file for combine.
   - First measure how many data files a run produces (count them before
     combine).
   - Candidate fixes: drop the redundant `.pth` (pytest-cov 6's, or coverage's
     `a1_coverage.pth`, but not both), and point subprocess tests at
     in-process `main()` where they only test argument parsing.
   - Basis: [I]; unmeasured.

9. **`COVERAGE_CORE=sysmon` is not available.**
   - It needs Python ≥3.12, and with `branch = true` it is effective only on
     3.14+. Coverage falls back to `ctrace` on 3.12/3.13 for branch
     measurement. That is from coverage's changelog, recalled rather than
     re-verified here.
   - The fleet pins Python 3.10.16 per the "Toolchain pins" floor, so this is a
     toolchain-bump item, not a config flip.
   - Basis: [M] for the Python version; [I] for any gain.

## Not done, and what would close the gaps

- No full-suite run was made (host constraint), so no measured per-test
  durations exist. Adding `--durations=30` to one CI run closes this.
- The term-missing report's share of the 40 s tail is inferred from the
  standalone 34 s `coverage report`. One CI run with `--cov-report=` would
  measure it directly.
- The number of subprocess `.coverage.*` files and the combine time are not
  measured.
