# Fleet throughput bottlenecks — measured baseline and improvement targets

Maintainer-directed 2026-08-16, opened from the `ci-gate-latency` plan's
close-out: after the worktree-pack preflight fix (livespec-dev-tooling-ebkrhz.1,
PR #1444) the maintainer asked for a broad sweep — "any other low-hanging fruit
to significantly improve the throughput of all of the livespec repos", explicitly
including failure rates, and directed each finding be filed as a child of THIS
plan's epic. This document is the evidence base every child work-item of this
plan references. All Honeycomb figures are from team `thewoolleyweb`, environment
`livespec`, over the 14-day window ending 2026-08-16T06:20Z, queried live during
the research session (query permalinks in each section). Local figures are from
this repo's own gate-run records under `tmp/gate-runs/` on the shared factory
host, measured the same day.

## Finding 1 — the full pytest suite runs TWICE in every gate (top lever)

`check-coverage` (`scripts/just/check-coverage.sh`) and `check-per-file-coverage`
(`scripts/just/check-per-file-coverage.sh`) each run the IDENTICAL
`uv run pytest -n $test_nprocs --cov --cov-branch --cov-config=pyproject.toml`
invocation over the full suite; the per-file variant then runs
`livespec_dev_tooling.checks.per_file_coverage` over the resulting data. Read
directly from both scripts — this is duplication of the entire suite+coverage
run, not two different measurements.

Measured cost, both sides:

- **Local** (gate run `20260816T052036Z-3208187`, branch
  `fix/ebkrhz1-worktree-pack-preflight`, 66/66 passed, wall 40m46s):
  `check-coverage` 1,245.6s + `check-per-file-coverage` 1,188.8s — together
  ~2,434s of a ~2,446s gate. The next-slowest target was 37.2s. The two
  coverage targets ARE the gate wall-time.
- **CI** (github-ci dataset, 14d): the same two jobs are #1 and #2 fleet-wide by
  total compute — 244,054s + 235,770s ≈ **133 CI-hours per 14 days** (Honeycomb
  query 6TVJxVnkKdE).

Fix shape: one suite run produces the `.coverage` data file; both the aggregate
threshold check and the per-file floor check consume it. Expected: ~50% off
local gate wall (~20 min per commit/amend/push) and ~60 CI-hours/14d. Note
`check-coverage` deliberately runs with `COVERAGE_FILE` unset ("clean standalone
suite - strict, matches CI") — the fix must preserve whatever that isolation is
protecting against, or consciously retire it.

Also explains a repo-level skew: livespec-dev-tooling's `ci.run` P50 is 460s vs
146-337s for every other fleet repo (query AtS68TGNQ8z) — it pays the duplicated
suite most heavily.

## Finding 2 — ~20s fixed setup tax on every CI job, ×129,271 jobs/14d

Trivial checks that measure sub-second locally (`check-vendor-manifest` 0.7s,
`check-check-tools` 0.8s, `check-no-todo-registry` local ~1s) cost MIN 16-17s,
P50 24s as CI jobs (query wdizQrEmTVm). The delta is per-job setup
(checkout + mise install + uv sync), paid once per job by design of the
one-job-per-check matrix. Scale (query 6TVJxVnkKdE):

- 129,271 `ci.job.*` spans in 14d, total **8,053,194s ≈ 2,237 CI-hours**.
- The ~60 cheap static checks each pay ~20s+ setup to do ~1s of work: per run,
  ~24 min of job compute that a single batched "static checks" job would do in
  ~2 min (one setup + ~60×1s of checks).

Fix shape: batch the cheap static checks into one (or a few) CI jobs, keeping
the expensive ones (coverage, types, mutation) as separate jobs. Order-of-
magnitude CI compute cut, plus less runner-slot contention for everything else.
Constraint to respect: `check-ci-matrix-completeness` / branch-protection
`ci-green` wiring assume the current per-check job naming — the batching must
carry those checks' individual verdicts into the rollup without weakening
per-check fail-capability.

## Finding 3 — 14× P95 tail on trivial CI jobs (runner contention)

The SAME trivial jobs with P50 24s show P95 344-357s fleet-wide (queries
6TVJxVnkKdE, wdizQrEmTVm) — identical ~1s of work taking 14× longer at the
tail. This is the CI-side signature of shared-host contention on the
self-hosted runners, the same mechanism as the 1,108s local
`check-per-file-coverage` outlier (vs ~130-150s June baseline) that opened the
`ci-gate-latency` plan. The `github-ci` dataset has no queue-time attribute
(schema read via get_dataset_columns), so queue-wait vs execution-slowdown
cannot be separated from current telemetry.

Fix shape: this is what the in-flight fleet-ci-runner-pool Kueue/ARC migration
should recover. File as a MEASUREMENT item, not a duplicate migration item:
re-run the same queries after cutover and verify trivial-job P95 drops from
~345s toward ~25s; add a queue-time attribute to the CI telemetry export so the
next contention episode is attributable (see also the telemetry-gaps section).

## Finding 4 — 12.8% of factory review gates return verdict "unknown"

`livespec-dispatcher` dataset, `review.gate` spans, 14d (query yCWS3SsYPh):
9,944 approve / 1,524 **unknown** / 399 fix / 26 blank = 11,893 total.
Every `unknown` is a completed LLM review pass whose output could not be parsed
into a verdict — ~109 wasted review passes per day, 12.8% of review-gate
capacity. (Span details: `review.fix_rounds` 0 in 95%, `review.hit_cap` false
in all samples — the unknowns are not cap-collisions; they are verdict-parse
failures.)

Fix shape: make the dispatcher's review-verdict extraction robust (structured
output / retry-on-unparseable / prompt tightening), and alarm on the
unknown-rate so regressions surface. Recovers ~13% of review throughput and the
token cost of every wasted pass.

## Finding 5 — failure-rate hotspots: 16% of ci-green rollups are red, led by two sub-second checks

14d, all repos (query 3cTt6toZrhi): `ci-green` failed 164/1,023 runs (**16%**).
Leaf-check leaders:

- `check-no-lloc-soft-warnings` — 122 failures (6.7% of 1,813 runs)
- `check-no-todo-registry` — 100 failures (5.0% of 2,008 runs)
- `check-per-file-coverage` / `check-coverage` — 53/52 (3.1%)
- `check-public-api-result-typed` — 51 (3.0%)

Repo-level job-failure rates: livespec-runtime 1.6%, livespec 1.5%,
livespec-overseer 1.3%; livespec-dev-tooling 0.2% (query i14A2LuKjks).

The two leaders are sub-second checks locally, yet 222 CI runs in 14d went red
on them — each red costing a full fix-and-rerun cycle. The most likely leak:
zero-`.py` changesets take the doc-only pre-commit fast path
(`check-pre-commit-doc-only.sh`, observed live this session: "doc-only subset
(no repo-metadata checks wired yet)"), so TODO-registry and LLOC-warning
violations in doc/CI/shell changesets are never checked locally and surface
only in CI.

Fix shape: wire the cheap, changeset-relevant checks (at minimum
`check-no-todo-registry`, `check-no-lloc-soft-warnings`) into the doc-only
pre-commit subset — converting a full red CI cycle into a ~1s local refusal.
Verify against the actual failing-run changesets before assuming the doc-only
path is the only leak.

## Finding 6 — 128k `bd` CLI calls/14d at P50 378ms; 41% are `bd config`

`bd-guard` dataset, 14d (query jLxuqBYCykQ): 127,962 guarded `bd` invocations,
P50 378ms, P95 919ms. Breakdown: `config` 52,854 (41%!) at P50 349ms ≈ **5.1
hours of pure config-lookup latency**; `show` 41,975; `list` 19,694; `comments`
5,440 — reads total ~93% of traffic, together ~12-13 hours of agent-loop
latency per 14d, paid in-line inside every loop iteration of every session.

Fix shape: session-scoped (or short-TTL) caching for `bd config` — the values
are effectively static within a session — and batched/cached `show` for
repeat-reads. ~10h/14d of latency removed from the fleet's agent loops without
touching write-path safety.

## Exit-criteria protocol (maintainer-directed, binding on every child)

Every child work-item of this plan carries exit criteria naming a HARD,
OBSERVABLE Honeycomb metric: the exact dataset + query shape, the measured
BASELINE from this document, and the closure threshold. An item may not close
on "the change merged" — it closes on a fresh Honeycomb measurement over a
comparable post-change window showing the metric moved, with the query
permalink and the computed percent-improvement recorded in the closing note.

Per-item metrics (baseline, 14d window ending 2026-08-16T06:20Z):

| Item | Honeycomb metric (dataset · query shape) | Baseline |
| --- | --- | --- |
| .1 coverage dedup | github-ci · SUM(duration_ms) of `ci.job.check-coverage` + `ci.job.check-per-file-coverage`; secondary: dev-tooling `ci.run` P50 | 479,824s/14d; 460s P50 |
| .2 CI job batching | github-ci · SUM(duration_ms) over all `ci.job.*`; jobs-per-run COUNT | 8,053,194s/14d; ~64 jobs/run |
| .3 runner tail | github-ci · P95(duration_ms) of trivial jobs (`check-vendor-manifest`, `check-check-tools`, `check-no-todo-registry`) | ~345s (P50 24s) |
| .4 review verdicts | livespec-dispatcher · COUNT(`review.verdict`="unknown") / COUNT on `review.gate` | 12.8% (1,524/11,893) |
| .5 red-cycle prevention | github-ci · failure COUNT of `check-no-todo-registry` + `check-no-lloc-soft-warnings`; `ci-green` fail rate | 222 fails/14d; 16% |
| .6 bd caching | bd-guard · COUNT(`bd.subcommand`="config") and SUM(duration_ms) over read subcommands | 52,854 calls; ~12-13h/14d |

**Running summary report.** On EVERY child closure, the closer appends a
handoff comment to this plan's epic containing the running table for ALL
children — three columns exactly: item id, metric, percent improved (blank
until an item closes) — freshly measured via Honeycomb at that moment, with
query permalinks. The final table at plan archive is the plan's completion
evidence.

## Cross-references and telemetry gaps

- The worktree-pack preflight fix (finding 7 of the originating sweep) is DONE:
  livespec-dev-tooling-ebkrhz.1, PR #1444, measured 3.7s self-heal vs a wasted
  ~25-30-min gate run. Not re-filed here.
- `livespec-dev-tooling-7us.7` (xdist worker-cap tuning under real load) and
  `livespec-dev-tooling-e60` (RGR/agent-loop Honeycomb observability) remain
  open on their own tracks; finding 3's contention numbers are fresh evidence
  for 7us.7, and the telemetry gaps below belong to e60's scope:
  - `ci.run` spans carry an empty `ci.conclusion` (query m7Vh1wwuwkh);
  - no queue-time attribute exists on CI job spans;
  - local/detached gate runs are entirely unobserved in Honeycomb (checked
    live: `claude_code.tool.execution` MAX duration is 3.5s — long-running
    gates never appear).
- The June baseline research (`archive/research/justcheck-performance/`) and the
  `ci-gate-latency` plan's `gate-speed-followups.md` are the priors this sweep
  corrects and extends; the parallel dispatcher and pre-push green-token are
  SHIPPED (7us.3/.4) and deliberately out of scope here.

## Fleet-scope audit (maintainer-directed, 2026-08-16)

The maintainer asked for confirmation that every item applies to every governed
repo — fleet and adopters. The audit (every governed repo's origin/master read
locally, same day) found the original filing under-scoped and corrected it with
scope-amendment riders on .1/.2/.5, a new child .7, and this section.

Per-repo facts, verified not assumed:

| Repo | coverage pair in justfile | local dedup | gate runner |
| --- | --- | --- | --- |
| livespec | yes | **YES — reference implementation** | no |
| livespec-dev-tooling | yes (via scripts/just/*.sh) | no | **yes (only repo)** |
| livespec-driver-claude / -codex / -pi | yes | no | no |
| livespec-orchestrator-beads-fabro / -git-jsonl | yes | no | no |
| livespec-overseer / livespec-runtime | yes | no | no |
| livespec-console-beads-fabro | check-coverage only (no per-file) | n/a | no |

**Erratum (2026-08-21, recorded at archive; the table above is left as
written because it is the record of what the audit believed).** Two
corrections filed on `livespec-dev-tooling-yilyxr.8` on 2026-08-17 showed the
"local dedup" column wrong for five of the eight "no" rows: livespec-driver-claude,
livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl,
livespec-overseer and livespec-runtime each already carried a firing
"no duplicate suite run" reuse conditional (in four different homes), and
every consumer runs a SERIAL aggregate that orders check-per-file-coverage
before check-coverage, so those repos already ran the suite once per
aggregate. The only genuine local double-runs were livespec-driver-codex and
livespec-driver-pi. The real fleet defects .8 then fixed were staleness
(every conditional reused ANY leftover `.coverage`; fixed by consume-once),
measurement-env hardening, and the two codex/pi dependency re-runs; the
CI-side pair cost was standalone-job duplication by design, removed by the
#1504/#1511-shaped producer/consumer chain ported to every Python repo on
2026-08-19. Separately, the ".3 / .4 / .6 are inherently fleet-scoped (shared
infrastructure)" premise below is false for .3's telemetry half: each repo runs
its OWN copy of `.github/scripts/export-ci-telemetry.sh`, so PR #1470's
`ci.job.queue_ms` reached dev-tooling only (594/594 spans there, 0/6,989
elsewhere, 48h to 2026-08-21); the port is tracked as a named successor item
in this repo's ledger, discovered-from `yilyxr.3`.

What this changes:

- **.1 (coverage dedup)** is fleet-scoped across the 8 duplicating repos, with
  livespec's `check-coverage` recipe as the reference implementation: it reuses
  the `.coverage` file `check-per-file-coverage` produced ("no duplicate suite
  run") and only runs the suite standalone (the CI-matrix case). The CI-side
  duplication persists even in livespec (each coverage job is a standalone
  runner) — only job consolidation (.2) removes that half.
- **.2 / .5** were already fleet-wide in their Honeycomb baselines; riders make
  the fleet scope explicit (per-repo ci.yml wired to the canonical matrix; the
  doc-only pre-commit path shared through the canonical pre-commit scripts).
- **.7 (new)**: the detached gate runner + worktree-pack preflight exists ONLY
  in dev-tooling, while every governed repo carries the worktree pack and both
  exposures the runner fixes (silent 20-min harness kills; the
  `worktree_pack_absent` wasted run). .7 distributes it fleet-wide through each
  repo's own gates.
- **.3 / .4 / .6** are inherently fleet-scoped (shared runner infrastructure, a
  single dispatcher service, shared bd-guard) — no amendment needed.
- **Adopters** outside the fleet inherit every canonical-carrier change (.1's
  recipe if canonicalized, .2's matrix, .5's pre-commit scripts, .7's runner)
  through the same template / pin-bump propagation that carries every other
  shared-enforcement change; nothing here is fleet-member-only by construction.

## Fleet-rollout restructure (maintainer-directed, 2026-08-16, same day)

The maintainer directed that the missed fleet work be first-class work items,
not scope riders. Ledger state after the restructure:

- **.1 / .2 / .5** remain the canonical-mechanism owners (recipe shape, matrix
  redesign, doc-only-subset fix).
- **NEW .8 / .9 / .10** are their fleet-confirmation companions: .8 coverage
  dedup landed in the 8 duplicating repos; .9 batched matrix landed in every
  repo's ci.yml; .10 doc-only pre-commit wiring effective per repo (with
  planted-violation repro in the 3 worst repos).
- **.7** (gate-runner adoption) strengthened to the same standard.
- **Binding per-repo exit criteria** on .7/.8/.9/.10: closure requires a
  verified per-repo confirmation table across all 10 governed repos — columns:
  repo | verified state | evidence (merged commit/PR + per-repo Honeycomb query
  where measurable) — rows verified against each repo's origin/master, modeled
  on the audit table above; not-applicable rows must state why; adopter
  propagation (template / pin-bump fan-out) must be confirmed in the closing
  note. The plan-wide running-summary-table obligation applies to these items
  like every sibling.
- **.3 / .4 / .6** stay single-shared-surface items (no per-repo rollout
  exists), with closing measurements broken down by repo where the dataset
  supports it.
