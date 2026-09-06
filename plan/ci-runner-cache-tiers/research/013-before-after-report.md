# 013 — Before → after, per tier and per repository, from Honeycomb

The maintainer's archive condition for this plan (stated 2026-09-06): improvement
numbers, before and after, for everything the plan did, presented for approval
before any archive. This note is that report, composed 2026-09-06T16:40Z by the
plan session. Every AFTER cites the Honeycomb query it was read from; BEFORE
values come from this plan's `research/011` windows or, where named, the console
plan's `research/008` / `research/011`. Percentages are `(after − before) / before`
at P50.

**Amended 2026-09-06T17:40Z.** At composition the compilation cache's win was
NOT being delivered: the writer's cache puts had not reached redis since the
01:59Z reboot (`livespec-dev-tooling-efqeip.4`, P1). That regression was
diagnosed and fixed the same afternoon (PR #1890, `08ff6f37`, converged
17:36Z); the last section now carries the cause and the recovered numbers. The
tables say what the tiers do when they work, and as of 17:36Z they do.

## The two substrate changes that are not this plan's

| Change | When | Effect on every row below |
|---|---|---|
| Pool work volumes and containerd moved from the RAID-5 array to NVMe; `ci-workvols` reformatted XFS `reflink=1` | 2026-09-04T17:10Z (single card), 2026-09-05 (second card, XFS) | the disk knee that rejected B2 and bounded the uv seed is gone; every per-job number improved by this alone (console `check-shell-quality`, which compiles nothing: 136 → 32 s) |
| Console CI parallelism (`CARGO_BUILD_JOBS=12`) and the fuzz-capable image | console plan, 2026-09-05/06 | console compile phases and `check-fuzz` wall time; separated out in the console rows |

Where a row cannot separate the disk from the cache, it says so.

## Tier by tier

| Tier (item) | What it replaced | BEFORE | AFTER | Δ | Evidence |
|---|---|---|---|---|---|
| A1 warm cargo registry + git, host-SERVED through the crates proxy (`oiltq3`) | per-job crates.io fetch, or a 379 → 1,388 MB per-start byte copy | registry fetch per job; the byte-copy variant cost 6.8 s and 2,153 MB written per job start (research/005) | `build.cache.registry.hit = true` on 100 % of 530 CI `build.cargo-*` spans; 0 bytes copied per start; console `check-deps` 188 → 37 s (−80 %, NVMe + proxy, not separable) | — | research/011 §2; console research/011 (`94dxd82kfDd`) |
| B1 host sccache, redis-backed, jobs read-only (`ddiszt`) | every job compiling the dependency graph cold | console `cargo clippy` 43.0 s, `cargo nextest` 24.7 s, `cargo test` 67.7 s (same medium, cache cold) | 20.2 s / 13.1 s / 59.8 s with the cache warm (−53 % / −47 % / −12 %); host hit ratio 0.91; per-job hit ratio 59.3 % over 126 jobs (40 of them uncached profiles) | −53 % on the clippy phase | research/011 §3 (the same-medium warm-vs-cold pair) |
| Console full matrix (charter criterion 1) | hosted warm-cache baseline ~430 s | array + uv tier only: P50 474 s / P90 1,235 s (99 push runs, 08-22..09-01) | NVMe + A1 + B1 warm: P50 329 s / P90 370 s (26 runs, 09-04T17:30Z..09-06T01:59Z) — 23 % under the hosted baseline | −31 % / −70 % | research/011 §1 |
| uv warm tier, reflink SEED (`hmv2bo`, with the lifecycle plan's from-empty generation) | a per-job byte copy of the uv cache (0.8 s at 379 MB, 6.8 s at 1,388 MB), then a hardlink seed that a job could write through | byte copy 6.8 s / 2,153 MB written per start | reflink seed 13.3 s on the 191k-file generation, 3.0 s on the 12,192-file from-empty generation, 0 data bytes, every inode the job's own; `uv sync` 7.9 s → 0.5 s; hook `cache.warm-copy` `hit=true` on 100 % of non-canary jobs in all ten routed repositories | −56 % per-start (13.3 → 3.0 s after the generation shrank; 0 bytes vs 2.1 GB) | warm-cache README §"What it buys, measured"; `hmv2bo` 06:06Z comment; research/011 §2 |
| Target tier, ASAN fuzz key, reflink-seeded (`c5byjh` decided; shipped by console `ydlant` in this repo's `c4b70c2c`) | the console's fuzz job compiling ASAN objects cold every run | `build.check-fuzz.compile` P50 78 s | 4 s (n = 21); `check-fuzz` job wall 316 → 224 s; generation 264 MB / 328 files, seeded by reflink | −95 % on the phase, −29 % on the job | research/012; console research/011 (`hBdGTVBtYWv`, `xaE3EmeUvD7`) |
| Compilation-cache persistence (`efqeip.3`) | RAM-only redis: every reboot emptied the cache and the busy-pool guardrail kept it empty for hours (1 % hit rate measured 2026-09-06 morning) | after the 01:59Z reboot: sccache 59.3 % → 0.35 %, host hit ratio 0.91 → 0.14, `cargo clippy` 20.2 → 43.0 s | dump.rdb on the ci-cache tier, `--save 300 1 60 10000` + SIGTERM save + populator BGSAVE; a restart restores the keyspace (probe-proven 06:42Z; the 10:00Z idle tick read the restored marker; the 17:37Z credential-rotation pod roll restored all 422 keys) | the reboot penalty is bounded by one populate tick INSTEAD of hours | `efqeip.3` comments 06:5xZ, 08:08Z, 10:05Z; `efqeip.4` 17:36Z comment |
| Writer-server isolation (`efqeip.4`) | the writer's cargo talked to whichever sccache server the pod already had — since the 2026-09-06 image bump, one the cargo shim's `--zero-stats` had started without the writer credential, ReadOnly | 2026-09-06 05Z-17Z: three writer builds, 0 objects written (`DBSIZE` 42 all day), host hit ratio ~0.0, console `check-clippy.compile` P50 47 s / `check-nextest.compile` 35 s (n = 93 each) | the writer starts its OWN server on port 4227 under the writer credential and refuses to build unless its log says `ReadWrite`; first build after the fix: `DBSIZE` 42 → 422, `cmdstat_set` +382 for ~383 misses; host hit ratio 0.77 within one tick; console job `hit_ratio` P50 0.62 (19 jobs); `check-clippy.compile` 24 s, `check-nextest.compile` 26 s (n = 2 each, first hour) | the cache's win, restored | `efqeip.4` comments 17:05Z-17:36Z; Honeycomb `nu68G64MnBY`, `n4ZaHRBsCms`, `wn9ePbVyGKU` |
| Populator guardrails (`osmzo4`) | an unbounded writer build on the job node | — | 6-CPU cap, `nice 19 / ionice 3`, admitted-job gate at 16 (skipped every tick from 06:30Z to 09:30Z today at 19-32 admitted; built at 10:00Z at 10 admitted), per-generation manifest | enabling; measured only as "no job regressed" | research/011; populate logs 2026-09-06 |
| Cache telemetry, host and pod (`gjqw2i`, `mlg5sf`) | no signal for any of the above | — | six `component:ci-cache` triggers live (dead-man, populate-failing, memory, stale generation, hit floor, negative tests); `cache.warm-copy` and `cache.job-summary` spans per job; the hit-floor trigger is what exposed the last section | enabling; counted, not measured | Honeycomb triggers list; research/003 |
| Negative tests on the timer (`tqpszl`, `hmv2bo`) | trust by assertion | the hardlink seed was writable from a job (case 1 red on every scheduled run 09-04T15:31Z..09-05T18:27Z) | all four cases green in-pod; two consecutive scheduled greens 06:38Z and 12:33Z on 2026-09-06 | criterion met | `hmv2bo`; `gh run list --workflow ci-cache-negative-tests.yml` |
| Factory parity, this repo's half (`npsqeu` / `efqeip.1`) | factory `build.cargo-*` spans without cache attributes | — | the sandbox shim attaches `build.cache.sccache.*` and `build.cache.registry.hit`; NOT yet visible in Honeycomb because the orchestrator's receiver allowlist admits only `build.cache.tier` / `hit` (`bd-ib-nslh` part 1, finding recorded 15:40Z) | not deliverable from this repo | research/011 item 6; `bd-ib-nslh` |

## Per job, per repository

Console (Rust), P50 seconds, from the console plan's tables (RAID-5 era → NVMe
window 2026-09-03T23:25Z..09-06T00:19Z, n = 20 per job): `check-fuzz` 398 → 316
(→ 224 with the target tier), `check-nextest` 256 → 64, `check-clippy` 184 → 52,
`check-deps` 188 → 37, `check-coverage` 243 → 87; no job regressed. The disk
accounts for the first ~82 s of the fuzz job's drop; the caches and the console
plan's levers for the rest.

livespec-dev-tooling (Python, uv tier only; no Rust), P50 seconds, before =
2026-08-22..09-01 (array, n = 52 per job, `CHiowBxYFCf`), after =
2026-09-04T17:30Z..09-06T16:20Z (NVMe + reflink seed + PyPI proxy, n = 150 per
job, `uR72oxZNQyS`):

| Job | BEFORE | AFTER | Δ |
|---|---|---|---|
| check-per-file-coverage | 189 | 138 | −27 % |
| check-python-batch | 95 | 54 | −43 % |
| check-types | 95 | 42 | −56 % |
| check-metadata-batch | 84 | 59 | −30 % |
| check-lint | 80 | 26 | −68 % |
| check-format | 76 | 26 | −66 % |
| check-coverage | 75 | 38 | −49 % |
| check-check-coverage-incremental | 68 | 27 | −60 % |
| check-red-green-replay | 65 | 27 | −58 % |
| check-fleet-conformance | 193 | 205 | +6 % (cross-repo network checks; not a cache consumer) |

The dev-tooling rows are disk + uv tier together; the tier's own share is the
`uv sync` 7.9 → 0.5 s and the absent PyPI round trip, the same on every job.

## What a job sees right now (composed 2026-09-06T16:40Z; amended 17:40Z)

- The uv tier, the registry tier and the target tier are delivering the numbers
  above (`yAN2QzKuNVG`: target rows `hit=true` after the 15:43Z hook converge;
  registry hit 100 %).
- **The compilation cache was not, and now is.** At composition the host
  hit-ratio gauge had read ~0.0 since 05:00Z (`mhNBWpBbass`); redis held 42 keys
  with 1,056 hits against 52,283 misses; the 16:00Z writer build reported 119
  misses and produced no puts (`INFO commandstats`: 56 SET calls all day).
  Console compile phases were back at cold: `build.check-nextest.compile`
  13-20 s → 34-56 s, `check-clippy.compile` 19 s → 44-60 s (`cpZ6faSgSLJ`).
  Filed as `livespec-dev-tooling-efqeip.4` (P1, host-routed).
- **Cause** (diagnosed 17:00Z from the writer's own debug log): since `c4b70c2c`
  moved the populator to the `python-rust-fuzz` image, whose cargo shim runs
  `sccache --zero-stats` before every measured cargo subcommand, the
  populator's `cargo fetch` started the pod's sccache server from the pod
  environment — endpoint present, writer credential absent — so that server
  failed its storage write check as the read-only `default` user and came up
  `ReadOnly`; the writer build five seconds later connected to it on the
  default port and sccache dropped every put with `Cannot write to read-only
  storage` at debug level while counting a plain miss. `efqeip.3`'s persistence
  was correct and idle: it preserves what the writer writes.
- **Fix and recovery** (PR #1890, `08ff6f37`, converged on the node 17:36Z with
  the mounted ConfigMap's hash verified against git): the writer build and the
  target build each start their own server on port 4227 under the writer
  credential and refuse to compile unless its log says `ReadWrite`. The first
  build behind it took redis from 42 to 422 objects (`cmdstat_set` +382 for
  ~383 misses); the host hit ratio read 0.77 at the 17:35Z tick
  (`n4ZaHRBsCms`); 19 console jobs 17:25-17:35Z carried
  `build.cache.sccache.hit_ratio` P50 0.62 (`nu68G64MnBY`); the first two
  warm samples of `check-clippy.compile` and `check-nextest.compile` read 24 s
  and 26 s against today's cold P50 of 47 s and 35 s (`wn9ePbVyGKU`; the
  research/011 warm references are 20.2 s and 13.1 s, so a fuller evening
  sample is still owed before the row is called fully restored). The hit-floor
  trigger `HfK9RB9tZYp` evaluates a trailing 4 h hourly and cannot clear before
  roughly 21:00Z.
- The shim's `--zero-stats` starting a server as a side effect is recorded on
  the work item as a finding for the shim's owner (orchestrator repository).
- Run-level wall clock today (`2x2NMKYyEq`: push P50 314 s, P90 1,306 s) is
  dominated by pool queueing under 31-47 concurrent runner pods, not by the
  caches; the per-job spans above are the clean signal (`6CqZuNjC8Nt`: console
  jobs P50 43 s, P90 199 s today).

## What this asks the maintainer to approve, and what it does not

Approve the tier rows as the plan's measured outcomes, with the console and
dev-tooling per-job tables as the per-repository view. Do NOT read this as
archive-ready: `efqeip.4` has landed and this note carries the recovered
hit-ratio numbers, but its compile-phase row rests on two samples and the
hit-floor trigger has not yet cleared; `bd-ib-nslh` part 1 gates the factory
row; the canary two-week gap (research/003 item 2) is reachable 2026-09-18.
