# PyPI files proxy — what the warm uv cache is built through

The host-served cache of `files.pythonhosted.org` that
`../warm-cache-populate.sh` builds every generation through (livespec plan
`ci-runner-pod-lifecycle-reliability`, item `livespec-41w4`, Carrier F2).
Where `../../crates-proxy/` fronts crates.io for every job, this proxy fronts
PyPI's file host for ONE consumer: the populator, which rebuilds the warm uv
cache from empty on every lock change and would otherwise re-download ~105 MB
from PyPI each time (48 rebuilds a day at the CronJob cadence is 5 GB/day
direct). Workflow pods never use it — their locks are untouched and they read
the seeded generation.

| Path | Role |
|---|---|
| `pypi-proxy.yaml` | Namespace `ci-warm-cache` (shared with the CronJob), the nginx config (one flat cache zone, verified upstream TLS, `limit_except GET HEAD`), the digest-pinned Deployment (`hostPath` store on the `ci-cache` tier, `readOnlyRootFilesystem`), and the ClusterIP Service on 8081. Its header carries the design: why a FILES proxy and not an index proxy, why the store is flat, the bound, the trust argument. |
| `../converge-warm-cache.sh` | Applies this manifest (with a config-hash stamp so an edit rolls the pod, and a bounded rollout wait) before the CronJob's objects. Run by the boot converge and by hand after editing the manifest. |
| `../warm-cache-populate.sh` | The reader: probes `/health`, rewrites the file-host prefix in its own clone of each routed `uv.lock` to `http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/packages/`, and counts the store's objects before and after each build for the hit ratio. |

## Why this one and not devpi or proxpi

`uv sync --frozen` downloads every locked distribution from the absolute
`files.pythonhosted.org` URL in `uv.lock`; the index URL (`UV_DEFAULT_INDEX`,
`UV_INDEX_URL`) serves only unlocked build dependencies. So an index proxy
caches nothing for the populator, and what works is a prefix swap in the
lock — which needs only `location /packages/` on a caching reverse proxy.
The comparison the choice rests on (measured 2026-09-04, uv 0.9.26) is in
`../README.md` "Proxy choice"; the short form:

| | devpi-server 6.20.3 | proxpi 1.3.0 | nginx 1.28.3 `proxy_cache` |
|---|---|---|---|
| file-cache bound | none | bytes, LFU | bytes (`max_size`), LRU, plus `inactive` ageing and `min_free` |
| idle / after one union | heaviest (sqlite + pyramid) | 60 MiB / 230 MiB | 5 MiB / 107 MiB |
| hit/miss surface | none | none exposed | `cache=HIT|MISS` per request in the log, `X-Cache-Status` header |
| cold union through it | — | 18.4 s (each file GET first lists the package) | 14.8 s; warm 13.5 s, 94/94 HIT |

## Operating it

- **Converge / re-apply**: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  ../converge-warm-cache.sh` on the host (it applies this manifest first).
  After editing the manifest, also re-run
  `../../reconstruct/install-converge-unit.sh` so the boot copy under
  `/usr/local/lib/ci-runner-k3s/warm-cache/pypi-proxy/` matches.
- **Is it live?** `kubectl -n ci-warm-cache get deploy,pods,svc pypi-proxy`.
  From a pod in the cluster (or `kubectl -n ci-warm-cache exec` into the
  populator's Job pod), `curl -s http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/health`
  returns `ok`. The populator's log opens with `pypi files proxy … healthy`
  or `WARN: … not answering /health; building DIRECT` — a missing proxy
  degrades a build to direct PyPI, never fails it.
- **Is a build using it?** `kubectl -n ci-warm-cache logs deploy/pypi-proxy`
  — one line per request with `cache=HIT|MISS|…`. A from-empty rebuild is
  ~100 lines; the first is all `MISS`, a lock-bump rebuild is mostly `HIT`.
  The populator's `last-run.json` carries the same fact as
  `proxy_hit_ratio`, and the host sweep emits it as
  `livespec.ci_warm.proxy_hit_ratio` (`../README.md` "Metrics").
- **Store**: `sudo ls /var/cache/ci-runner/pypi-proxy | wc -l` on the host
  is the object count (flat, one file per cached object). Bound 8 GB /
  30 days idle; the cache manager evicts least-recently-used entries.
- **Flush**: `sudo rm -rf /var/cache/ci-runner/pypi-proxy/*` on the host and
  restart the Deployment; the next rebuild re-fetches through it (one cold
  union, ~105 MB from PyPI).
- **Tampering is caught downstream, not here**: uv verifies every lock hash
  on what it receives, so a corrupted cached object fails the sync for that
  repository (`Failed to download <pkg>`), the repository is skipped
  fail-soft, and the next tick retries. Flush the store if that persists.
