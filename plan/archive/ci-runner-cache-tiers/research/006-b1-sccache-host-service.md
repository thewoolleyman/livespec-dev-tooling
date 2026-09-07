# 006 — B1 converged: the host sccache, what it took to make jobs hit, and the redis ceiling

Written 2026-09-04 in the session that converged child
`livespec-dev-tooling-ddiszt` (spec commitment `sccache-host-service`) on the
pool, directly after A1 (research/005). Everything here was run live on
`poweredge-xubuntu`; the GitOps is `ci-runner/k3s/phase2/sccache/` plus the
hook template, the populator, and the boot converge chain (PR named in the
handoff). This note records the three decisions the child's acceptance asks
the plan store to hold — the memory ceiling derivation, the eviction policy,
and the measured hit behaviour — and the two defects found on the way that a
future reader would otherwise rediscover.

## The shape

| Piece | Realization |
|---|---|
| The cache | redis 8.8.2 (alpine, digest-pinned), RAM-only (`--save ""`, no AOF), `maxmemory 16gb`, `allkeys-lru`, non-root, read-only rootfs, in namespace `ci-sccache`; ClusterIP for pods, `hostPort 6379` for off-node consumers |
| Trust | An ACL file (rendered into a Secret by the converge): `default` user `on nopass -@all +@read +@connection +info` — every job pod connects as this; `sccache-writer` `+@read +@write +@keyspace +@connection` with a password generated on the host (`/etc/ci-runner/sccache-redis-writer.pass`, root 0600) and projected only into `ci-warm-cache`. Verified: `SET` as default → `NOPERM`; no `SCCACHE_REDIS_*` credential variable in any job pod. |
| The binary | sccache 0.17.0 (musl, sha256-pinned) at `/usr/local/lib/ci-runner-k3s/bin/sccache`, installed node-locally, mounted READ-ONLY into every job container and the populator at `/opt/ci-runner/bin`. The pool provides it: no routed repository bumps its `container:` pin. |
| The reader | The hook template's `postStart` appends `[build] rustc-wrapper = "/opt/ci-runner/bin/sccache"` + `incremental = false` to `/.cargo/config.toml` when the binary is mounted AND redis answers a 2 s TCP probe; `SCCACHE_REDIS_ENDPOINT` + `SCCACHE_REDIS_RW_MODE=READ_ONLY` as pod env. |
| The writer | The populator (`warm-cache-populate.sh`), per routed `Cargo.lock`: `cargo build --workspace --all-targets --all-features`, `cargo test … --no-run`, `cargo check --all-targets …` (clippy's dependency graph), `cargo build --release --workspace`, under `nice -n 19 ionice -c 3` at the repository's own `build.jobs` cap, as `sccache-writer`; skipped when the marker key `livespec:sccache:populated:<repo>` already equals `<sha>@<toolchain>`. |

## The memory ceiling, derived (acceptance item 4)

The spec's rule: the ceiling MUST be sized against the pool's concurrency
cap so cache memory and job memory never compete for the same headroom.

| Term | Value | Source |
|---|---|---|
| Allocatable RAM | 188.8 GiB | `kubectl get node -o jsonpath={.status.allocatable.memory}` (197 933 544 Ki) |
| Churn-slot cap `C` | 32 | `ci-runner.io/churn-slot` on the node (interim; 64 when the NVMe tier lands) |
| Per-job envelope | 4 GiB | the console's jobs at `build.jobs = 4` peak well under 2 GiB per rustc set; 4 GiB leaves room for `cargo llvm-cov` and nextest fan-out |
| Job budget | 128 GiB | `C × 4 GiB` |
| Host services | ~8 GiB | k3s + containerd + the collector + the crates proxy + host daemons, measured idle at ~4 GiB used |
| Page cache reserve | ~20 GiB | the warm uv tree (1.8 GiB), the crates proxy store, and the checkout/registry working sets of concurrent jobs |
| Remainder | ~32 GiB | |
| **redis `maxmemory`** | **16 GiB** | half the remainder; container limit 18 GiB for redis's own overhead |

At `C = 64` the job budget doubles to 256 GiB and the remainder is negative
on paper; the honest reading is that the 4 GiB envelope is conservative
(most fleet jobs are Python at well under 1 GiB) and the cap should be
re-derived from measured per-job RSS (the lifecycle plan's Carrier B
gauges) before `C` is raised, not that redis must shrink. Recorded so the
re-derivation has its inputs.

**Eviction policy:** `allkeys-lru`, sccache's documented fit: entries are
content-addressed and any of them is regenerable by the next populate; the
working set (one repository's default-branch graph across four profiles)
measured **381 keys** after the first fill, far below the ceiling; the
headroom exists for PR-lockfile variants — which jobs compile and do NOT
write — and a second Rust repository.

## Defect 1 — sccache is not fail-soft on its own

Measured with a scratch Job in the console's CI image: with
`SCCACHE_REDIS_ENDPOINT` pointing at a dead port, `cargo build` exits 101 —
sccache 0.17 refuses to start its server when the storage backend fails its
startup check, and cargo reports the wrapper's failure. So the tier's
fail-soft property is the postStart PROBE (no redis answer → no wrapper
stanza → cargo compiles as before), not sccache. A redis that dies after a
job's sccache server started counts subsequent failures as cache errors and
compiles locally (sccache's stats contract; not measured here). The hook
template's header says exactly this; the earlier draft's claim that sccache
"treats a backend error as a miss" was corrected.

## Defect 2 — every job missed the first fill: `CARGO_*` is in the key

The first writer build filled redis with 378 entries; the console's rerun
then showed job pods with 54 misses and 0 hits against it. sccache's Rust
hasher (`src/compiler/rust.rs`) hashes EVERY environment variable that
starts with `CARGO_` into the cache key, excluding only `CARGO_MAKEFLAGS`,
`CARGO_BUILD_JOBS`, `CARGO_REGISTRIES_*`, and `CARGO_ENCODED_RUSTFLAGS`. The
populator's env carried `CARGO_INCREMENTAL=0`, `CARGO_NET_RETRY=5`, and
`CARGO_TERM_COLOR=never`; no job carries any of them (the console's only
`CARGO_*` is `CARGO_BUILD_JOBS`, excluded). Fix: the populator sets NO
`CARGO_*` variable — `incremental = false` and `[net] retry = 5` moved into
its `/.cargo/config.toml` (cargo config is not hashed), and the CronJob's
`CARGO_NET_RETRY` env was removed. The same rule is written on the hook
template: it sets none either.

The second axis, absolute paths, was designed for from the start: the
populator builds at `/__w/<repo>/<repo>` with the image's `/root/.cargo` as
`CARGO_HOME` because that is where a job checks out and extracts (verified
`HOME=/root` in a live workflow pod), and cargo's `-C metadata` for a path
package hashes that path. `SCCACHE_BASEDIRS` exists but would not fix the
metadata hash, so it is not used.

## Measurements

The console's last green master run was rerun three times on the pool
during this work (its workflow untouched):

| Run | State of the pool | nextest | clippy | coverage | mutants | deps | fuzz | matrix wall clock |
|---|---|---|---|---|---|---|---|---|
| 1 (10:23Z, rerun of 6073a05d) | crates proxy only (research/005) | 1:42 | 1:34 | 1:52 | 1:30 | 1:04 | 14:13 | 14:19 |
| 2 (10:53Z, rerun of 6073a05d) | sccache wired, cache keyed away by Defect 2 (all misses), overlapping the populator's own writer build | 1:53 | 1:48 | 2:30 | 2:03 | 1:15 | — | — |
| **3 (10:59Z, rerun of 89662644)** | sccache wired, cache matching (per-pod stats mid-run: 123/184, 127/183, 70/115 hits, 0 errors) | **1:32** | **1:19** | **1:50** | **1:32** | **1:03** | **5:42** | **5:47** |

What the rows say. The miss overhead of a wrapped rustc is real but small
(10–40 s on ~2-minute jobs, with the populator's build competing for the
same cores in run 2). With the cache matching, every Rust job is faster
than both earlier runs — clippy by 15 s, nextest by 10 s against the
proxy-only run — and `check-fuzz`, the job that bounds the matrix, went
from 14:13 to 5:42 because its nightly `cargo fuzz build` no longer waits
behind the other jobs' dependency compiles for the host's cores. The
run-level number: **347 s wall clock against the ~430 s hosted warm-cache
baseline the spec names** — on ONE run, on a Thursday morning with only the
console's own sixteen jobs on the pool. The section's acceptance and the
archive evidence ask for this "from run spans, not a one-off run"; that is
the standing query the telemetry children (`gjqw2i`, `mlg5sf`) exist to
answer, and this row is the first data point, not the proof.

Note also how far the July numbers are from today's: `9mp` measured 883 s
on the podman lane; the proxy-only run here was 859 s for the matrix but
~2 minutes per Rust job. The matrix was already contention-bound on
`check-fuzz` rather than on any one job's dependency compiles, which is
why B1's per-job savings look modest while its matrix saving is large.

## The second consumer: the factory host, and the one thing its wiring must do

From this factory host (a different machine; it reaches the pool host only
over Tailscale, not the LAN), the console's own sandbox image with the
pool-provided sccache mounted at `/opt/ci-runner/bin` built the console
workspace against the pool's proxy and redis, read-only:

| Sandbox's registry URL | Hits / requests | Build |
|---|---|---|
| `sparse+http://100.78.140.72:3080/index/` (the Tailscale address) | 2 / 139 (1.4 %) | 79 s |
| `sparse+http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080/index/`, with `--add-host` aliases for both pool service names → the Tailscale address | **139 / 139 (100 %)** | 63 s |

The registry URL string is part of the path: cargo names the extraction
directory `registry/src/<url-host>-<hash>/`, and sccache hashes the absolute
source path, so a consumer that spells the proxy differently from the jobs
misses every registry crate. The factory's wiring (`livespec-dev-tooling-
npsqeu`, the cross-repo child) therefore MUST make the sandbox resolve
`crates-proxy.ci-crates-proxy.svc.cluster.local` and
`sccache-redis.ci-sccache.svc.cluster.local` to the pool host's Tailscale
address (docker `--add-host`, or the dispatcher's equivalent) and write the
same `/.cargo/config.toml` the hook template writes — not point at the IP.
With that, one host service has its two consumers.

## What is deliberately not in this child

- Coverage-instrumented artifacts (`cargo llvm-cov`, `-C instrument-coverage`
  RUSTFLAGS): a separate hash space; `cargo-llvm-cov` is installed per job by
  `taiki-e/install-action`, not baked, so the populator cannot fill it yet.
  Reconsider with the image bump that bakes it (the console's tool-prebuild
  lesson from `9mp`).
- `cargo +nightly fuzz build`: nightly toolchain, different compiler hash;
  not filled. `check-fuzz` is the matrix's floor for other reasons.
- The populator guardrails' admitted-job gate and the per-generation
  manifest (`osmzo4`); the negative tests on the isolation timer (`tqpszl`);
  the per-job `cache.job-summary` span and the factory shim's stats
  (`mlg5sf`, `npsqeu`). The factory host reaches the same redis at the pool
  host's Tailscale address on 6379 (verified reachable for the crates proxy
  on 3080 from the factory host; the LAN address is not routable from it).
