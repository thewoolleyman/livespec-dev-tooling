# 004 — Cross-plan alignment with `ci-runner-pod-lifecycle-reliability` and `poweredge-raid-array-maintenance`

Written 2026-09-04 at the maintainer's direction ("read the updated plans and
status ... they should not conflict"), after reading both livespec-repo plans
at their 2026-09-04 state: epic `livespec-ifwnqj` (its 2026-09-04 scope
amendment, Carriers A–G, the four children filed 08:31Z) and epic
`livespec-g52yrb` (handoffs 06:35Z, 07:30Z, 07:53Z, 08:28Z; research
`nvme-pex8747-gen3-link-fault.md`), plus lifecycle research 003 and 004. This
note records every conflict found and how this plan resolved it. Research 002
and 003 stand except where this note says otherwise.

## Facts that changed the plan

| Fact (source) | Effect on this plan |
|---|---|
| **Media-neutral tier identity is adopted**: three ext4 filesystems addressed by LABEL (`ci-cache`, `ci-containerd`, `ci-workvols`), byte-identical on any medium; a tier moves by data copy + relabel; fstab never changes (g52yrb 08:28Z; ifwnqj Carrier A, child `livespec-el5y`; dev-tooling `a222494c` landed the git side). | ext4 has no reflink. XFS cannot even carry the label names (12-byte limit). **The reflink request in research/002 is WITHDRAWN.** The target-directory tier (B2) is a byte copy or nothing. |
| **The array's knee is a START-BURST knee** (ifwnqj 2026-09-02 evidence; Carrier F, child `livespec-381e`): every job start writes the runner externals copy (~125 MB, ~10k files), the warm-cache postStart copy, and the checkout; ~6 simultaneous starts drive `sda` to 100 %; a fan-out starts ~13 jobs per repo within seconds; the churn-slot cap bounds concurrency, not start rate. Under load the array serves a flat ~1,000 write req/s at ~95 MB/s with ~100 queued and ~100 ms await (lifecycle research 004, `sar` and Honeycomb agreeing). | **Any tier realized as a per-start copy makes the knee worse.** A 300 MB cargo-registry copy per start is the same class of write as the uv copy Carrier F already targets; a 2.2 GB target copy × 13-job fan-out is ~30 GB of allocation-heavy writes into a device serving 95 MB/s. So: the registry tier is realized host-SERVED (reads over the node network from host RAM or page cache; the only disk writes are the crate extractions a job does anyway), and B2 is deferred until `ci-workvols` is on the NVMe and the copy is measured there. sccache (B1) adds no start writes: a hit writes the same artifact a compile would have written. |
| **tmpfs work volumes were REJECTED by the maintainer 2026-09-01** ("it will just take up RAM headroom"; `livespec-trxcf7` closed). | Not a conflict, but easy to misread: this plan's RAM use is a READ-ONLY, regenerable cache (redis for sccache; the page cache for warm trees), not RAM-backed work volumes. Research 002 says so explicitly; this note repeats it so the lifecycle session does not read the cache plan as a reversal. |
| **Routing**: g52yrb 07:30Z restored the seven pool repos and said livespec + console "stay hosted until the NVMe tier lands"; ifwnqj's amendment says the console/livespec routing is "decided from Carrier B's read by the maintainer". | The maintainer decided it on 2026-09-04 (this session): all nine back on the array now. Recorded as a cross-link comment on both epics. The soak read (g52yrb's next action) now includes the console's Rust matrix, the heaviest start-burst source. |
| **Churn-slot cap C stays at 32** until Carrier B's soak data shows the knee (ifwnqj amendment; the 'restore to 64' condition retired). | Research 002/003's concurrency figures assumed 32. Consistent. |
| **The k3s lane's build telemetry never reaches Honeycomb** (lifecycle research 004 §6; console item `livespec-console-beads-fabro-2dnpq3`): the cargo shim's default endpoint `172.17.0.1:4318` is unreachable from pods, and the host collector listens on `127.0.0.1:4319` only. | Identical to research 003's finding. One `otel-collector` change (a pod-reachable keyless OTLP/HTTP listener) closes both; the cache plan's `cache.warm-copy` span (copy_ms, copy_bytes per tier) is exactly the per-start measurement Carrier F item 1 asks for. Cross-linked. |
| **Carrier B (`livespec-vwzv`)** extends the heartbeat path with lifecycle and capacity gauges. | The cache plan's `livespec.ci_cache.*` gauges ride the same path and timer; no second emitter. |
| **Populator builds are churn too.** | Amended guardrail: the populator's Rust builds run at low CPU AND I/O priority and MUST NOT start while the pool's admitted-job count is above a threshold (it is a 30-minute CronJob; skipping a tick is free). |
| **RAM is 188 GB, not 128** (verified live; a further upgrade is on g52yrb's follow-ups ~Sep 10). | More headroom for the redis cap; no design change. |

## Amended tier realizations

| Tier | Before (research 002) | After this note |
|---|---|---|
| A1 cargo registry + git | populator `cargo fetch` → warm tree → postStart copy → `CARGO_HOME` | **host-served**: a caching crates.io proxy on the host (sparse index + `.crate` downloads cached on `ci-cache`, hot in page cache), with cargo pointed at it through a `config.toml` in a tiny pod-provided `CARGO_HOME` (`[source.crates-io] replace-with` → the host mirror). Zero bytes copied at start; a job's `registry/src` extraction happens as it does on hosted runners. Git dependencies: the same proxy or a populator-maintained bare-mirror tree bind-mounted read-only (cargo can read a git DB it does not write). The copy shape stays as the fallback if the proxy proves unworkable, and MUST carry its measured per-start bytes. |
| B1 sccache | unchanged | unchanged; explicitly zero start writes |
| B2 target warm cache | copy, reflink preferred | **deferred until `ci-workvols` is on the NVMe**; byte copy measured there; rejected on the array |
| Populator | core cap + low CPU priority | + low I/O priority + admitted-job threshold gate |

The maintainer's A1 acceptance (2026-09-04) named the GOAL — warm cargo
dependencies, transparent, fleet-wide — not the copy mechanism; the host-served
realization meets the goal and Carrier F. Whether cargo's registry protocol
can be proxied transparently enough (sparse index over HTTP, `dl` URL
rewriting, auth-free) is the first thing the child `warm-cargo-registry`
verifies; candidate implementations are surveyed there, not here.

## What this plan owes the other two, and what it asks

- **To ifwnqj (Carrier F):** the per-start copy measurement from the
  `cache.warm-copy` span once the pod-reachable endpoint exists; no new
  per-start copy from this plan.
- **To g52yrb:** nothing beyond the existing 1 TiB `ci-cache` LV, which now
  also holds the registry proxy's store and redis persistence if any. The
  reflink ask is withdrawn.
- **From otel-collector:** the pod-reachable keyless OTLP/HTTP listener
  (shared need with `2dnpq3` and Carrier B).

## Spec proposal amendments made in the same change

`SPECIFICATION/proposed_changes/ci-runner-cache-tiers.md` was amended before
revision: the tiers clause now prefers host-served realizations and forbids an
unmeasured per-start copy; the target-directory tier MUST NOT ship while the
work-volume tier is on the array; the populator guardrail adds I/O priority and
the admitted-job gate; the storage-placement clause is rewritten around the
label-addressed `ci-cache` role and forbids any dependence on reflink or
copy-on-write; the first scenario no longer assumes a copy; the
`target-warm-cache-measured` commitment is re-scoped to the NVMe.
