# 003 — Cache observability: the Honeycomb emission contract

Maintainer direction 2026-09-04: "All of the important metrics about this
caching should be emitted to Honeycomb. Whether they are used, the timings
they give, etc." This note grounds that in the fleet's existing Honeycomb
practice and in Honeycomb's own guidance, and states the contract the spec
proposal carries. Nothing here is built; the host was offline.

## The failure this exists to prevent

Today's tier 1 has NO signal. The `postStart` copy is fail-soft by design: a
failed copy deletes its own output and exits 0, the job runs cold, and
nothing anywhere says so. The populator logs into its own Job output, which
nothing reads. The CI-runner heartbeat's own header records the precedent:
"from 2026-08-15 to 2026-08-23 this script exited 7 every five minutes for
eight days and nothing noticed ... A metric with no named reader is
indistinguishable from a metric that stopped being emitted." A cache is the
worst place for that shape, because a silently cold cache costs every job
while looking fine.

## Fleet practice this contract inherits (verified 2026-09-04)

| Practice | Where it lives | What this plan reuses |
|---|---|---|
| One Honeycomb environment for CI: `livespec`; CI runs in dataset `github-ci`, routed by `service.name=github-ci`, `service.namespace=livespec-family` | `livespec` spec §"CI telemetry export"; `.github/scripts/export-ci-telemetry.sh` (`ci.run` root + `ci.job.<name>` children with `repo`, `git.commit.sha`, `git.branch`, `ci.event`, `ci.job.queue_ms`) | same env, same dataset, same resource attributes; cache spans are joinable to `ci.job.*` by `repo` + `git.commit.sha` |
| Build-phase spans with a shared attribute scheme: `build.env` (`local`/`factory`/`ci`), `build.phase`, `repo`, `git.commit.sha`, `toolchain.version`; OPTIONAL `build.cache.tier` (`none`/`registry`/`target`) and `build.cache.hit` (bool) | console `plan/optimize-console-builds/telemetry-attribute-scheme.md`; `.github/scripts/emit-build-telemetry.sh`; this repo's `livespec_dev_tooling/otel_cargo_phase.py` for the factory | the optional cache attributes were DEFINED for exactly this plan and never populated; this contract extends them |
| Failure contract per environment: CI emitters fail-HARD (closed loop, a broken pipeline reddens the run); factory emitters best-effort NON-FATAL; local fail-soft | the same scheme document | pod-side hooks are best-effort (a hook must never fail a job); host-side emitters are fail-closed with a dead-man trigger |
| Host telemetry from the CI host: `ci-runner-heartbeat.sh` posts gauges every 5 min to the host collector at `127.0.0.1:4319` → `metrics` dataset, every row stamped `host.name`; dead-man triggers are UNGROUPED and FILTERED to one host, value triggers use MAX/MIN over a trailing window | `ci-runner/observability/`; `otel-collector` repo `config.ci-runner-host.yaml`; triggers `3EftfEEGm1k`, `4uMQfR6V2cr`, `byh8SSQRjFe` | the cache's host-side gauges ride the same timer-and-collector path and get the same two trigger shapes |
| Factory spans go through the dispatcher's receiver on `172.17.0.1:4318`, whose forwarded-attribute allowlist is FAIL-CLOSED: an unlisted attribute is silently dropped | `livespec-orchestrator-beads-fabro` plan `otel-receiver-attr-verification` (PR #777 lesson) | every new `build.cache.*` attribute MUST be allowlisted there before factory emission is trusted |
| Triggers carry a runbook, the emitter path, the receiver path, and the work-item in their description; tags `host:`, `kind:dead-man|value`, `service:` | the eleven `livespec` triggers | same |

Honeycomb's guidance (observability-fundamentals and the wide-event
attribute catalogue): one wide event per unit of work with cache state ON
that event, one boolean per cacheable operation (`cache.<thing>` = hit/miss)
so BubbleUp can split slow from fast by cache state, and never a metric where
an event carries the same fact with its context.

## Why the pod cannot just send to Honeycomb today

Two facts shape the realization. The CI host's collector listens on
LOOPBACK only (`127.0.0.1:4319`), which a workflow pod cannot reach. And no
ingest key may enter a job (the runner host requirements forbid injecting
fleet secrets into self-hosted jobs), so a pod cannot post to Honeycomb
directly. The factory solved the same problem with a keyless host receiver
routing by `service.name`. The CI host needs the same: a pod-reachable,
keyless OTLP/HTTP endpoint on the host (the cni bridge address, restricted to
the pod CIDR), realized in the `otel-collector` repository. Until it exists,
the pod-side spans below cannot ship; the host-side gauges can.

## The contract

### Per-job spans (dataset `github-ci`, best-effort, transparent)

Emitted by the pool, not by workflows, from the two lifecycle points the hook
pod template owns. Both carry `repo` (from the scale set), `git.commit.sha`,
`git.branch` and `ci.event` (from `/__w/_temp/_github_workflow/event.json`
on the shared work volume), `build.env=ci`, `host.name`, and
`build.cache.kill_switch` (bool).

- **`cache.warm-copy`** — one span per tier per job from `postStart`:
  `build.cache.tier` (`uv` | `registry` | `target`), `build.cache.hit`
  (generation present AND copied), `build.cache.generation` (the stamp),
  `build.cache.generation_age_s`, `build.cache.copy_ms`,
  `build.cache.copy_bytes`, `build.cache.copy_method` (`copy` | `reflink`),
  `build.cache.error` (string, empty on success).
- **`cache.job-summary`** — one span per job from `preStop`, after the
  steps: `build.cache.sccache.enabled`, `build.cache.sccache.hits`,
  `.misses`, `.errors`, `.hit_ratio` (from `sccache --show-stats
  --stats-format=json`, zeroed at pod start), `build.cache.sccache.backend`
  (`redis` | `none`), `build.cache.sccache.rw_mode` (`READ_ONLY` expected).

The console's existing per-job `build.check-*.compile|test` spans keep their
scheme; `build.cache.tier`/`hit` on them are widened to per-tier booleans
`build.cache.registry.hit`, `build.cache.target.hit`, and
`build.cache.sccache.hit_ratio`, populated from the same status file the
`preStop` hook reads. That keeps one query shape across CI and factory.

### Factory spans (dataset `github-ci`, best-effort)

The baked cargo shim's timer (`otel_cargo_phase.py`) gains the same
`build.cache.sccache.*` attributes (zero stats before cargo, read after) and
`build.cache.registry.hit` (the baked registry's presence). The receiver
allowlist in `livespec-orchestrator-beads-fabro` MUST admit `build.cache.*`
first, and the verification is the documented one: a dispatch, then
`get_span_details` shows the attributes populated.

### Host gauges (dataset `metrics`, fail-closed, every 5 min, `host.name` stamped)

Folded into the existing heartbeat timer path, `service.name=ci-runner-liveness`:

| Gauge | Source |
|---|---|
| `livespec.ci_cache.generation_age_s{tier}` | mtime of the current generation symlink target |
| `livespec.ci_cache.generation_bytes{tier}` | `du` of the current generation |
| `livespec.ci_cache.populate.duration_s`, `.repos_synced`, `.repos_failed`, `.toolchain_version` | the populator's per-generation manifest |
| `livespec.ci_cache.sccache.keyspace_hits`, `.keyspace_misses`, `.used_memory_bytes`, `.maxmemory_bytes`, `.evicted_keys` | `redis-cli INFO` |
| `livespec.ci_cache.kill_switch` | the pod template's current value |

### Canary: a live cold baseline, pool-owned

To prove "helping" as a query rather than a remembered benchmark, a fixed
fraction of jobs run COLD by construction: `postStart` deterministically
skips every tier for one job in N (default N=50, from the pod name's hash)
and tags it `build.cache.kill_switch=canary`; the `preStop` summary carries
the same tag. Warm-versus-cold P50 per repo and phase over the same host and
contention is then one `github-ci` query, and a closing gap means rot or a
copy that has outgrown its saving. The same env that drives the canary is
the operator's fleet-wide kill switch (`build.cache.kill_switch=operator`).

### Triggers (env `livespec`)

| Trigger | Shape | Fires when |
|---|---|---|
| Cache telemetry dead-man | ungrouped COUNT of `livespec.ci_cache.generation_age_s` filtered to the host, 20 min | the cache gauges stopped (timer, collector, or host) — folded into the heartbeat dead-man if the gauges ride the same POST |
| Warm cache stale | MAX generation age per tier > 2× the populate interval (60 min at 30-min populates) | the populator stopped publishing |
| Populate failing | MAX `repos_failed` > 0 for two consecutive windows | one routed repository has failed twice running |
| sccache hit floor | in `github-ci`, AVG `build.cache.sccache.hit_ratio` per repo over 24 h below 0.5, excluding canary and kill-switch jobs, evaluated hourly | the compilation cache rotted (toolchain bump without a re-populate, redis emptied) |
| Copy cost | P95 `build.cache.copy_ms` for `tier=target` over 24 h above 10 000 ms | the target copy is costing more than a dependency build saves; B2 needs reflink or removal |
| redis memory | MAX `used_memory_bytes` / `maxmemory_bytes` over 1 h above 0.95 | eviction pressure; the cap is too small for the PR-variant population |

### Negative tests (isolation suite, on the existing timer)

From inside a routed job: writing the warm-cache mount MUST fail; a redis
`SET` with the pod's credentials MUST be refused; a pod MUST NOT hold the
writer credentials. Results are green/red on the timer's existing report.

### Acceptance evidence the plan can archive on

1. The console matrix on the pool at or under the hosted warm baseline
   (~430 s), from `ci.run` spans, not a one-off run.
2. The canary gap (warm P50 < cold P50 per phase) holds for two consecutive
   weeks in `github-ci`.
3. The hit-floor trigger has never fired outside a toolchain bump.
4. The negative tests are green on the timer.
5. A second routed repository's `cache.warm-copy` spans show `hit=true` with
   zero workflow changes in that repository.
6. `get_span_details` on a factory `build.cargo-*` span shows
   `build.cache.sccache.*` populated (the allowlist verification).

### What is deliberately NOT emitted

Per-crate compile timings (cargo `--timings` output is large and the sccache
ratio answers the question), uv statistics (uv has none; the copy hit is the
signal), and anything carrying a credential or a cache key's contents.
