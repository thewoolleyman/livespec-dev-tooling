# 012 — B2, the per-repo target tier: measured on the NVMe, decided

The record `livespec-dev-tooling-c5byjh` asked for and `research/009` D5 left
open: measure A1+B1 against A1+B1+B2 on the console matrix once the CI work
volumes sit on the NVMe, ship B2 only if it beats sccache-only within the
start-burst budget, else record the decision to rely on sccache. Composed
2026-09-06 by the plan session; every number below cites its source.

## What changed since D5 (2026-09-04)

- The storage gate opened. `ci-workvols` is on the NVMe as **XFS with
  `reflink=1`** (`findmnt` on `/var/lib/rancher/k3s/storage`, `xfs_info`,
  read 2026-09-06T15:22Z), the format the reflink arm needs and the one
  `hmv2bo` closed the warm-seed trust regression on.
- The console plan `optimize-console-builds` (`livespec-console-beads-fabro`
  epic `gqmtwa`, child `ydlant`) **shipped the reflink arm of B2 for one key**
  — `asan-fuzz`, the console's `cargo +nightly fuzz build` tree — in this
  repository's `c4b70c2c` (PRs #1771/#1776) and the console's #982. The
  populator builds the tree at the in-pod path under the writer guardrails,
  the local-path provisioner reflink-seeds it into every work volume beside
  the uv seed, and the consuming job renames it into place and restores keyed
  source mtimes. `ci-runner/k3s/phase2/warm-cache/README.md` §"Target
  generations" is the design record.
- The same plan **dropped the dev/test key** — the general form of B2 — by
  measured headroom, not deferral: once sccache took `build.check-nextest.compile`
  to 20 s, a warmed dev/test `target/` could save at most ~20 s per job
  (console `research/009`, `research/010` "Go / no-go").

## The measurement

| What | Value | Source |
|---|---|---|
| Target generation, `asan-fuzz`, on the tier | 263,920,631 bytes, 328 files | `.target-manifest.json`, generations `20260906T130411Z` and `20260906T150318Z`, read on the node 2026-09-06T15:22Z |
| Populator rebuild of that generation (sccache warm, as the writer) | 9 s and 7 s | same manifests (`build_seconds`) |
| Per-start seed cost, uv + target together, on XFS reflink | 3.0 s wall for the provisioner's helper pod, pod overhead included (two samples 06:04–06:05Z); 13.3 s on the 191k-file uv generation before the from-empty rebuild shrank it to 12,192 files | recorded on `hmv2bo` 2026-09-06T06:06Z by the ci-runner-pod-lifecycle-reliability session |
| Hook `cache.warm-copy` row, `tier=target`, all ten routed repos, 06:00Z–15:24Z | n = 8,514; `build.cache.copy_ms` P50 42 ms, P95 347 ms, MAX 5,056 ms; `copy_method=reflink-seed` | Honeycomb `k1yS9R2Xp8Y` — this is the hook's OWN clock (the time from postStart to the row), not the seed: the seed ran at PVC provisioning, before the pod started |
| Console `build.check-fuzz.compile`, P50, before → after the warmed tree | 78 s → 4 s (−95 %; P95 5 s; MAX 52 s = the designed partial hit on a domain-crate PR), n = 21 since 07:55Z | console `research/011`, Honeycomb `hBdGTVBtYWv` |
| Console `check-fuzz` job wall, P50 / P95 / MAX, fuzz image + warmed tree | 316 s → 224 / 245 / 265 s (−29 % at P50; ~30 s above the ratified 180 s fuzz floor) | console `research/011`, Honeycomb `xaE3EmeUvD7` |
| The sccache-only residual on the profiles B2's dev/test key would serve (same medium, sccache warm) | `cargo clippy` 20.2 s, `cargo nextest` 13.1 s, `cargo test` 59.8 s | this plan's `research/011` §3 |
| Headroom a dev/test key could add over that residual | ≤ 20 s per job | console `research/009`, `research/010` |
| The plain byte-copy arm | not measured on purpose: on a reflink filesystem it is strictly dominated (research/005 measured 6.8 s and 2,153 MB written per job for a 1,388 MB tree by `cp -rp`; console `research/010` Result 1 measured hardlink/reflink ~15× cheaper than bytes) | `research/005`; console `research/010` |

Reading it: the compile shape sccache cannot reach (ASAN objects nothing else
in the fleet produces) is where a warmed `target/` pays — 74 s per console PR
at P50 for a 264 MB, 328-file reflink that costs the job nothing at start. The
shapes sccache DOES reach are within 20 s of what a warmed tree could give,
and a dev/test generation would be a multi-GB tree (console `research/010`:
752 MB for one dev profile on the vps) rebuilt on every default-branch commit
under the writer guardrails, for ≤ 20 s. That is not within the start-burst
budget's meaning of "beats sccache-only"; it is a second cache for the same
seconds.

## Decision (D5 resolved)

**Rely on sccache for every profile it reaches; ship the warmed `target/`
tier only for keys sccache cannot reach, reflink-seeded, one key at a time,
each with its own measured before/after.** Today that is the console's
`asan-fuzz` key, shipped and measured by the console plan. No dev/test key is
built. B2's plain byte-copy arm is retired: on the XFS reflink tier the seed
is a metadata operation, and the "per-start byte copy grows silently with the
cache" hazard (`README.md` §"Lesson") no longer has a byte copy to grow.

`c5byjh` closes as absorbed: its measurement is this note plus the console
plan's `research/010`–`011`; its decision is this section, recorded on the
plan epic; its "own `cache.warm-copy` span" criterion is the `target` row the
hook already emits — corrected in this PR, below.

## Two things the measurement turned up

**The target row reported a miss on every job.** The hook's postStart recorded
`tier=target` rows with `hit=false` and an empty `generation` on all 1,005
console jobs since 06:00Z (Honeycomb `cWJFZ8PtrNJ`, raw rows), while the
console's compile phase was plainly warm. Cause: `hook-pod-template.yaml` read
`$target_gen` in three places and assigned it nowhere (`uv_gen` had its `cat`;
`target_gen` never did), so `target_hit` could not be true. Fixed in this PR:
the hook reads `/__w/_warm/target/*/*/.generation`, the stamp the provisioner
writes per seeded `(repo, key)`. Converge: stage the merged tree on the node,
`install-converge-unit.sh`, then `converge-hook-pod-template.sh`; runner pods
created after the ConfigMap converge carry it (existing runner pods keep the
old template for their one job each).

**The copy-cost trigger cannot ride the hook row.** `research/003` planned
"P95 `build.cache.copy_ms` for `tier=target` over 24 h above 10,000 ms" and
`gjqw2i` did not provision it (the six live `component:ci-cache` triggers are
the dead-man, populate-failing, memory, stale-generation, hit-floor and
negative-tests ones). That was correct by accident: the target row's `copy_ms`
is the hook's own elapsed (42 ms P50 above), because the seed happens in the
provisioner before the pod exists. The seed cost lives in the lifecycle plan's
`start-seed-cost` sweep class and its gauges (`e6d8847c`, `livespec-44qx` /
`livespec-kgdlte`), where a growth alarm belongs; a threshold set from this
measurement would be ~10× the 3.0 s helper-pod time. No trigger is created
here, and none is owed by this plan.

## Queries

- `k1yS9R2Xp8Y` — `cache.warm-copy`, `tier=target`, by repo × method × hit,
  2026-09-06T06:00Z–15:24Z.
- `cWJFZ8PtrNJ` — the console's raw `target` rows since 13:00Z (empty
  generation, `hit=false`, one `canary`).
- `hBdGTVBtYWv`, `xaE3EmeUvD7` — the console plan's compile-phase and job-wall
  before/after (their `research/011`).
