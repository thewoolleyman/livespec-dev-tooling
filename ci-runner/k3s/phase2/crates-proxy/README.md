# Crates proxy — the warm cargo dependency cache, host-served

The cargo half of the pool's warm dependency cache (`SPECIFICATION/
non-functional-requirements.md` §"Runner-pool build cache tiers", v054;
plan `ci-runner-cache-tiers`, child `livespec-dev-tooling-oiltq3`). Where the
uv tier (`../warm-cache/`) copies a lower into every pod, this tier copies
NOTHING: one nginx `proxy_cache` on the host fronts crates.io's sparse index
and crate CDN, and every job's cargo is pointed at it by a one-file source
replacement. Zero workflow changes in any routed repository.

| Path | Role |
|---|---|
| `crates-proxy.yaml` | Namespace `ci-crates-proxy`, the nginx config (two cache zones, verified upstream TLS, keepalive upstreams, `limit_except GET HEAD`, `stub_status`), the digest-pinned Deployment (`hostPath` store on the `ci-cache` tier, `hostPort 3080`), and the ClusterIP Service. Its header carries the design and the trust argument. |
| `converge-crates-proxy.sh` | Idempotent apply + bounded rollout wait. Run by the boot converge (`../reconstruct/converge-ci-stack.sh`) and by hand after editing the manifest. |
| `../arc/hook-pod-template.yaml` | The reader side: the job container's `postStart` probes the proxy and, if it answers, writes `/.cargo/config.toml` replacing `crates-io` with the proxy. Also carries the fleet-wide kill switch. |
| `../warm-cache/warm-cache-populate.sh` | The pre-warm: every routed repository with a `Cargo.lock` gets `cargo fetch --locked` run through the proxy on the populator's half-hourly timer, so the cache holds every locked crate before a job asks. |

## Why this shape

Verified live on the pool 2026-09-04 (plan research
`plan/ci-runner-cache-tiers/research/005-a1-crates-proxy-verification.md`):
cargo 1.92 accepts `registry = "sparse+http://…"` with no TLS, keeps
`Cargo.lock` byte-identical under source replacement, and resolved all 151
registry crates of the console lockfile through the proxy with the second
pass 297/297 hits.

The honest number: the per-job wall-clock saving is under one second on
this host (warm proxy + fresh `CARGO_HOME` 3.9 s vs direct crates.io 4.6 s),
because Fastly is ~80 ms away and a fresh `CARGO_HOME`'s dominant cost is
extracting ~250 MB of `registry/src`, identical either way. What the tier
buys is (1) resilience — a job's ~300 unretried CDN requests per fresh cargo
home become local hits, and `proxy_cache_use_stale` keeps serving through a
crates.io incident; (2) v054 conformance at zero per-start disk writes,
which the pool's start-burst knee forbids adding to; (3) one service for two
consumers — the fabro factory host can use the same hostPort. The console
matrix wall-clock acceptance rides on the compilation cache (B1), not here.

## Operating it

- **Converge / re-apply**: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  ./converge-crates-proxy.sh` on the host. After editing the manifest, also
  re-run `../reconstruct/install-converge-unit.sh` so the boot copy under
  `/usr/local/lib/ci-runner-k3s/crates-proxy/` matches.
- **Is it live?** `kubectl -n ci-crates-proxy get deploy,pods,svc`; from the
  host, `curl -s http://127.0.0.1:3080/index/config.json` must return a
  `dl` URL pointing back at the proxy, and `curl -s
  http://127.0.0.1:3080/nginx_status` shows request counts.
- **Host gauges**: `ci-runner/observability/ci-cache-gauges.sh` emits
  `livespec.ci_cache.registry.{up,requests_5m}` every 5 min from
  `stub_status`; the cache dead-man trigger in
  `ci-runner/observability/triggers/` covers the emitter.
- **Is a job using it?** `kubectl -n ci-crates-proxy logs deploy/crates-proxy`
  — one line per request with `cache=HIT|MISS|…` and the pod's address. A
  routed Rust job's fetch shows up as ~300 lines from one address, all
  `HIT` once the populator has warmed the lockfile.
- **Turn it off for every job without a deploy**: set the `$job` container's
  `CI_CACHE_KILL_SWITCH` env in `../arc/hook-pod-template.yaml` to
  `operator`, converge the ConfigMap (`../arc/converge-hook-pod-template.sh`),
  recycle idle runners. Every tier's `postStart` step is skipped; jobs run
  cold.
- **Flush**: `rm -rf /var/cache/ci-runner/crates-proxy/*` on the host and
  restart the Deployment; the next populate re-warms it.
- **A lockfile with git dependencies**: the proxy serves the registry only.
  The populator logs a `WARN` for any routed `Cargo.lock` carrying a `git+`
  source; those crates fetch from their forge as they do on hosted runners.
  No routed lockfile has one today.
- **Off-node consumers** (the fabro factory host): the node IP on port
  3080, same `config.toml` shape. `servicelb` is disabled on this k3s, so
  the hostPort is the mechanism, not a LoadBalancer Service.
