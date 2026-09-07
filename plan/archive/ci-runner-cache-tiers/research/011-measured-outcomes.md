# 011 — Measured outcomes: what the cache tiers changed, from the standing queries

Written 2026-09-06 (04:40Z–05:10Z) by the plan session, at the maintainer's
direction that hard before/after data, absolute and percentage, for every
caching improvement is a gate of this plan, and per decision D1 that
single-run hand-read numbers are not the plan's evidence. Every number
below comes from a Honeycomb query in environment `livespec` (datasets
`github-ci` and `metrics`), the ledger, or the GitHub API; the query run id
is beside each table so the row can be re-run. Nothing here is a status
queue; the ledger is the status.

## The one-paragraph answer

With the crates proxy (A1) and the host sccache (B1) live and warm, the
console's full CI matrix on the pool runs at **P50 329 s, P90 370 s**
(26 runs over 32 hours), against **P50 474 s, P90 1235 s** on the same pool
without them (99 runs, 2026-08-22 to 09-01) and the ~430 s hosted
warm-cache baseline the charter names: **-31% at P50, -70% at P90, and 23%
under the hosted number**. The uv seed tier is hit on 100% of routed jobs
in all ten repositories with zero workflow changes, and the pool-owned
canary shows those jobs' in-pod time is 8–36% lower than the same jobs run
cold. Two things the data also says, neither flattering: most of the
matrix-level win between late August and now came with the storage move to
NVMe rather than from the caches (the no-cargo `check-format` job fell by
the same proportion as the compile jobs), and the compile cache is
**cold right now** — since the 01:59Z proving reboot on 2026-09-06 the
sccache hit ratio is 0.35%, the hit-floor trigger is firing, `cargo clippy`
takes 2.1× and `cargo nextest` 1.9× what they took warm, and the matrix
P90 has gone from 370 s to 661 s. That is `livespec-dev-tooling-efqeip.3`,
and it is the next thing this plan should fix.

## How to read the windows

The console repository is the only routed repository that compiles Rust,
so it is the matrix the charter's acceptance names. Its routing history,
from the GitHub API's per-job runner labels (not from the `CI_RUNNER_LABELS`
variable, whose creation date is 2026-09-04 for every repo because the
variables were recreated that morning):

| Period | Where the console's jobs ran | State of the caches |
|---|---|---|
| to 2026-08-05 at least | hosted `ubuntu-latest` | GitHub `actions/cache`, warm |
| 2026-08-17 → 2026-09-04 09:00Z | pool `livespec-console-beads-k3s` on the RAID array (a hosted excursion on 2026-09-02 during the provisioner-stall recovery) | tier 1 uv seed only; every Rust job compiled its whole dependency graph |
| 2026-09-04 10:00Z → 17:00Z | pool, array | A1 crates proxy + B1 sccache (research/006's reruns) |
| 2026-09-04 17:30Z → 2026-09-06 01:59Z | pool, `ci-workvols` on the first NVMe | A1 + B1, sccache **warm** (populated 2026-09-04) |
| 2026-09-06 02:00Z → 04:45Z | pool, two NVMe, `ci-workvols` XFS reflink | A1 + B1, sccache **cold** (RAM-only redis emptied by the 01:59Z reboot; the populator's busy-pool guardrail skipped every refill) |

The `check-fuzz` job was added on 2026-08-22, so the "before" window opens
at 2026-08-22 21:00Z and every matrix row below is a run whose trace
contains a `ci.job.check-fuzz` span — a full matrix, not a docs-only run.
The hosted baseline predates fuzz (its ~5-minute job is now the matrix's
critical path), which makes every pool-versus-hosted comparison below
conservative in the pool's disfavour.

## 1. The console matrix wall-clock (`ci.run` spans)

| Window | Medium / cache state | Runs | P50 | P90 | Min | Query |
|---|---|---|---|---|---|---|
| Hosted, 2026-07-16 | hosted, warm `actions/cache` (hand-read, `livespec-dev-tooling-9mp`) | 3 | 427 / 424 / 448 s | — | — | ledger |
| Before: 2026-08-22 21:00Z → 09-01 | pool, array, uv only | 99 (83 push, 16 PR) | push **474 s**, PR 568 s | push **1235 s**, PR 1832 s | 318 s | `HvyRR3oT5HF` |
| 2026-09-04 10:00Z → 17:00Z | pool, array, A1 + B1 | 4 | 401 s (871, 395, 364, 358) | — | 358 s | `f7M7oZS9pfX` |
| Warm: 2026-09-04 17:30Z → 09-06 01:59Z | pool, NVMe, A1 + B1 warm | 26 | **329 s** | **370 s** | 303 s (full runs) | `GQKTRwQNZpg` |
| Cold: 2026-09-06 02:00Z → 04:45Z | pool, 2× NVMe, sccache cold | 19 | **383 s** | **661 s** | 325 s | `Fp21tiNYEsB` |

Deltas: before → warm, P50 474 → 329 s (**-31%**), P90 1235 → 370 s
(**-70%**); warm versus the ~430 s hosted baseline, **-23%** at P50 and
-14% at P90; warm → cold, P50 +16%, P90 +79%. The July self-hosted cold
number was 883 s (`9mp`, podman lane) and research/006's proxy-only rerun
on 2026-09-04 was 871 s; both are in the table's lineage but neither is a
window.

The charter's first acceptance criterion — "at or below the hosted warm
baseline, from run spans, not a one-off run" — is **met for the warm
window** on 26 runs, P50 and P90 both under 430 s. In the cold window the
P50 still clears it and the P90 does not.

## 2. Per-job wall-clock, and why the matrix delta is mostly not the caches

P50 / P90 in seconds, console `ci.job.*` spans, push and PR.

| Job | Hosted Jul (n=3) | Before, array, uv only (n=105) | Warm, NVMe (n=26) | Cold sccache (n=19) | Before → warm |
|---|---|---|---|---|---|
| check-fuzz | — | 403 / 524 | 315 / 330 | 318 / 347 | -22% |
| check-nextest | 134 / 134 | 270 / 411 | 73 / 109 | 78 / 110 | -73% |
| check-clippy | 70 / 71 | 182 / 280 | 61 / 84 | 69 / 84 | -66% |
| check-coverage | 119 / 123 | 245 / 368 | 84 / 99 | 90 / 110 | -66% |
| check-mutants | — | 126 / 235 | 74 / 112 | 69 / 82 | -41% |
| check-deps | 43 / 45 | 188 / 319 | 38 / 53 | 37 / 51 | -80% |
| check-e2e-tmux | 204 / 207 | 256 / 379 | 158 / 175 | 144 / 245 | -38% |
| **check-format (no cargo build)** | 27 / 27 | **134 / 265** | **30 / 59** | 27 / 40 | **-78%** |

Queries: hosted `w6Jy7E9g8Ng`, before `G21vk5mfgCb`, warm `BzHDNbU4TXn`,
cold `bFHHqUKy5mb`.

Read the last row first. `check-format` compiles nothing and touches no
cache tier, and it fell 134 → 30 s across the same boundary as the compile
jobs. The pool in late August was contention-bound on the RAID array (the
2026-09-01 provisioner stall is inside that window; research/004 and the
sibling lifecycle plan's research/005 measured the start burst), and the
storage move on 2026-09-04 removed most of that. So the per-job "before →
warm" column is the pool getting a faster disk **and** the caches, and it
cannot be attributed to the caches alone. The cache attribution has to
come from measurements taken on the same medium with the cache on and off,
which is what the next two sections are.

## 3. The compile cache (B1): same medium, warm versus cold

The shim-level `build.cargo-*` spans time exactly one cargo invocation
and carry that invocation's own sccache ratio. Console, `build.env=ci`,
P50 / P90 in seconds, average per-span sccache hit ratio.

| Cargo phase | Warm (n) | Cold (n) | Warm → cold |
|---|---|---|---|
| cargo-clippy | 20.2 / 22.9, ratio 1.00 (8) | 43.0 / 48.3, ratio 0.01 (18) | **+113%** |
| cargo-nextest | 13.1 / 19.0, ratio 0.49 (16) | 24.7 / 40.1, ratio 0.00 (36) | **+88%** |
| cargo-test | 59.8 / 63.3, ratio 0.80 (8) | 67.7 / 77.7, ratio 0.01 (18) | +13% |
| cargo-llvm-cov | 40.5 / 55.2, ratio 0 (16) | 43.0 / 58.3, ratio 0 (38) | +6% (never cached, see below) |
| check-fuzz.compile (step) | 78 / 86 (26) | 87 / 117 (19) | +12% (nightly, never cached) |

Queries: warm `AAoywgQYVYJ`, cold `jMRzhaqSvyU`.

Aggregate, console `cache.job-summary` spans with sccache enabled, canary
excluded, alongside the host's redis gauge:

| Window | Jobs | Hits | Misses | Hit ratio | Jobs with zero hits | Host `hit_ratio_5m` avg (ticks) | Queries |
|---|---|---|---|---|---|---|---|
| Warm | 126 | 4371 | 3000 | **59.3%** | 40 | 0.91 (78) | `jct6GQbDCFi`, `CpMQDZwTqnV` |
| Cold | 183 | 27 | 7706 | **0.35%** | 156 | 0.14 (23) | `DJWaA6Qkefp`, `3KNjeLHArwg` |

The 40 zero-hit jobs in the warm window are not rot; they are three job
kinds whose compilations sccache never sees a match for, visible in the raw
per-job rows (`quZbfAZshDv`): `check-coverage` (llvm-cov instrumentation
flags, 2/113 per job), `check-fuzz` (nightly toolchain, 10/90), and one
more at 0/114 per job (the mutants profile). The populator builds none of
those three profiles. That is a lever — populate the coverage and mutants
profiles and the warm ratio rises from ~59% toward ~85% — but it is not this
plan's accepted scope and it is recorded here as an observation for the
maintainer, not filed.

The cold window is `livespec-dev-tooling-efqeip.3` exactly as filed at
04:24Z: redis is RAM-only, the 01:59Z proving reboot emptied it, CI was
restored at 02:07Z, and every populate tick since has skipped the sccache
build because the pool was busy. Redis's cumulative counters since the
reboot read 579 hits / 17,174 misses at 04:44Z. The hit-floor trigger
`HfK9RB9tZYp` is **triggered** as of 04:42Z. Archive-evidence item 3 in
research/003 ("the hit-floor trigger has never fired outside a toolchain
bump") is therefore false as written: it fires after a host reboot, and
will on every reboot until `efqeip.3` lands. The item should be re-based
to "outside a toolchain bump or a host reboot" only if the maintainer
decides not to fix `efqeip.3`; the recommendation is to fix it (redis RDB
snapshot on the `ci-cache` tier so a reboot restores the last generation,
plus a one-shot post-boot populate that ignores the busy guardrail once)
and let the clock start from that landing.

Other host gauges over both windows: `memory_ratio` max 0.01 of the
16 GiB ceiling; `populate.repos_failed` max 0 (the populate-failing trigger
has never had cause); `generation_age_s` max 6988 s in the warm window (the
2026-09-04 17:00–17:43Z NVMe install hold) and 8969 s in the cold window
(the reboot), both back under the 30-minute cadence afterwards.

## 4. The uv seed and registry tiers, fleet-wide, warm versus canary

`cache.warm-copy` spans since 2026-09-04, all routed repositories
(6170 spans, `AJdcsQqr5YM`): with the kill switch off, `build.cache.hit`
is **true on 100%** of spans for both the `uv` and `registry` tiers in
every one of the ten routed repositories (livespec, livespec-dev-tooling,
livespec-overseer, livespec-orchestrator-beads-fabro,
livespec-orchestrator-git-jsonl, livespec-driver-claude, -codex, -pi,
livespec-console-beads-fabro, livespec-runtime), with zero workflow changes
in any of them — the charter's third criterion, met ten times over rather
than once. Canary jobs (`kill_switch=canary`, 1 in 20 by pod-name hash) are
0% by construction. The hook's own elapsed for the seed: P50 26–33 ms warm
across repos; canary 2.0–5.0 s, which is the cost of unlinking the seed the
provisioner already made. By seed mechanism (`64ZFqAZstqk`): hardlink seed
2464 spans at P50 28 ms; reflink seed (since 03:30Z on 2026-09-06)
462 spans at P50 27 ms; registry served 2926 spans at P50 32 ms. The seed
itself is paid in the provisioner before the pod starts and was measured on
the host (`hmv2bo`): byte copy 6.8 s / 2,153 MB → hardlink ~3 s / ~0 MB →
reflink 13.3 s / 165 MB of metadata, on a 191k-file, 2.1 GB generation.

In-pod job time (the `cache.job-summary` span, postStart to preStop), P50
seconds, warm versus canary per repository (`63cwbdYwg2a`):

| Repository | Warm (n) | Canary (n) | Delta |
|---|---|---|---|
| livespec-dev-tooling | 19.3 (497) | 30.1 (26) | **-36%** |
| livespec-driver-codex | 16.9 (209) | 25.8 (15) | -35% |
| livespec-orchestrator-git-jsonl | 15.3 (183) | 21.9 (9) | -30% |
| livespec-overseer | 18.2 (392) | 25.7 (18) | -29% |
| livespec | 20.9 (514) | 28.1 (27) | -26% |
| livespec-driver-claude | 17.9 (179) | 22.2 (13) | -19% |
| livespec-orchestrator-beads-fabro | 26.6 (218) | 32.2 (16) | -17% |
| livespec-driver-pi | 16.6 (164) | 19.8 (12) | -16% |
| livespec-console-beads-fabro | 28.7 (492) | 31.1 (20) | -8% |
| livespec-runtime | 15.1 (77) | 7.4 (3) | n too small |

About 3 s of every canary figure is the seed unlink, so the tier's own
saving is the delta less ~3 s (dev-tooling: 27.1 → 19.3 s, -29%). The
console's small delta is expected: its in-pod time is Rust, and the canary
switches off the seed tiers, not the host-served sccache. The canary gap
has held every day since 2026-09-04 18:00Z; archive-evidence item 2 asks
for two consecutive weeks, so the earliest it can be attested is
2026-09-18.

Registry tier (A1): `build.cache.registry.hit` is true on 100% of the 530
CI `build.cargo-*` spans (`u2NMosNiay4`). Its wall-clock contribution is
small by design (research/005: the win is in B1); the no-op
`cargo fetch --locked` floor of 2.3 s → 0.39–0.46 s recorded on `kjanc4`
was the removal of an unreachable-endpoint POST timeout, a telemetry fix,
and is not claimed here as a cache saving.

## 5. What is not yet evidenced

- **Factory parity (evidence item 6).** The only `build.env=factory` spans
  carrying the console's repo are the 60 from the 2026-09-04 22:32–22:42Z
  pollution window (`u2NMosNiay4`); their `registry.hit` is 0% and their
  sccache ratio 0 because the cross-repo half (`bd-ib-nslh`, the
  orchestrator's ledger) has not landed. No factory dispatch has yet shown
  `build.cache.sccache.*` populated.
- **Negative tests on the timer (evidence item 4).** Seven scheduled runs
  from 2026-09-04 15:31Z to 09-05 18:27Z were red by design (case 1 was
  re-based by `hmv2bo`); the 2026-09-06 01:06Z run was **skipped, not
  failed** — the workflow's `if` gate saw the runner variable pointing at
  hosted during the reboot window; the 03:48Z dispatch `34009895497` is
  green. The cron is `17 */6` and GitHub fires it ~20 minutes late, so the
  two scheduled greens `hmv2bo` needs are the ~06:37Z and ~12:33Z runs on
  2026-09-06.
- **The canary gap over two weeks (item 2)** — earliest 2026-09-18.
- **The hit-floor trigger (item 3)** — false as written; see §3.

## Standing queries for the archive review

| Question | Query shape (dataset `github-ci` unless noted) |
|---|---|
| Console matrix on the pool over time | `ci.run`, repo = console, `any.name = ci.job.check-fuzz`; P50/P90 `duration_ms` by `ci.event` |
| Compile cache warm vs cold | `build.cargo-*`, repo = console, `build.env = ci`; P50 `duration_ms` and AVG `build.cache.sccache.hit_ratio` by `name` |
| sccache aggregate per repo | `cache.job-summary`, `build.cache.sccache.enabled = true`, `kill_switch != canary`; SUM hits, SUM misses by `repo` |
| Second-routed-repo hits | `cache.warm-copy`; COUNT where `build.cache.hit = true` by `repo`, `build.cache.tier`, `build.cache.kill_switch` |
| Canary gap | `cache.job-summary`; P50 `duration_ms` by `repo`, `build.cache.kill_switch` |
| Host floor | dataset `metrics`, `host.name = poweredge-xubuntu`; AVG `livespec.ci_cache.sccache.hit_ratio_5m`; trigger `HfK9RB9tZYp` |
| Negative tests | `gh run list --workflow ci-cache-negative-tests.yml`; trigger `rxd7n9GVBYx` |
