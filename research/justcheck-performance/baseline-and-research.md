# `just check` performance — baseline and optimization research

Work-item: **livespec-dev-tooling-7us.1** (research-only child of the
just-check-performance epic). Measured 2026-06-12.

## Bottom line

- A full `just check` pass costs **~3.2–4.3 minutes** in the two heavy
  consumers (livespec-dev-tooling: 191.6s cold / 222.1s warm over 45
  targets; livespec: 259.7s cold / 196.6s warm over 50 targets) and
  ~52–67s in the three siblings (impl-beads 67.2s, impl-git-jsonl
  63.9s, runtime 52.0s).
- **One target dominates**: `check-per-file-coverage` (the single full
  `pytest -n auto --cov --cov-branch` run) is 60–69% of the
  dev-tooling pass and 42–47% of the livespec pass. Top-3 targets
  (per-file-coverage, types, coverage) are ~75% of dev-tooling's pass.
- Of the pytest target itself, **coverage instrumentation is ~2.8x**:
  744 tests at `-n auto` take 44.6–52.0s without `--cov` vs
  132.8–141.6s with it (Python 3.10 C tracer; `sysmon` core needs
  ≥3.12).
- The other ~42 "cheap" targets are ~0.5–3s each — dominated by
  **per-process Python import cost (~0.5s)**, not by uv (`uv run`
  no-sync overhead ≈ 0.05–0.1s) and not by work.
- **Target-level parallelism works and is the cheapest big win**: the
  42 cheap dev-tooling targets run serially in 30.1s, at `-P 4` in
  9.7s, at `-P 8` in 5.1s (same-load back-to-back A/B, zero failures).
  A simulated fully-parallel aggregate (pytest+cov, pyright, and the
  cheap block all concurrent) completed in **103.7s wall vs 192–222s
  serial** — the floor is the pytest+cov suite itself.
- Per RGR cycle the local gates alone cost ~8–10 minutes today (Red
  hook 58.0s dt / 89.2s ls, Green-amend full pass, pre-push full
  pass). A 5-commit multi-RGR item pays **~25–38 minutes of pure gate
  wall-time** before any implementation work — a large bite out of the
  ~2h ACP sandbox ceiling. The proposed items below cut that ~3–4x.

## Measurement context (read before trusting any number)

- Host: 18 cores (`nproc` = 18 — note the "18-worker" in the
  hypothesis-deadline flake livespec-6sxd is exactly `-n auto` here),
  94 GiB RAM, Linux 6.17.
- **The host was under concurrent heavy load during measurement**
  (sibling implementer agent running `just check`/pytest in
  livespec-impl-beads, plus a Fabro docker sandbox running a full
  dispatch). Observed `uptime` load averages ranged **7.3–22.4**
  across the session. Numbers are load-inflated but representative of
  real dispatch conditions. Load-bearing numbers were sampled twice
  (cold + warm passes; two extra samples for the pytest
  decomposition); single-pass sibling numbers were sampled once.
- Variance examples (treat ±20–30% as noise): livespec
  `check-per-file-coverage` 120.9s cold vs 81.9s warm; dev-tooling's
  warm pass (222.1s) ran *slower* than its cold pass (191.6s) because
  load was higher during the warm pass. There is no meaningful
  cold-vs-warm cache effect in these aggregates beyond venv creation —
  `.ruff_cache` and `.pytest_cache` move nothing measurable.
- Method: scratch worktrees at `origin/master` (livespec-dev-tooling
  `1eeb328` v0.13.0, livespec `af3ac7a`, impl-beads `e468a44`,
  impl-git-jsonl `8d146eb`, runtime `2b62c5b`). Venv via
  `uv sync --all-groups` directly — **not** `just bootstrap`, which
  must not be run in a worktree (it clobbers the shared
  `.git/config` `livespec.primaryPath`; bug found by a sibling agent
  during this session). This does not skew cold-start numbers: the
  venv-relevant part of bootstrap is the same `uv sync`.
- Per-target wall-time = `date +%s.%N` around `just <target>`, output
  captured to files, exit codes recorded. **All 318 recorded target
  runs exited 0.** Aggregate-faithful env: dev-tooling pass ran with
  one up-front `uv sync` + `UV_NO_SYNC=1` (matching its `check:`
  recipe); livespec and the siblings ran without it (matching theirs —
  see "ool gap" below).
- "cold" = freshly created worktree, freshly synced `.venv` (uv wheel
  cache warm; network-cold sync NOT measured), no `.pytest_cache` /
  `.ruff_cache` / `.coverage`. "warm" = immediate second pass.

## Baseline matrix

### Pass totals

| repo | targets | cold (s) | warm (s) | notes |
|---|---:|---:|---:|---|
| livespec-dev-tooling | 45 | 191.6 | 222.1 | warm > cold = host-load noise |
| livespec | 50 | 259.7 | 196.6 | |
| livespec-impl-beads | 44 | — | 67.2 | single pass (fresh venv) |
| livespec-impl-git-jsonl | 46 | — | 63.9 | single pass |
| livespec-runtime | 43 | — | 52.0 | single pass |

Cold venv creation (`uv sync --all-groups`, warm uv wheel cache):
dev-tooling 11.9s, livespec 8.7s, impl-beads 5.5s, git-jsonl 0.9s,
runtime 2.1s. One-time per worktree; not a per-pass cost.

### Top targets by share of pass

| repo | target | cold / warm (s) | share of warm pass |
|---|---|---|---:|
| dev-tooling | check-per-file-coverage | 132.8 / 141.6 | 64% |
| dev-tooling | check-types (pyright) | 14.7 / 16.5 | 7% |
| dev-tooling | check-coverage (report read) | 6.0 / 8.7 | 4% |
| dev-tooling | other 42 targets (sum) | 38.1 / 55.3 | 25% |
| livespec | check-per-file-coverage | 120.9 / 81.9 | 42% |
| livespec | e2e-test-claude-code-mock | 21.1 / 17.3 | 9% |
| livespec | check-types | 23.2 / 16.8 | 9% |
| livespec | check-coverage (report read) | 20.1 / 16.4 | 8% |
| livespec | check-doctor-static | 8.4 / 5.6 | 3% |
| livespec | check-prompts | 5.2 / 2.4 | 1% |
| livespec | other 44 targets (sum) | 60.8 / 56.2 | 28% |

In the small repos the inversion is total: runtime's
check-per-file-coverage is only 13.6s and the ~40 cheap targets'
fixed overhead (~25s) is ~half the pass.

### Hook-leg reality (what actually runs, measured)

| leg | dev-tooling | livespec |
|---|---:|---:|
| Red pre-commit (`just skip="check-coverage check-per-file-coverage" check`, real run) | 58.0s | 89.2s |
| commit-msg replay (pytest on the staged test file, representative file) | ~9.8–10.1s | not measured (same mechanism) |
| Green-amend pre-commit (full aggregate; livespec skips only check-red-green-replay) | ≈ full pass (192–222s) | ≈ full pass (197–260s) |
| pre-push (full aggregate when any .py changed) | ≈ full pass | ≈ full pass |
| doc-only subset (`check-pre-commit-doc-only`) | 0.08s (stub) | 5.2s (6 targets) |

So one RGR commit cycle + push = Red (58–89s) + replay (~10s) +
Green (~200–260s) + pre-push (~200–260s) ≈ **7.5–10 min of serial
local gating**, and CI re-runs everything as a parallel per-target
matrix (off the local critical path; wall there is bounded by the
slowest matrix job). A 5-commit item ≈ 25–38 min of gates.

### Fixed per-invocation overhead decomposition

Measured on a representative cheap check (`check-main-guard`,
dev-tooling, warm, 3 samples each):

| layer | wall |
|---|---|
| `just <target>` (whole thing) | 0.60–0.72s |
| `uv run python -m <module>` (UV_NO_SYNC=1) | 0.43–0.67s |
| `.venv/bin/python -m <module>` | 0.48–0.91s |
| `.venv/bin/python -c "import <module>"` | 0.50s |
| bare `python -c pass` | 0.02–0.04s |
| `uv run` wrapper itself (no sync) | 0.05–0.11s |
| no-op `uv sync --all-groups` (warm) | 0.07–0.41s |

**The fixed cost is Python import time (~0.5s), not uv and not just.**
At ~42 cheap targets that is ~21s/pass of pure import overhead
(plus ~10–30s of actual check work).

The `UV_NO_SYNC` up-front-sync pattern (work-item
livespec-dev-tooling-ool) exists **only in this repo's justfile**.
livespec and all three siblings still pay a per-target sync probe:
A/B on 10 cheap livespec targets measured 9.87s with per-target sync
vs 7.34s with `UV_NO_SYNC=1` → **~0.25s/target ≈ 12.5s/pass** left on
the table in livespec (plus the venv-corruption race window the ool
work documented).

### Pytest decomposition (dev-tooling, 744 tests)

| variant | wall |
|---|---|
| `pytest --collect-only -q` | 2.5s |
| `pytest -n auto` (18 workers), no cov | 52.0s / 44.6s (2 samples) |
| `pytest -n 8 --cov --cov-branch` | 106.5s |
| `pytest -n auto --cov --cov-branch` (the shipped recipe) | 132.8s / 141.6s |
| single test file (17 tests, subprocess-heavy) | 9.8s / 10.1s |

Two load-bearing facts:

1. **Coverage is ~2.8x.** `--cov --cov-branch` under Python 3.10's
   C tracer adds ~85–95s to a ~45–50s suite. The `sysmon` coverage
   core (`COVERAGE_CORE=sysmon`) that removes most tracing overhead
   requires Python ≥ 3.12 (and branch-coverage support there is even
   newer); the fleet pins **3.10.16**, so this lever is locked
   behind a Python-bump epic. Recorded here so any future bump epic
   picks it up.
2. **18 workers is slower than 8 with coverage on this host** (132.8
   / 141.6s at `-n auto`=18 vs 106.5s at `-n 8`, measured under
   sibling load). Over-subscription costs real time AND is the
   established flake mechanism (livespec-6sxd: hypothesis-deadline
   flake at 18 workers). Caveat: single `-n 8` sample on a loaded
   host; re-verify once on an idle host before pinning a number.

## Findings per research angle

### (1) Parallelization — biggest cheap win; do it at target level

`just` has no jobserver, but it doesn't need one: the aggregate is
already a bash for-loop over `just <target>` invocations, so a
parallel dispatcher is a drop-in change to one recipe (xargs -P /
a small python driver), not a build-system migration.

Measured (dev-tooling, back-to-back at load ~7.7):

- 42 cheap targets: serial 30.1s → `-P 4` 9.7s → `-P 8` 5.1s, zero
  failures, zero venv contention (with `UV_NO_SYNC=1`, `uv run` is
  read-only on the venv; WITHOUT it, concurrent per-target syncs are
  exactly the corruption race the ool comment documents — the
  up-front-sync pattern is a prerequisite for safe parallelism).
- Full-aggregate simulation (check-per-file-coverage in one lane,
  check-types in another, cheap block at `-P 8`): **103.7s wall**
  vs 192–222s serial. cheap+types lane finished at 17.4s; the rest
  is waiting for pytest+cov.
- Target-level vs test-level: test-level parallelism is already
  maxed (`-n auto` inside the big target); the unexploited axis is
  target-level. The right composition is the opposite of naive: give
  the pytest+cov target the cores (it is the critical path), cap it
  at ~8–12 workers, and run pyright + the cheap block in its shadow.
- Constraints/dependencies discovered: `check-coverage` READS the
  `.coverage` file `check-per-file-coverage` writes (explicit
  dependency edge; today guaranteed by alphabetical order);
  `check-master-ci-green` / `check-branch-protection-alignment` are
  network-bound (gh api, ~2–3s) and parallelize trivially; per-target
  stdout must be buffered and replayed to keep failure output
  readable (the measurement harness already did this).
- Flake risk: bounding total concurrent CPU demand (xdist workers +
  cheap lane ≤ nproc) directly addresses the 6sxd mechanism. The
  cheap checks are single-threaded AST walks; only pytest and pyright
  multiplex.

### (2) Short-circuit / no-op — Red leg and pre-push are the targets

- The doc-only fast path already exists and is cheap (5.2s livespec /
  0.08s dev-tooling) but only fires on zero-.py changesets.
- The Red leg already skips the only pytest-running targets. What's
  LEFT at Red is the cheap-block sum + pyright (+ in livespec:
  e2e-mock 17–21s, prompts 2–5s, doctor-static 6–8s — ~40–50% of the
  livespec Red leg gated on artifacts a staged-test-file commit
  cannot touch). Scoping those three out at Red (by staged-path
  class, same mechanism check-pre-commit already uses) cuts livespec
  Red from ~89s to ~40–50s with zero safety loss (Green/pre-push/CI
  unchanged).
- "Run only the staged test file at Red": the commit-msg replay hook
  ALREADY does exactly this (~10s). The pre-commit Red aggregate is
  pure repo-state gating; it runs no suite. So the staged-test-only
  idea is already implemented where it matters.
- Impacted-module pytest subsetting via import-graph: **not
  recommended.** It fundamentally conflicts with the 100% per-file +
  aggregate coverage gates (a partial suite produces partial coverage
  data → the gates would have to be skipped → the leg stops meaning
  anything), and the measured ceiling is modest anyway once the suite
  runs in parallel with everything else.
- Per-target input manifests for no-op fast-exit: correct idea, but
  measured value on the cheap block is small (the whole block is 5.1s
  parallel); its real payoff merges into the result-cache item below.

### (3) Caching / daemonization — one big win (pre-push token), several deads

- **Pre-push green-token short-circuit (recommended).** The Green
  amend runs the FULL aggregate; pre-push then re-runs the identical
  aggregate against the byte-identical tree minutes later (~200–260s
  of pure repetition per push). A token recording (HEAD tree-hash,
  uv.lock hash, target-set hash) written on a green full pass and
  honored by `check-pre-push` (clean worktree + matching tree-hash →
  skip) eliminates a full pass per RGR cycle. CI remains the
  authoritative gate; the token is a local-only advisory, exactly like
  the existing doc-only short-circuit. This is the
  "result-cache keyed on (target, tree-hash)" idea reduced to the one
  place it pays.
- Persistent venv: landed (ool) in this repo; **porting it is the
  cheapest item on the list** (~12.5s/pass in livespec + corruption-
  window elimination + parallelism prerequisite; siblings similar).
- pytest collection cache: dead end — collection is 2.5s of a 132s
  target.
- pyright incremental/watch daemon: pyright CLI has no cross-run
  cache; a watch daemon helps interactive loops but not one-shot
  hooks. Under the parallel dispatcher, check-types (15–23s) runs
  entirely inside the pytest target's shadow, so its wall-time
  contribution drops to zero. Defer.
- Warm interpreter daemon for the ~45 python startups: measured
  import overhead is ~21s/pass serial, but the parallel dispatcher
  already hides it (5.1s wall for the whole cheap block). A simpler
  non-daemon variant — one python process importing
  `livespec_dev_tooling` once and dispatching checks in-proc (39 of
  41 check modules already expose a uniform `main()`) — is worth
  having only if the parallel dispatcher is rejected, or for CI job
  consolidation. Defer behind item 1.

### (4) Measurement-first — instrument the aggregate

The `check:` loop already prints `::: just <target>` headers; adding
per-target wall-time to that line (plus an optional machine-readable
summary) is a few lines in one recipe and gives every future session
(and the e60 Honeycomb proposal) longitudinal data for free. All
numbers in this report came from an external harness because this
instrumentation doesn't exist yet.

## Proposed impl child items (ordered by impact/effort)

1. **Parallel check-aggregate dispatcher (dev-tooling first, then
   fleet).** Replace the serial for-loop in `check:` with a
   parallel scheduler: heavy lane (check-per-file-coverage, capped
   `-n 8..12`) starts first; cheap lane fans out at `-P 4..8`;
   explicit edge per-file-coverage → check-coverage; per-target
   output buffered, replayed serially on completion/failure; `skip=`
   semantics preserved; per-target wall-time emitted (folds in item
   6). Acceptance: same target set, all-green, wall ≤ 60% of the
   serial baseline on the same host (measured sim: 103.7s vs
   192–222s), no new flakes across 20 consecutive runs. Expected:
   dev-tooling ~220s → ~105s; livespec ~200–260s → ~120–140s (its
   heavy lane has 4 independent slow targets — e2e-mock, types,
   doctor-static, prompts — that overlap well). Risk: medium —
   contention flakes (mitigated by the core-budget cap; 6sxd prior
   art), output interleaving.
2. **Pre-push green-token short-circuit.** Record (tree-hash,
   uv.lock-hash, target-set-hash) on a green FULL aggregate; let
   `check-pre-push` skip when HEAD's tree matches and the worktree is
   clean; any mismatch → full run. Acceptance: push immediately after
   a green Green-amend completes its pre-push gate in <10s; mutating
   any tracked file invalidates the token. Expected: −190–260s per
   push (one full pass per RGR cycle). Risk: medium — token-trust
   design must be advisory-local with CI authoritative; needs the
   "fix the gate, not the bypass" framing review.
3. **Port the ool up-front-sync (`UV_NO_SYNC`) pattern to livespec +
   impl-beads + impl-git-jsonl + runtime.** Measured ~0.25s/target
   (~12.5s/pass in livespec); also the safety prerequisite for item
   1's parallel `uv run`s and closes the concurrent-sync corruption
   window fleet-wide. Acceptance: all four `check:` recipes sync
   once up-front and export UV_NO_SYNC=1. Risk: low (pattern proven
   in this repo).
4. **Scope the livespec Red-leg target set by staged-path class.**
   At Red (single staged test file), additionally skip e2e-mock /
   prompts / doctor-static unless the staged path is under their
   input trees (tests/e2e/, tests/prompts/, SPECIFICATION/ +
   prose). Expected: livespec Red 89s → ~40–50s (~17 + 2–5 + 6–8s
   removed); with item 1 the Red leg drops to ~types-bound ~20–25s.
   Acceptance: Red-mode commit with a staged unit-test file skips the
   three targets; a staged tests/e2e/ file does not. Risk: low-medium
   (scoping rule must live next to the existing Red-shape detection,
   full aggregate untouched at Green/pre-push/CI).
5. **Cap pytest-xdist workers for coverage runs.** `-n auto` (=18
   here) measured slower than `-n 8` WITH cov (132.8/141.6 vs
   106.5s) and is the 6sxd flake mechanism. Make the worker count a
   just-variable default (e.g. `min(auto, 8)`) overridable per
   invocation; verify once on an idle host before pinning.
   Acceptance: per-file-coverage wall non-regressing, 6sxd-style
   hypothesis-deadline flake non-reproducing under concurrent load.
   Risk: low.
6. **Per-target wall-time instrumentation in the aggregate output**
   (feeds the e60 Honeycomb proposal). If item 1 lands, it carries
   this; file separately only if item 1 stalls. Risk: trivial.

**Explicitly not proposed** (measured dead ends): pytest collection
caching (2.5s), impacted-test-subset selection (conflicts with the
100% coverage gates), pyright daemon (hidden by item 1),
in-proc batch check runner (hidden by item 1; revisit for CI),
`COVERAGE_CORE=sysmon` (locked behind a Python ≥3.12 bump — attach to
any future Python-bump epic, the single biggest lever on the pytest
target at ~2.8x).

### Tie to the epic's success criterion

Today a 5-commit multi-RGR dispatch pays ~25–38 min of local gates.
With items 1–4: Red ≈ 25s, Green ≈ 105–140s, pre-push ≈ 10s →
5-commit item ≈ **8–12 min of gates** — comfortably inside the ~2h
ACP ceiling even with implementation work, doctor, and PR mechanics
on top. CI is unaffected throughout (parallel matrix, already
off the local critical path).

## Appendix A — full per-target matrices

### livespec-dev-tooling (45 targets; cold then warm; UV_NO_SYNC aggregate-faithful)

| target | cold (s) | warm (s) |
|---|---:|---:|
| check-aggregate-completeness | 0.86 | 1.69 |
| check-all-declared | 0.91 | 1.9 |
| check-assert-never-exhaustiveness | 1.33 | 1.82 |
| check-branch-protection-alignment | 2.24 | 3.16 |
| check-check-coverage-incremental | 1.35 | 1.31 |
| check-check-mutation | 0.65 | 1.14 |
| check-check-tools | 1.07 | 1.96 |
| check-claude-md-coverage | 0.43 | 1.28 |
| check-comment-line-anchors | 0.84 | 2.28 |
| check-commit-pairs-source-and-test | 1.41 | 1.71 |
| check-file-lloc | 0.62 | 3.75 |
| check-global-writes | 0.65 | 1.83 |
| check-heading-coverage | 0.71 | 0.93 |
| check-keyword-only-args | 1.03 | 2.18 |
| check-main-guard | 0.68 | 0.8 |
| check-master-ci-green | 2.0 | 2.18 |
| check-match-keyword-only | 0.97 | 1.1 |
| check-newtype-domain-primitives | 0.39 | 0.82 |
| check-no-direct-destructive-cli | 0.73 | 1.12 |
| check-no-direct-tool-invocation | 0.57 | 0.77 |
| check-no-except-outside-io | 0.49 | 0.81 |
| check-no-inheritance | 0.9 | 0.86 |
| check-no-lloc-soft-warnings | 1.21 | 1.32 |
| check-no-raise-outside-io | 0.83 | 0.79 |
| check-no-todo-registry | 0.56 | 1.35 |
| check-no-write-direct | 1.05 | 0.69 |
| check-pbt-coverage-pure-modules | 0.64 | 1.19 |
| check-per-file-coverage | 132.82 | 141.59 |
| check-primary-checkout-commit-refuse-hook-installed | 0.55 | 1.54 |
| check-private-calls | 0.8 | 1.06 |
| check-public-api-result-typed | 0.9 | 0.68 |
| check-red-green-replay | 0.58 | 0.61 |
| check-rop-pipeline-shape | 0.74 | 0.73 |
| check-skill-invocation-paths | 1.2 | 0.72 |
| check-supervisor-discipline | 0.81 | 0.6 |
| check-tests-mirror-pairing | 0.61 | 0.53 |
| check-tool-backed-check-completeness | 0.59 | 1.02 |
| check-vendor-manifest | 0.9 | 0.83 |
| check-wrapper-shape | 1.05 | 0.59 |
| check-lint | 0.63 | 2.8 |
| check-format | 1.47 | 0.93 |
| check-types | 14.71 | 16.52 |
| check-coverage | 6.0 | 8.72 |
| check-fleet-conformance | 0.79 | 0.86 |
| check-fabro-image-pin-lockstep | 1.3 | 0.99 |
| **total** | **191.6** | **222.1** |

### livespec (50 targets; cold then warm; per-target sync, aggregate-faithful)

| target | cold (s) | warm (s) |
|---|---:|---:|
| check-aggregate-completeness | 1.23 | 0.69 |
| check-all-declared | 0.99 | 0.94 |
| check-assert-never-exhaustiveness | 0.83 | 1.31 |
| check-branch-protection-alignment | 2.54 | 2.74 |
| check-check-coverage-incremental | 1.24 | 0.65 |
| check-check-mutation | 0.72 | 0.62 |
| check-check-tools | 0.9 | 1.12 |
| check-claude-md-coverage | 1.6 | 1.25 |
| check-comment-line-anchors | 2.83 | 0.8 |
| check-commit-pairs-source-and-test | 0.96 | 2.17 |
| check-file-lloc | 1.64 | 2.7 |
| check-global-writes | 1.16 | 1.28 |
| check-heading-coverage | 1.0 | 1.17 |
| check-keyword-only-args | 0.86 | 1.37 |
| check-main-guard | 0.73 | 0.93 |
| check-master-ci-green | 1.96 | 2.13 |
| check-match-keyword-only | 0.66 | 0.92 |
| check-newtype-domain-primitives | 1.17 | 1.55 |
| check-no-direct-destructive-cli | 1.35 | 1.22 |
| check-no-direct-tool-invocation | 0.69 | 0.77 |
| check-no-except-outside-io | 0.77 | 0.92 |
| check-no-inheritance | 1.24 | 0.6 |
| check-no-lloc-soft-warnings | 0.76 | 1.82 |
| check-no-raise-outside-io | 0.9 | 1.79 |
| check-no-todo-registry | 1.02 | 0.77 |
| check-no-write-direct | 0.82 | 2.06 |
| check-pbt-coverage-pure-modules | 1.01 | 2.08 |
| check-per-file-coverage | 120.88 | 81.85 |
| check-primary-checkout-commit-refuse-hook-installed | 0.89 | 0.63 |
| check-private-calls | 0.44 | 0.56 |
| check-public-api-result-typed | 0.79 | 0.68 |
| check-red-green-replay | 1.8 | 0.51 |
| check-rop-pipeline-shape | 2.01 | 0.73 |
| check-skill-invocation-paths | 2.08 | 0.59 |
| check-supervisor-discipline | 1.1 | 1.03 |
| check-tests-mirror-pairing | 1.29 | 1.65 |
| check-tool-backed-check-completeness | 2.94 | 0.68 |
| check-vendor-manifest | 0.99 | 0.9 |
| check-wrapper-shape | 1.05 | 0.57 |
| check-comment-no-historical-refs | 3.26 | 2.75 |
| check-copier-template-smoke | 2.62 | 2.76 |
| check-coverage | 20.11 | 16.38 |
| check-doctor-static | 8.36 | 5.61 |
| check-format | 4.42 | 2.21 |
| check-imports-architecture | 1.48 | 1.31 |
| check-lint | 0.86 | 1.05 |
| check-prompts | 5.23 | 2.38 |
| check-schema-dataclass-pairing | 1.33 | 1.29 |
| check-types | 23.16 | 16.8 |
| e2e-test-claude-code-mock | 21.06 | 17.27 |
| **total** | **259.7** | **196.6** |

### livespec-impl-beads (44 targets; single pass)

| target | wall (s) |
|---|---:|
| check-aggregate-completeness | 1.27 |
| check-all-declared | 0.66 |
| check-assert-never-exhaustiveness | 1.12 |
| check-branch-protection-alignment | 1.19 |
| check-check-coverage-incremental | 0.62 |
| check-check-mutation | 0.72 |
| check-check-tools | 0.88 |
| check-claude-md-coverage | 0.52 |
| check-comment-line-anchors | 1.84 |
| check-commit-pairs-source-and-test | 0.8 |
| check-file-lloc | 0.77 |
| check-global-writes | 0.62 |
| check-heading-coverage | 0.55 |
| check-keyword-only-args | 0.66 |
| check-main-guard | 0.71 |
| check-master-ci-green | 2.45 |
| check-match-keyword-only | 0.54 |
| check-newtype-domain-primitives | 0.48 |
| check-no-direct-destructive-cli | 0.5 |
| check-no-direct-tool-invocation | 0.59 |
| check-no-except-outside-io | 1.28 |
| check-no-inheritance | 1.42 |
| check-no-lloc-soft-warnings | 0.84 |
| check-no-raise-outside-io | 0.54 |
| check-no-todo-registry | 0.53 |
| check-no-write-direct | 0.46 |
| check-pbt-coverage-pure-modules | 0.5 |
| check-per-file-coverage | 25.53 |
| check-primary-checkout-commit-refuse-hook-installed | 1.01 |
| check-private-calls | 0.49 |
| check-public-api-result-typed | 0.47 |
| check-red-green-replay | 0.47 |
| check-rop-pipeline-shape | 0.54 |
| check-skill-invocation-paths | 0.65 |
| check-supervisor-discipline | 0.61 |
| check-tests-mirror-pairing | 0.56 |
| check-tool-backed-check-completeness | 0.52 |
| check-vendor-manifest | 0.49 |
| check-wrapper-shape | 0.72 |
| check-format | 0.65 |
| check-lint | 0.81 |
| check-types | 7.05 |
| check-coverage | 3.0 |
| check-work-item-merge-evidence | 0.53 |
| **total** | **67.2** |

### livespec-impl-git-jsonl (46 targets; single pass)

| target | wall (s) |
|---|---:|
| check-aggregate-completeness | 1.17 |
| check-all-declared | 0.61 |
| check-assert-never-exhaustiveness | 0.78 |
| check-branch-protection-alignment | 1.33 |
| check-check-coverage-incremental | 0.83 |
| check-check-mutation | 0.66 |
| check-check-tools | 1.15 |
| check-claude-md-coverage | 0.78 |
| check-comment-line-anchors | 1.17 |
| check-commit-pairs-source-and-test | 0.67 |
| check-file-lloc | 0.61 |
| check-global-writes | 0.58 |
| check-heading-coverage | 0.43 |
| check-keyword-only-args | 0.59 |
| check-main-guard | 0.58 |
| check-master-ci-green | 2.06 |
| check-match-keyword-only | 0.68 |
| check-newtype-domain-primitives | 0.59 |
| check-no-direct-destructive-cli | 0.57 |
| check-no-direct-tool-invocation | 0.65 |
| check-no-except-outside-io | 0.51 |
| check-no-inheritance | 0.57 |
| check-no-lloc-soft-warnings | 1.36 |
| check-no-raise-outside-io | 1.74 |
| check-no-todo-registry | 0.73 |
| check-no-write-direct | 0.74 |
| check-pbt-coverage-pure-modules | 0.5 |
| check-per-file-coverage | 22.19 |
| check-primary-checkout-commit-refuse-hook-installed | 0.5 |
| check-private-calls | 1.32 |
| check-public-api-result-typed | 0.53 |
| check-red-green-replay | 0.8 |
| check-rop-pipeline-shape | 0.56 |
| check-skill-invocation-paths | 0.59 |
| check-supervisor-discipline | 0.53 |
| check-tests-mirror-pairing | 0.81 |
| check-tool-backed-check-completeness | 0.49 |
| check-vendor-manifest | 0.89 |
| check-wrapper-shape | 0.58 |
| check-format | 1.6 |
| check-lint | 0.87 |
| check-types | 5.78 |
| check-coverage | 1.99 |
| check-no-divergent-heads | 0.28 |
| check-no-raw-store-read | 0.42 |
| check-work-item-merge-evidence | 0.57 |
| **total** | **63.9** |

### livespec-runtime (43 targets; single pass)

| target | wall (s) |
|---|---:|
| check-aggregate-completeness | 1.25 |
| check-all-declared | 0.58 |
| check-assert-never-exhaustiveness | 0.51 |
| check-branch-protection-alignment | 2.27 |
| check-check-coverage-incremental | 1.67 |
| check-check-mutation | 0.95 |
| check-check-tools | 0.77 |
| check-claude-md-coverage | 0.63 |
| check-comment-line-anchors | 0.54 |
| check-commit-pairs-source-and-test | 0.61 |
| check-file-lloc | 0.66 |
| check-global-writes | 0.57 |
| check-heading-coverage | 0.59 |
| check-keyword-only-args | 0.57 |
| check-main-guard | 0.65 |
| check-master-ci-green | 1.72 |
| check-match-keyword-only | 0.47 |
| check-newtype-domain-primitives | 0.49 |
| check-no-direct-destructive-cli | 0.53 |
| check-no-direct-tool-invocation | 0.9 |
| check-no-except-outside-io | 0.71 |
| check-no-inheritance | 0.63 |
| check-no-lloc-soft-warnings | 0.66 |
| check-no-raise-outside-io | 0.43 |
| check-no-todo-registry | 0.57 |
| check-no-write-direct | 0.59 |
| check-pbt-coverage-pure-modules | 0.5 |
| check-per-file-coverage | 13.6 |
| check-primary-checkout-commit-refuse-hook-installed | 1.05 |
| check-private-calls | 0.57 |
| check-public-api-result-typed | 0.63 |
| check-red-green-replay | 0.92 |
| check-rop-pipeline-shape | 0.48 |
| check-skill-invocation-paths | 0.66 |
| check-supervisor-discipline | 0.87 |
| check-tests-mirror-pairing | 0.77 |
| check-tool-backed-check-completeness | 0.7 |
| check-vendor-manifest | 0.79 |
| check-wrapper-shape | 0.55 |
| check-lint | 1.37 |
| check-format | 0.36 |
| check-types | 6.05 |
| check-coverage | 1.59 |
| **total** | **52.0** |

## Appendix B — explicitly NOT measured

- Idle-host numbers (all measurements under sibling-agent load,
  load avg 7.3–22.4; deliberately accepted as representative).
- Network-cold `uv sync` (uv wheel cache was warm in every "cold"
  measurement).
- Cold/warm distinction for the three sibling repos (single pass
  each).
- livespec commit-msg replay-hook wall-time (mechanism identical to
  dev-tooling's measured ~10s single-file pytest).
- CI wall-times (per-target parallel matrix on GitHub runners; off
  the local critical path that this item targets).
- `-n 8` no-cov, `-n 12`/`-n 4` cov variants (only `-n 8` and
  `-n auto`=18 with cov were sampled).

## Appendix C — reproduction

Harness (external; per-target instrumentation does not exist yet):

```bash
# in a scratch worktree at origin/master, after `uv sync --all-groups`
for t in $(awk '/^    targets=\(/,/^    \)/' justfile \
           | grep -E '^\s+(check-|e2e-)' | awk '{print $1}'); do
  s=$(date +%s.%N); just "$t" >/tmp/out 2>&1; rc=$?
  echo "$t $(echo "$(date +%s.%N) $s" | awk '{printf "%.2f", $1-$2}') rc=$rc"
done
```

Key one-offs: `pytest --collect-only -q`, `pytest -n auto -q`,
`pytest -n 8 --cov --cov-branch --cov-config=pyproject.toml -q`,
`just skip="check-coverage check-per-file-coverage" check`,
`xargs -a cheap-targets.txt -P 8 -I{} sh -c 'just {} >/dev/null'`
(with `UV_NO_SYNC=1` after one up-front sync). Raw CSV from this
session: 318 rows, all rc=0 (kept out of the repo; regenerate with
the loop above).
