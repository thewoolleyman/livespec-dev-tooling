# 007 — The host-side cache telemetry: what is emitted, the trigger ids, and what is still unmeasurable

Written 2026-09-04 in the session that converged child
`livespec-dev-tooling-gjqw2i` (spec commitment `cache-host-gauges`),
directly after A1 (research/005) and B1 (research/006). v054's rule is the
reason this child came before the guardrails and the negative tests: "A
tier with no emitted signal MUST NOT be considered shipped." With this
note, A1 and B1 are shipped in the spec's sense.

## The emitter

`ci-runner/observability/ci-cache-gauges.sh`, on `ci-cache-gauges.timer`
(every 5 min, one minute offset from the heartbeat), one OTLP/HTTP POST to
the host collector's loopback receiver → the `livespec` environment's
`metrics` dataset, `service.name=ci-runner-liveness`, `host.name` stamped.
DynamicUser with a `StateDirectory` for the previous tick's counters. Every
read is unprivileged: the warm root, the crates proxy's `stub_status` and
redis over their loopback hostPorts (redis's unauthenticated user carries
`+info +@read` for this), the populator's manifest, and the hook template's
boot-durable copy for the kill switch.

| Gauge (`livespec.ci_cache.`) | Source | Emitted when |
|---|---|---|
| `kill_switch` | the hook template's `CI_CACHE_KILL_SWITCH` | always — the dead-man's column |
| `generation_age_s`, `generation_bytes` `{tier=uv}` | the `warm/uv` symlink target | the warm root has a generation |
| `registry.up`, `registry.requests_total`, `registry.requests_5m` | the proxy's `stub_status` | `up` always; the counters when it answered |
| `sccache.up`, `.keys`, `.keyspace_hits`, `.keyspace_misses`, `.used_memory_bytes`, `.maxmemory_bytes`, `.evicted_keys`, `.memory_ratio`, `.populated_repos` | redis `INFO`, `DBSIZE`, `SCAN` of the marker keys | `up` always; the rest when it answered |
| `sccache.hit_ratio_5m` | hits/(hits+misses) over the previous tick | ONLY when there was traffic — an idle host is not a cold cache |
| `populate.age_s {toolchain}`, `.duration_s`, `.repos_synced`, `.repos_failed`, `.cargo_warmed`, `.sccache_built` | `warm/populate-manifest.json`, written by the populator at publish (added in this child; the per-generation manifest the guardrails clause asks for) | the manifest parses |

Fail-closed per source: an unreadable source omits its gauges and reddens
the unit; a source that answers "down" emits `up=0` and omits the rest
rather than false zeros. First emission verified in Honeycomb 2026-09-04
11:2xZ: `kill_switch` datapoints arriving, `generation_age_s{tier=uv}` 59 s
after a populate, 381 keys, memory ratio 0.014, one populated repository,
and after one sandbox build against the pool, `hit_ratio_5m` 0.979 with
316 proxy requests in the tick.

**Dropped during verification:** a `registry.store_bytes` gauge. nginx
keeps its cache tree mode 0700, so the unprivileged emitter's `du` read
0 — a false zero, exactly what the fail-closed rule forbids — and running
the emitter as root for one number is the wrong trade. Store size is a
`du` as root when someone asks; the memory-pressure signal that matters
is redis's, which is emitted.

## The triggers (env `livespec`, dataset `metrics`)

Created through the API by `ci-runner/observability/triggers/apply-triggers.sh`
from the committed definitions, idempotent by name, in the fleet's shape
(ungrouped, filtered to one host, runbook + emitter + receiver + work item
in the description, tags `host`/`service`/`kind`/`component`).

| Trigger | id | Shape |
|---|---|---|
| CI cache gauges dead-man | `FfauzAW8154` | `COUNT_DATAPOINTS(kill_switch) < 1` over 20 min, every 10 min |
| CI warm cache stale | `vnW13mLVzen` | `MAX(generation_age_s{tier=uv}) > 3600` over 10 min, every 5 min |
| CI cache populate failing | `7i3YLL4gQjX` | `MIN(populate.repos_failed) > 0` over 60 min, every 30 min — two consecutive populates |
| CI sccache hit floor | `HfK9RB9tZYp` | `AVG(sccache.hit_ratio_5m) < 0.5` over 4 h, hourly |
| CI sccache redis memory pressure | `4saxtcKLoEx` | `MAX(sccache.memory_ratio) > 0.95` over 60 min, every 15 min |

Three things Honeycomb taught during creation, written into the apply
script and the definitions so nobody relearns them: a trigger window is at
most 14 400 s (the hit floor is "over 4 h", not the 24 h research/003
sketched); a trigger cannot reference a column no datapoint has created
yet (the hit-ratio gauge, emitted only under traffic, needed one real tick
before its trigger could exist); and descriptions have a length cap.

## What research/003 asked for that is NOT here, and why

- **The copy-cost trigger** (`P95 build.cache.copy_ms{tier=target} > 10 000 ms`):
  its data source is the per-job `cache.warm-copy` span (`mlg5sf`) for a
  tier that does not ship until the NVMe (`c5byjh`). No column, no trigger.
- **The per-repository, canary-excluding hit floor** from job spans: also
  `mlg5sf`'s. The host-side floor above is the standing substitute.
- **Populate `toolchain_version` as a gauge**: it is a string; it rides as an
  attribute on `populate.age_s`.

## Evidence this child contributes to the archive list

Item 3 of research/003's acceptance evidence ("the hit-floor trigger has
never fired outside a toolchain bump") is now a query on a trigger that
exists; item 1 (the matrix number from run spans) still needs the per-job
spans. The one run recorded in research/006 (347 s) stands as the first
data point.
