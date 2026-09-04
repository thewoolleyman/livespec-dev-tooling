# sccache — the shared Rust compilation cache, host-served

B1 of plan `ci-runner-cache-tiers` (`livespec-dev-tooling-ddiszt`; v054
§"Runner-pool build cache tiers"): the tier the console matrix's wall clock
actually rides on. Ten concurrent jobs each cold-rebuilding the same
dependency graph is what made the self-hosted lane 2x slower than hosted
(883 s vs 427 s; `livespec-dev-tooling-9mp`); a compilation cache keyed on
compiler inputs lets ONE populator build serve every job's dependency
compiles, adds no per-job start writes (a hit writes exactly the artifact a
compile would have), and — because it is a network endpoint, not a mount —
serves fabro sandboxes on the factory host through the same door.

| Path | Role |
|---|---|
| `sccache-redis.yaml` | Namespace `ci-sccache`, the RAM-only redis Deployment (`redis:8.8.2-alpine` by digest, `maxmemory 16gb` + `allkeys-lru`, no persistence, non-root, read-only rootfs, `hostPort 6379`), and the ClusterIP Service. Its header carries the trust argument and the memory-ceiling derivation. |
| `converge-sccache-redis.sh` | Idempotent (root): ensures the host-held writer credential (`/etc/ci-runner/sccache-redis-writer.pass`, generated on first run), renders the ACL into the `sccache-redis-acl` Secret, projects the credential into the populator's namespace as `sccache-redis-writer`, applies the manifest, bounded rollout wait. Run by the boot converge (step 8c) and by hand. |
| `install-sccache-binary.sh` | Node-local (root): the pinned, checksum-verified sccache binary at `/usr/local/lib/ci-runner-k3s/bin/sccache`. The pool PROVIDES the binary — mounted read-only into every job container and the populator at `/opt/ci-runner/bin` — so no routed repository bumps its `container:` pin to get the tier. Run by `install-node.sh` (7b) and after a version bump. |
| `../arc/hook-pod-template.yaml` | The reader side: `SCCACHE_REDIS_ENDPOINT` (the cluster Service, as the unauthenticated read-only user) and `SCCACHE_REDIS_RW_MODE=READ_ONLY` on the `$job` container; the `postStart` appends `[build] rustc-wrapper` + `incremental = false` to `/.cargo/config.toml` only when the binary is mounted and redis answers a TCP probe. |
| `../warm-cache/warm-cache-populate.sh` | The ONE writer: builds each routed Rust repository's default branch (four cargo invocations mirroring the matrix's compile shapes, `--all-features`) at the job's own checkout path and cargo home, under `nice`/`ionice` at the repository's `build.jobs` cap, as the `sccache-writer` user; gated by a marker key in redis so an unchanged branch and toolchain costs nothing. |

## Trust by construction

Server-side, in the ACL file: the `default` (unauthenticated) user gets
`-@all +@read +@connection` — a job can GET, never SET, never DEL, never
FLUSH; the `sccache-writer` user gets `@read @write @keyspace` and its
password exists in exactly two places, the host file (root, 0600) and the
`sccache-redis-writer` Secret in `ci-warm-cache`, which nothing in
`arc-runners` can mount. Jobs additionally run sccache read-only so they
never attempt a write, but the boundary is the server's `NOPERM`, not the
client's configuration; the scheduled routed job that asserts exactly that
every six hours is `../isolation/` (`.github/workflows/ci-cache-negative-tests.yml`). A job's own compilation output is never
written back; the populator builds only the default branch.

## Why redis in RAM, sized how

Regenerable data with a hot working set that every job reads concurrently:
the right medium is RAM, not the array the start-burst knee lives on. The
ceiling (16 GiB, `allkeys-lru`) is derived against the concurrency cap so
cache memory and job memory never compete: 188 GiB allocatable, minus a
4 GiB envelope for each of the 32 churn slots (128 GiB), minus ~8 GiB for
k3s/containerd/host services, minus ~20 GiB of page cache the warm trees and
the crates proxy's store want to stay resident in — leaves ~32 GiB, of which
redis takes half. The console's four-profile dependency graph measured far
below the ceiling on first populate (see the plan store, research/006); the
headroom is for PR-lockfile variants (which a job compiles and does NOT
write) and a second Rust repository. No persistence: one populate refills it
after a restart, because the populator's marker key lives in the cache it
describes and is gone with it.

## What hits and what cannot

- Dependency crates on the default-branch lockfile: hit (the bulk of the
  9mp cost). Dependencies only a PR's lockfile names: compiled in the job,
  not written back.
- Unchanged workspace crates: hit only when the job's checkout path matches
  the populator's (`/__w/<repo>/<repo>`) and the profile matches — sccache
  hashes absolute paths and cargo's `-C metadata` hashes a path package's
  path; the populator mirrors both.
- Never cacheable (sccache's own caveats): crates that invoke the linker
  (`bin`, `proc-macro`, `cdylib`), incremental compiles (disabled by the
  config stanza), and `clippy-driver`'s own workspace invocations (clippy's
  DEPENDENCIES are plain rustc and hit; the populator's `cargo check` pass
  fills that graph).
- Coverage-instrumented builds (`cargo llvm-cov`, `-C instrument-coverage`)
  are a different hash space the populator does not fill yet; `cargo-llvm-cov`
  is installed per job, not baked. Tracked in the plan store.

## Operating it

- **Converge / re-apply**: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml sudo
  ./converge-sccache-redis.sh`; after editing the manifest, also re-run
  `../reconstruct/install-converge-unit.sh`. Bump sccache: edit the version
  and sha256 in `install-sccache-binary.sh`, run it as root; job pods pick
  the new binary up on their next start (it is a hostPath mount).
- **Is it live?** `kubectl -n ci-sccache get deploy,pods,svc`; `kubectl -n
  ci-sccache exec deploy/sccache-redis -- redis-cli DBSIZE` and `INFO memory`.
  The marker: `redis-cli GET livespec:sccache:populated:<repo>` prints
  `<sha>@<toolchain>` of the last writer build.
- **Host gauges and triggers**: `ci-runner/observability/ci-cache-gauges.sh`
  emits `livespec.ci_cache.sccache.*` (up, keys, hits/misses, 5-minute hit
  ratio, memory ratio, evictions, populated repos) every 5 min; the
  `CI sccache hit floor` and `CI sccache redis memory pressure` triggers in
  `ci-runner/observability/triggers/` read them.
- **Is a job using it?** Until the pod-side `cache.job-summary` span
  (`livespec-dev-tooling-mlg5sf`) lands: exec into a running workflow pod and
  run `/opt/ci-runner/bin/sccache --show-stats`; or watch `redis-cli INFO
  stats` `keyspace_hits` climb during a console run.
- **Rotate the writer credential**: `rm /etc/ci-runner/sccache-redis-writer.pass`,
  re-converge (a new one is generated and projected; the pod rolls on the
  ACL hash), and the next populate rebuilds as the new user.
- **Flush**: `redis-cli FLUSHALL` from inside the pod (the default user
  cannot; use `redis-cli --user sccache-writer --pass "$(sudo cat
  /etc/ci-runner/sccache-redis-writer.pass)"` — FLUSHALL is `@dangerous`, so
  restart the Deployment instead: `kubectl -n ci-sccache rollout restart
  deploy/sccache-redis`; RAM-only means empty), then trigger a populate.
- **Turn it off for every job without a deploy**: the fleet-wide
  `CI_CACHE_KILL_SWITCH` in `../arc/hook-pod-template.yaml` (skips every
  tier), or scale the Deployment to 0 (the postStart probe then writes no
  wrapper stanza and jobs compile cold).
- **Off-node consumers** (the fabro factory host): the host's Tailscale
  address on port 6379, same read-only default user; the factory-side wiring
  is `livespec-dev-tooling-npsqeu`.
