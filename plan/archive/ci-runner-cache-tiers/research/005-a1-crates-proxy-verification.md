# 005 — A1 verified on the pool: a caching crates proxy serves cargo transparently; the implementation is nginx `proxy_cache`

Written 2026-09-04 in the planning session that took the 09:07Z handoff's next
action (child `livespec-dev-tooling-oiltq3`, spec commitment
`warm-cargo-registry`): verify on the pool that cargo's registry protocol can
be served by a caching crates proxy on the host transparently, survey the
candidate implementations, and record the choice. Everything below was run
LIVE on `poweredge-xubuntu` (k3s v1.36.2+k3s1, host up since ~09:20Z on the
rebuilt array, all nine repositories routed) in a scratch namespace
`ci-cache-proxy-experiment` that was deleted at the end; nothing was
converged and no GitOps file changed. The converge is the child's work.

## The verification, in one table

A throwaway nginx (`docker.io/library/nginx@sha256:72ba65eb…`) with two
`proxy_cache` zones in an `emptyDir`, a ClusterIP Service, and a Job in the
console's own CI image (`livespec-fabro-sandbox:python-rust-v1.40.1`, cargo
1.92.0) that cloned `livespec-console-beads-fabro` and ran `cargo fetch
--locked` four times with a fresh `CARGO_HOME` each time:

| Run | Proxy state | `CARGO_HOME` | Wall clock |
|---|---|---|---|
| 1 | cold (flushed, restarted) | fresh | 13.5 s |
| 2 | warm (every entry from run 1) | fresh | 3.9 s |
| 3 | warm | warm (run 2's) — nothing to fetch | 2.3 s |
| 4 | bypassed — direct to crates.io | fresh | 4.6 s |

And the facts the table does not show:

- **Transparent.** `Cargo.lock` was byte-identical after every run (cargo's
  source replacement keeps the lockfile's
  `registry+https://github.com/rust-lang/crates.io-index` source and only
  changes where bytes come from). All 163 locked packages (151 registry
  crates, the rest workspace members) resolved through the proxy; the proxy
  log shows 296 upstream misses on run 1 and 297 hits on run 2 (one index
  entry + one `.crate` per crate, plus `config.json`). Zero workflow changes.
- **Plain HTTP is accepted.** cargo 1.92 takes
  `registry = "sparse+http://…"` with no TLS and no warning, so the pod-side
  path needs no certificate. (Cargo's own test suite drives sparse registries
  over `http://127.0.0.1`; this confirms it on the shipped toolchain.)
- **The `dl` rewrite works.** The proxy answers `/index/config.json` with
  `{"dl":"http://<host-as-requested>/crates","api":"https://crates.io"}`,
  cargo appends `/{crate}/{version}/download`, and the proxy forwards that to
  `https://static.crates.io/crates/…`, which returns the tarball directly
  (200, no redirect — verified with curl from this session too). Using the
  request's own `Host` header in the rewrite means one config serves cluster
  DNS consumers and node-IP consumers alike.
- **No write surface.** A `PUT` against the proxy came back 401 — but from
  static.crates.io, passed through. The converged config MUST refuse
  non-`GET`/`HEAD` locally (`limit_except GET HEAD { deny all; }`) so the
  negative test (`livespec-dev-tooling-tqpszl`) asserts the proxy's own
  refusal, not the CDN's.
- **cargo speaks HTTP/1.1 to it**, so `http2` on the listener is not needed.
- **The console lockfile has NO git dependencies** (`grep 'source = "git+'`
  over the current `Cargo.lock`: none), and the console is the only routed
  repository with a `Cargo.lock` (checked all nine). The git-mirror half of
  A1 is therefore not needed today; the populator should WARN if a routed
  lockfile ever gains a `git+` source so the gap is visible before it costs
  a job.

## What the timings mean — and the finding that reorders the plan

The proxy's per-job wall-clock win is SMALL. Run 4 minus run 3 says a fresh
`CARGO_HOME` costs about 2.3 s over the floor when fetching straight from
crates.io on this host; run 2 minus run 3 says about 1.6 s through the warm
proxy. That is under a second saved per job, because this host reaches
Fastly's edge at ~80 ms per object and the dominant cost of a fresh
`CARGO_HOME` is not the download but extracting 243 MB of `registry/src`,
which happens identically in both cases. (The cold proxy, run 1, is SLOWER
than direct because nginx opened ~300 fresh TLS connections upstream; that
is a one-time cost per crate version and is what the populator's pre-warm
exists to absorb — see below.)

So A1's value on this pool is NOT wall clock. It is:

1. **Resilience.** Every routed job today makes ~300 unretried requests to
   two external CDNs per fresh `CARGO_HOME`; with `proxy_cache_use_stale`,
   anything the pool has ever fetched keeps serving through a crates.io or
   Fastly incident. The fleet's workflow comments name unretried fetches as
   their largest flake surface.
2. **Conformance.** v054's tiers clause requires a warm dependency cache for
   every package manager the routed lockfiles name; this is the cheapest
   realization that satisfies it, and it is host-served, so it adds ZERO
   per-start disk writes (the start-burst knee, ifwnqj Carrier F).
3. **One service, two consumers.** The same proxy is reachable from fabro
   sandboxes (see "Exposure" below), which gives the factory the same
   resilience for its cold builds without baking a registry into the image.

The load-bearing consequence: **the time `9mp` measured is in dependency
COMPILES, not downloads**, and the plan's ordering should say so. B1 (host
sccache, `livespec-dev-tooling-ddiszt`) is where the console matrix's
883 s → ≤430 s acceptance will or will not be met; A1 is a cheap
prerequisite that should ship first only because it is a one-pod change
with no trust surface, not because it moves the number. The handoff
records that ordering.

## Candidate survey

| Candidate | What it is | Verdict |
|---|---|---|
| **nginx `proxy_cache`** (two locations: `/index/` → `index.crates.io`, `/crates/` → `static.crates.io`; a static `config.json`) | A generic caching reverse proxy; ~50 lines of config | **CHOSEN.** Verified above. No image to build or maintain (official image, pinned by digest like every other pool image); cache lifetimes follow crates.io's own `cache-control: public,max-age=600` on index entries and immutable `.crate` files; `proxy_cache_use_stale` gives outage resilience for free; `$upstream_cache_status` in the access log and `stub_status` are the hit/miss and health signals the host-gauges child reads; `proxy_cache_lock` collapses a fan-out's simultaneous misses for the same crate into one upstream fetch (exactly the 13-jobs-start-at-once shape). |
| `crates-io-proxy` 0.2.4 (ravenexp, Apache-2.0, 39 stars, last push 2026-05-08, no published container image) | Purpose-built: caches sparse index entries with a 1 h TTL and `.crate` files forever; rewrites `config.json` itself | Does the same job well, but it is a small third-party binary the pool would have to build into its own image and track; its index TTL (3600 s) is 6× crates.io's own; no stale-on-error. Keep as the fallback if nginx ever proves insufficient. |
| Kellnr 6.6.0 | A full private registry (SQLite/Postgres, web UI, auth) with a crates.io caching mode | Far more surface than the requirement; a registry the pool would administer. Rejected. |
| Panamax 1.0.14 | A FULL crates.io + rustup mirror (hundreds of GB) | Wrong shape: the pool wants what its lockfiles name, not everything. Rejected. |
| `cargo-cacher` 1.2.5 | A crates.io proxy | Last release 2020-07; predates the sparse protocol. Rejected. |
| ktra / estuary / margo | Private registries for publishing | Not proxies. Rejected. |
| The copy shape (populator `cargo fetch` → warm tree → `postStart` copy → `CARGO_HOME`) | Research 002's original A1 | Rejected on the array by the start-burst evidence (research 004); stays the documented fallback only if the proxy is unworkable, which it is not. |

## How the pod is pointed at the proxy — the injection point

Cargo's `[source]` tables are **not settable from the environment**
(`source.<name>.replace-with` / `.registry`: "Environment: not supported",
cargo reference, config chapter); the replacement MUST be a config file.
Cargo probes `.cargo/config.toml` in the working directory and every
ancestor up to `/.cargo/config.toml`, then `$CARGO_HOME/config.toml` last.
Deeper paths win.

So the pool's injection point is **`/.cargo/config.toml` in the job
container**, written by the hook pod template's existing `postStart` (the
container's own writable layer; no new volume, no `CARGO_HOME` change, no
dependency on `HOME`). It applies to every cargo invocation in the job
whatever its working directory; a repository that ships its own
`[source.crates-io]` in its checked-in `.cargo/config.toml` overrides it
(the console's only sets `build.jobs` and `[env]`); and it is fail-soft:
if the write fails, or the proxy is down at resolve time, cargo goes to
crates.io as today. The same `postStart` that writes it is the kill switch's
seam (do not write the file when the switch is set). This is what the
experiment did, verbatim:

```toml
[source.crates-io]
replace-with = "pool"
[source.pool]
registry = "sparse+http://<proxy>:3080/index/"
```

Two things the container hook does that the child must know:

- The hook sets the job container's `HOME` to `/github/home`
  (`runner-container-hooks` `packages/k8s/src/k8s/utils.ts`), so a job's
  default `CARGO_HOME` is `/github/home/.cargo` on the work volume — fresh
  per job, which is why every job pays the 243 MB `registry/src` extraction.
  That extraction is the copy-shaped cost this tier does NOT remove; it is
  the same on hosted runners.
- The cargo shim baked into the sandbox image posts factory telemetry to
  `172.17.0.1:4318` with a 2.0 s timeout (`otel_cargo_phase.py`
  `_POST_TIMEOUT_S`), and from a pod that address is unreachable, so
  **every measured cargo invocation in every k3s-lane job pays ~2 s** waiting
  on it (the run-3 floor above is mostly this). That is the known
  pod-reachable-endpoint gap (`livespec-console-beads-fabro-2dnpq3`, child
  `mlg5sf`), now with a per-invocation price on it; the shim should also
  skip the POST outright when `build.env` resolves to `ci`.

## Exposure: cluster DNS for pods, a host port for fabro

- **Pods:** a ClusterIP Service in the proxy's namespace; workflow pods run
  `dnsPolicy: ClusterFirst`, there are no NetworkPolicies, and the AppArmor
  profile grants `network`, so
  `crates-proxy.<ns>.svc.cluster.local:3080` resolves and connects from any
  scale set's namespace — verified from the probe Job.
- **Fabro sandboxes** (docker on the host) cannot use a ClusterIP, and this
  k3s runs with `--disable servicelb`, so a `LoadBalancer` Service will NOT
  bind the node IP. The route is a `hostPort: 3080` on the proxy pod (CNI
  portmap binds it on the node), reachable from a docker container at the
  host's bridge address exactly as B1's redis endpoint will be. Verify from
  one dispatch; not done here.

## What the child converges (the shape, for `oiltq3`)

1. `ci-runner/k3s/phase2/crates-proxy/`: a Namespace, the nginx ConfigMap
   (the experiment's config plus `limit_except GET HEAD`, upstream TLS
   verification against the image's CA bundle, `proxy_cache_path` on a
   `hostPath` under `/var/cache/ci-runner/crates-proxy/` — the label-addressed
   `ci-cache` tier, so it moves by copy + relabel like the uv warm tree —
   `stub_status` on a loopback location, `hostPort: 3080`), a Deployment
   pinned by digest, a ClusterIP Service, and an installer/converge script in
   the warm-cache pattern (idempotent, called from the boot converge chain).
2. `hook-pod-template.yaml`: the `postStart` gains the `/.cargo/config.toml`
   write, gated on the kill switch, emitting the tier's `cache.warm-copy`
   span with `copy_bytes=0` once `mlg5sf`'s endpoint exists.
3. `warm-cache-populate.sh`: after the uv sync, run `cargo fetch --locked`
   for every routed repository with a `Cargo.lock`, with the SAME
   `/.cargo/config.toml` pointed at the proxy, into a throwaway `CARGO_HOME`,
   so the proxy is pre-warmed for every locked crate before any job asks
   (absorbing run 1's cold cost on the populator's timer, never on a job);
   warn on any `git+` source. The populator already runs in the
   `python-rust`-capable image.
4. Record the redis/proxy store placement and the trigger thresholds in
   this plan store per the child's acceptance.

Acceptance evidence the child can produce now: a routed console job whose
`cargo fetch` shows every crate served from the proxy (access log
`cache=HIT` for every index and crate request, zero requests to
crates.io from the job's own address), `Cargo.lock` unchanged, and a `PUT`
refused by the proxy itself.
