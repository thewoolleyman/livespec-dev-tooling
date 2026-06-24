# Telemetry-informed CI build-speed analysis — livespec fleet

**Work-item:** livespec-dev-tooling-7us.10 (epic 7us — agent-loop + enforcement-suite performance)
**Data source:** Honeycomb env `livespec`, dataset `github-ci` (closed-loop CI export per livespec `SPECIFICATION/non-functional-requirements.md` §"CI telemetry export", history/v121).
**Window analyzed:** current closed-loop export `library.name = livespec.github-ci-export` (post-uv-cache; the representative "current CI" data). Historical `livespec.tmp.capture-runtime-telemetry` (275 runs, retired harvester) used only for trend context — and discarded as non-comparable (see Caveats).
**Generated:** 2026-06-20.

---

## 1. Data inventory & honesty caveats

The current closed-loop export is young and thin. Whole-run (`ci.run`) sample counts:

| repo | current-export `ci.run` count | usable? |
|---|---|---|
| `thewoolleyman/livespec-impl-beads` | 10–11 | yes (primary) |
| `thewoolleyman/livespec` | 9 | yes (primary) |
| `thewoolleyman/livespec-dev-tooling` | 1 | single sample only |
| `thewoolleyman/livespec-driver-claude` | 1 | single sample only |
| `thewoolleyman/livespec-impl-git-jsonl` | 1 | single sample only |
| `thewoolleyman/livespec-runtime` | 1 | single sample only |

So the **statistically meaningful** ranking rests on `livespec` (n=9) and `livespec-impl-beads` (n=10–11); the other four repos contribute single data points (directional only).

**Caveats (stated up front so the ranking isn't over-read):**
- **`repo` field differs by library.** Current export uses org-prefixed `thewoolleyman/<repo>`; the historical harvester used bare `<repo>`. All current-export queries filter on the prefixed form.
- **`duration_ms` is second-granular** (rounded to whole seconds), so percentiles land on 1000 ms boundaries. Fine for ranking; don't read sub-second precision into it.
- **Historical vs current is NOT a valid before/after.** Historical P50s are *lower* (livespec 56s vs current 73s; beads 31s vs current 50s) — but the historical set mixes `pull_request` runs (which gate out the `.py` matrix on doc-only PRs → much faster) while the current export is **`push`/`merge_group` only** (the full matrix always runs). The check count also grew between the two windows. The apparent "regression" is a population artifact, not a uv-cache regression. No uv-cache delta is claimed from this comparison.
- **All 519 current-export job spans concluded `success`.** The failure-distribution view is wired but has not yet captured a red run, so no failure ranking is presented.

---

## 2. Ranked long-pole report (current export)

### 2a. Per-job ranking — `livespec` (n=9, master pushes)

| rank | job | P50 | MAX | character |
|---|---|---|---|---|
| 1 | **check-coverage** | **52s** | 61s | full `pytest -n auto --cov` suite + per-file gate |
| 2 | **check-types** | **22s** | 23s | `uv run pyright` (whole tree) |
| 3 | check-doctor-static | 14s | 19s | doctor static phase over all trees |
| 4 | check-schema-dataclass-pairing | 10s | 19s | AST check |
| 5 | check-comment-no-historical-refs | 11s | 18s | grep/AST check |
| … | ~30 more checks | **9–14s** | 14–18s | **flat floor — see §3** |
| — | detect-py-changes (setup) | 9s | 18s | serialized prefix — see §4 |

### 2b. Per-job ranking — `livespec-impl-beads` (n=11)

| rank | job | P50 | MAX |
|---|---|---|---|
| 1 | **check-coverage** | **30s** | 37s |
| 2 | **check-types** | **18s** | 21s |
| 3 | check-tool-backed-check-completeness | 10s | 17s |
| … | flat floor | 9–14s | 13–16s |
| — | detect-py-changes (setup) | 9s | 13s |

### 2c. Whole-run wall-clock (`ci.run`, current export)

| repo | P50 | P95 | n |
|---|---|---|---|
| livespec-dev-tooling | 104s | — | 1 |
| **livespec** | **73s** | 77s | 9 |
| **livespec-impl-beads** | **50s** | 54s | 10 |
| livespec-impl-git-jsonl | 35s | — | 1 |
| livespec-runtime | 34s | — | 1 |
| livespec-driver-claude | 16s | — | 1 |

### The shape (the load-bearing finding)

Three regimes, identical across both well-sampled repos:

1. **check-coverage** dominates — 3–5× the median check. This is genuine work (full test suite under coverage instrumentation, `-n auto`). **Owned by the open sibling 7us.7** (pytest-xdist worker-cap tuning). Confirmed #1 by data; not re-filed here.
2. **check-types** is a clear, distant #2 (`pyright`, ~18–22s). It only becomes the wall-clock pole if coverage drops below it.
3. **~30 remaining checks form a flat ~9–14s floor.** impl-beads' floor ≈ livespec's floor *despite impl-beads having a far smaller check suite* — proving the floor is **fixed per-job startup overhead** (runner provisioning + checkout + `mise` install + `uv sync`), not the check's own work (which is ~1–2s of grep/AST).

---

## 3. Where the wall-clock actually goes (critical path)

The CI workflow (`livespec` and the 4 other setup-pattern repos) is structured:

```
setup (detect-py-changes + uv pre-warm)   ← runs ALONE, ~9–18s
        │  every matrix job `needs: setup`
        ▼
[ check-python ∪ check-metadata matrix ]   ← parallel; gated by check-coverage (~52s)
        │
        ▼
export-telemetry                            ← master/merge_group only
```

So on a master push the critical path is **`setup` (~9–15s) → `check-coverage` (~52s)** ≈ the observed ~73s wall-clock. The ~30 floor jobs run in parallel and finish (~15s) long before coverage, so **they do not affect wall-clock** — they cost runner-minutes (billing), not latency.

Empirical corroboration: **livespec-driver-claude has no `setup` job** (unified matrix, jobs self-restore the uv cache) and posts the **lowest wall-clock (16s)** in the fleet.

---

## 4. Prioritized remaining-optimization list

Each item carries an explicit **coverage-preservation rationale** (no check is removed or weakened by any proposal here).

### W1 — De-serialize the `setup` uv pre-warm  ★ top remaining win, fleet-wide

**Finding.** `setup` runs `mise install` + `actions/cache` + `uv sync --all-groups` to pre-warm `~/.cache/uv` *once* before the matrix; every matrix job `needs: setup`, so **check-coverage cannot start until the pre-warm finishes** (~9–15s on the critical path, every run). But:
- `actions/cache` **persists across runs** keyed on `uv.lock`. On the >99% of runs where the lock is unchanged, the cache already exists globally → matrix jobs hit the exact key and never touch PyPI **with or without the warm**. The pre-warm is redundant on these runs yet still serializes the whole matrix behind it.
- The pre-warm's only real value is the first run after a lock change. Even there, the matrix jobs' own `restore-keys: uv-<os>-` prefix fallback means only the *delta* wheels re-fetch (in parallel, with `UV_HTTP_RETRIES=5`), not a full cold herd.

**Fix.** Shrink `setup` to the change-detection gate only (checkout + `git diff` for `py_changed`); drop the `mise`/`cache`/`uv sync` pre-warm steps from it. Matrix jobs **already** independently restore the cache + run `uv sync` (verified in all 5 setup-pattern repos), so they are self-sufficient. `needs: setup` stays (for the gate output) but now waits only ~3–5s.

**Expected win.** ~5–10s off the critical path typical (up to ~13s at the tail), on **every** `push`/`merge_group` run. Biggest *relative* gain on the light repos whose total is dominated by the prefix (driver-claude-style ~16–35s repos → 15–40%); ~7–13% on livespec.

**Coverage preservation.** No check removed; the `py_changed` gate logic is byte-identical; matrix self-restore already exists. The only behavioral change is on lock-change runs (parallel delta-fetch instead of one serial warm), bounded by the prefix restore-key + retries. **driver-claude already runs exactly this de-serialized shape in production with no ill effect.**

**Scope (fleet-wide).**
- Hand-authored `ci.yml` — fix directly, one PR each: **livespec, livespec-dev-tooling, livespec-runtime**.
- Copier template `templates/impl-plugin/.github/workflows/ci.yml.jinja` — fix once; **impl-beads + impl-git-jsonl** inherit via `copier update --vcs-ref=master`.
- **driver-claude** — N/A (already de-serialized).

### W2 — check-types (pyright) caching/scoping — *investigate, low confidence*

**Finding.** `check-types` = `uv run pyright` over the whole tree, ~18–22s, the #2 per-job pole. It has no cross-run cache.

**Why not a cheap PR.** pyright has no robust on-disk incremental cache across fresh CI runners; scoping it to changed files would weaken type coverage (a type error in an un-changed file that a changed signature introduces would be missed). Any speedup here must preserve whole-tree analysis → not a clear win. Flagged for investigation only.

**Coverage preservation.** Would require proving no loss of whole-tree type coverage; do not pursue as a quick win.

### W3 — Collapse the ~30-job fixed-overhead floor — *spec-level tradeoff, not a cheap PR*

**Finding.** ~30 trivial AST/grep checks each pay ~9–14s of fixed startup to do ~1–2s of work. This is the fleet's largest **billing** cost (~30 × ~10s ≈ 300 wasted runner-seconds per livespec run) — but **not** a wall-clock cost (they finish before coverage).

**Why not a cheap PR.** Consolidating fast checks into fewer jobs collides with the `SPECIFICATION/non-functional-requirements.md` check-invocation-surface contract ("one job per check via a matrix strategy"), with branch-protection per-check required-status-check names, and with the per-`ci.job.name` granularity the telemetry export itself depends on. Changing it is a deliberate contract decision (propose-change/revise), not a tactical optimization.

**Coverage preservation.** Consolidation must preserve per-check pass/fail attribution (a grouped job that fails must still pinpoint which check failed) — achievable but it is a spec change, out of scope for this item. Surfaced for maintainer decision.

### W4 — Cache the built `.venv` (not just the uv download cache) — *investigate, lower confidence*

**Finding.** Every matrix job rebuilds `.venv` via `uv sync` (~2–4s) even on a warm download cache. Caching `.venv` keyed on `uv.lock` + python version could cut the floor further.

**Why not now.** venv portability across runner instances is not guaranteed (absolute paths / interpreter pinning); correctness risk outweighs the ~2–4s/job billing gain, and it does not move wall-clock. Investigate behind W1.

---

## 5. Recommendation

1. **Land W1** as a fleet epic: livespec + dev-tooling + runtime (direct), plus the copier template (→ impl-beads, impl-git-jsonl). Recommend doing **livespec first**, letting the closed-loop telemetry confirm the wall-clock drop on master, then propagating to the template + siblings (telemetry-informed propagation, matching the repo's careful style).
2. **Coverage (the true #1 long pole) stays with 7us.7.** This analysis confirms it is the dominant cost and that CI's `-n auto` already caps at runner cores; add a coordination note to 7us.7 with the CI-side numbers.
3. **W2/W3/W4** are documented above as deliberately-not-cheap; W3 (job-floor consolidation) is the largest *efficiency* prize but is a spec-level call for the maintainer.

---

## 6. Rollout (W1) — executed as a fleet epic (2026-06-20)

| repo | change | PR |
|---|---|---|
| livespec | own `ci.yml` + copier template `ci.yml.jinja` (siblings inherit) | #487 |
| livespec-dev-tooling | own `ci.yml` + this report | (this PR) |
| livespec-runtime | own `ci.yml` | filed |
| livespec-impl-beads | `copier update --vcs-ref=master` (after #487 merges) | follows template merge |
| livespec-impl-git-jsonl | `copier update --vcs-ref=master` (after #487 merges) | follows template merge |
| livespec-driver-claude | none — already de-serialized (no setup job) | n/a |

W2/W3/W4 left as documented findings for maintainer decision; coverage (the #1 pole) remains with 7us.7.
