# 002 — First research pass: charter questions answered, corrections, and the combined B1+B2 design

Written 2026-09-04 in the maintainer's discussion-and-research session
(`/livespec-orchestrator-beads-fabro:plan ci-runner-cache-tiers`), against
the charter (`001-charter-ci-runner-cache-tiers.md`) and the ledger record on
epic `livespec-dev-tooling-efqeip` and child `livespec-dev-tooling-9mp`. Every
"verified" claim below names what was read; the pool host was OFFLINE for the
storage plan's array rebuild throughout (SSH timed out; `CI_RUNNER_LABELS`
unset on every fleet repo), so nothing here was measured on the host.

## Vocabulary this plan uses from here on

- **Warm cache** (the record's "lower"): a read-only directory tree on the CI
  host, filled only by the trusted populator CronJob, published as numbered
  generations behind a symlink, that every job pod mounts read-only and
  copies into its own scratch volume in `postStart`. Jobs read it; nothing a
  job does can write it. Tier 1 is the uv warm cache shipped 2026-08-23.
- **Tier 2** (the record's "local Actions cache"): a server on the host that
  speaks GitHub's `actions/cache` protocol, so workflows that KEEP
  `actions/cache` steps restore and save from local disk. Keyed, not
  transparent.
- **Option letters** (A1, A2, B1, B2, C1, C2) are the landscape enumeration in
  §"The full option landscape" below and are used by the handoff.

## Open question 1 — is tier 2's forked-runner cost real today?

**Yes as stated, and there is an unpatched path the record never considered.**

Verified against `actions/runner` at its 2026-08-31 head
(`0b0ac2fdabf53d69add6175026945b8afc8549a5`), file
`src/Runner.Worker/Handlers/NodeScriptActionHandler.cs`: the handler merges
workflow env first, then UNCONDITIONALLY sets `ACTIONS_RESULTS_URL` from the
job message's `SystemVssConnection.Data["ResultsServiceUrl"]` (and
`ACTIONS_CACHE_SERVICE_V2` from a job variable). There is no `.env`, config,
or flag that overrides it; `ContainerActionHandler.cs` does the same. The
action side (`actions/toolkit` `packages/cache/src/internal/config.ts`,
`getCacheServiceURL()`) reads ONLY that variable. The falcondev-oss
`github-actions-cache-server` docs (read 2026-09-04, v9.7.0) still say:
"the runner does not allow setting the ACTIONS_RESULTS_URL yourself, we need
to patch the runner binary/source", offering their forked runner image or a
hex patch plus `disableUpdate: true`.

**The unpatched path.** The ARC container hook
(`actions/runner-container-hooks`, `packages/k8s/src/k8s/utils.ts`
`writeRunScript`) executes each step inside the job container as
`exec KEY=VAL ... <entrypoint>` under `sh -l` — the runner's env is PREFIXED
onto the container's own env, not substituted for it. The runner never sets
`NODE_OPTIONS` (it only refuses workflows setting it through file commands:
`FileCommandManager.cs`/`ActionCommandManager.cs` block-lists). So the hook
pod template this repo already owns (`ci-runner/k3s/phase2/arc/hook-pod-template.yaml`)
can set `NODE_OPTIONS=--require=<path-in-a-read-only-hostPath>` on the `$job`
container, and a two-line preload can rewrite `process.env.ACTIONS_RESULTS_URL`
before `actions/cache` reads it. No forked runner, no self-update pinning,
fail-soft (a workflow that sets its own `NODE_OPTIONS` simply loses the
redirect and uses GitHub's cache). The server forwards everything it does not
handle (artifact uploads/downloads) to `DEFAULT_ACTIONS_RESULTS_URL`.
**Status: hypothesis until run on the host**; the proof is a routed job
whose `actions/cache` save lands on the local server.

**Trust tiering is free with the server.** `lib/scope.ts` verifies the
GitHub-signed `ACTIONS_RUNTIME_TOKEN` against the OIDC JWKS and enforces the
token's `ac` cache scopes (per-ref `Scope` + `Permission`) and `repository_id`.
That is GitHub's own read/write scoping — a PR job reads base-branch caches
and writes only its own ref scope — enforced server-side from a signed claim,
with no forgeable per-pod signal anywhere. ADR 0006 keeps signature
verification mandatory.

**Consequence.** Tier 2's price drops from "run a third-party runner fork in
ten scale sets" to "one pod-template env line, one preload file, one
namespace". It is STILL not transparent: every workflow must carry
`actions/cache` steps, and every fleet repository gates its uv cache step to
the hosted lane today (`LIVESPEC_CI_LANE == 'hosted'`). The scope event's
tier-2 deferral is re-priced but not reversed: the maintainer's requirement
is transparency, and the transparent tiers below do not need it.

## Open question 2 — does "transparent" also cover kept `actions/cache` steps?

Recorded decision 2026-09-04: the maintainer accepted **A1** (extend the warm
cache with the cargo registry) and asked for the fastest, most concurrent
shape that fabro can also exploit. The keyed tier was presented as a
complement that needs no runner fork and a one-line gate change per step;
the maintainer did not take it up. This plan therefore treats the keyed
tier as **not required** for the pool's contract: the pool MUST NOT depend
on a forked runner, MAY offer the preload redirect once proven, and owes
nothing to workflows that keep `actions/cache` steps beyond not breaking
them. The spec proposal filed by this pass states exactly that.

## Open question 3 — can a copied multi-GB `target/` pay for itself?

Not answerable without the host. What the pass established instead:

- The copy's SOURCE is the warm cache (storage plan: cold bulk, RAID-5
  array) and its DESTINATION is the pod work volume (hot bulk, NVMe once the
  retier lands; today stand-in LVs on the array). A 2.2 GB target tree
  (the July console measurement) copied by 32 concurrent slots is ~70 GB of
  writes per wave. The page cache will keep the read side resident (the host
  has 128 GB RAM), so the bound is destination write bandwidth.
- **Reflink removes the cost.** `cp --reflink` on XFS (formatted with
  `reflink=1`) or btrfs makes the copy metadata-only and copy-on-write. It
  requires the target warm cache and the pod work volumes to live on the
  SAME filesystem. The regenerated target tree is disposable, so placing it
  on the NVMe work-volume filesystem is sound — but that filesystem must be
  reflink-capable, which is a request to the storage plan
  (`livespec-g52yrb`), recorded in the handoff.
- Measurement order when the host returns, each against the console matrix
  wall clock and the `9mp` acceptance (≤ ~430 s): A1 alone; A1+B1; A1+B1+B2
  plain copy; A1+B1+B2 reflink. This isolates each win.

## Charter corrections (three)

| Charter claim | Record |
|---|---|
| The 10 GB hosted cache cap is unraisable | GitHub's current docs (read 2026-09-04): "By default, the limit is 10 GB per repository, but this limit can be increased by enterprise owners, organization owners, or repository administrators. Any usage beyond 10 GB is billed." The case for local caching is round-trip cost and eviction, not the cap. |
| `livespec-dev-tooling-9mp` was "OPEN, never started" | It was BUILT and PROVEN on the podman lane: PR #429 merged 2026-07-17 (throwaway fuse-overlayfs per warm subdir, forged-mount stripping, T10 isolation test), 30× per-job speedup (cold 91 s → warm 3 s), and the console matrix acceptance MET at 370 s on 2026-07-18 — with the finding that the other half of the 984 s was per-job Rust tool SOURCE-BUILDS, fixed by prebuilt taiki-e installs. The podman lane's deletion (2026-08-21) removed the mechanism; the design, measurements, and the tool-prebuild lesson stand. |
| Tier 2 costs a forked runner | True by env; the preload path above re-prices it, pending live proof. |

## The full option landscape

| Option | What it caches | Mechanism | Transparent | Trust | Fabro can use | Status |
|---|---|---|---|---|---|---|
| **A1** warm cargo registry + git | crate downloads | populator `cargo fetch` per routed lockfile; `postStart` copy; `CARGO_HOME` env | yes | read-only mount, one trusted writer | no (no mount) | ACCEPTED 2026-09-04; mechanical extension of tier 1 |
| A2 registry baked into sandbox image | crate downloads | image build | yes | image is trusted | yes (the factory plan's shape) | owned by `console-factory-build-cache`; worse than A1 for CI pods |
| **B1** sccache on the host | compiler invocations (dependency AND unchanged-workspace crates) | `RUSTC_WRAPPER=sccache`, `CARGO_INCREMENTAL=0`, redis backend in RAM over the node IP / docker bridge | yes (pod env) | pods hold a redis ACL user that can only read + `SCCACHE_REDIS_RW_MODE=READ_ONLY`; populator holds the writer user | **yes — the only compilation cache fabro can consume** | proposed |
| **B2** per-repo target warm cache | cargo's finished artifacts for the profiles the populator built | one more warm cache + `postStart` copy + `CARGO_TARGET_DIR` | yes | copy is pod-private | no | gated on Q3 measurement; reflink placement requested |
| C1 tier 2 via cache server | keyed tarballs (`actions/cache` semantics) | falcondev server + NODE_OPTIONS preload redirect | no | GitHub-signed token scopes, server-enforced | no | re-priced; not required; proof pending |
| C2 fork actions with S3 backend | keyed tarballs | `runs-on/cache` + MinIO | no (`uses:` + creds change) | rebuilt from bucket policy | no | rejected: worse than C1 on every axis |
| Already handled | image pulls; work-volume I/O | containerd node cache; storage plan NVMe retier | — | — | — | not this plan's |

## B1 versus B2, and why both

Neither touches linking, test execution, or a workspace crate the PR
changed. Cargo marks every workspace crate dirty on a fresh checkout (file
mtimes are newer than the copied dep-info), so B2 does not save workspace
compiles either; both remove DEPENDENCY compiles, which is the ten-jobs-
rebuild-the-same-graph cost `9mp` measured.

| | B1 sccache | B2 target copy |
|---|---|---|
| Dependency crates on the default-branch lockfile | hit, fetched per object from redis | reused in place, no fetch |
| Dependency crates only on the PR's lockfile | miss → compile (not written back) | miss → compile |
| Unchanged workspace crates | hit if the hash matches (stable ARC checkout path) | miss (mtime) |
| Profiles | any the populator built | exactly the populator's |
| Per-job startup cost | none | the copy (near-zero with reflink) |
| RAM | redis cap (~16 GB with LRU, room for PR variants) | page cache holds 2–3 GB per Rust repo |
| 32 concurrent jobs | thousands of small GETs, fine | 32 copies; plain = NVMe-write-bound, reflink = trivial |
| Survives host reboot | no (RAM); one populate restores | yes |
| Fabro | yes | no |

**Combined design (decided direction, pending measurement).** The populator
builds each routed Rust repository's default branch, per matrix profile
(dev, test, instrumented coverage), with sccache as the WRITER against
redis. That single build fills B1 and leaves the target tree that becomes
B2's next generation — one unit of work, two caches. Per job: `postStart`
copies registry (+ target) into the work volume; pod env sets `CARGO_HOME`,
`CARGO_TARGET_DIR`, `RUSTC_WRAPPER`, `CARGO_INCREMENTAL=0`, the redis
read-only endpoint and `SCCACHE_REDIS_RW_MODE=READ_ONLY`. A PR's own
compiles are never written back to either cache. Per fabro sandbox: baked
registry (factory plan) + the same sccache endpoint over `172.17.0.1`.

**Guardrails that must ship with it** (see 003 for the signals): the
populator gets a core cap and low CPU priority (it now compiles for minutes
on the node the jobs use); redis gets a fixed `maxmemory` with LRU, sized
against the churn-slot cap's job-memory budget; a fleet-wide kill switch in
the pod template turns every tier off without a deploy.

## Maintainer decisions recorded this session (2026-09-04)

1. A1 accepted.
2. Goal restated: as fast and as concurrent as possible; fabro must benefit
   as much as possible; the host has 128 GB RAM and can take more, so RAM-
   resident and page-cache-resident caches are the preferred medium.
3. Every important cache metric — whether the cache is used, what it saves,
   what it costs — MUST be emitted to Honeycomb (→ `003-cache-observability.md`).
4. Everything this plan does MUST be captured in the specification via
   propose-change (→ `SPECIFICATION/proposed_changes/ci-runner-cache-tiers.md`).
5. The stale `relocate-warm-cache-tier` worktree (podman-era, uncommitted,
   no PR) was removed at the maintainer's direction.

## Requests to other plans

- **Storage plan `poweredge-raid-array-maintenance` (`livespec-g52yrb`)**:
  format the NVMe work-volume filesystem reflink-capable (XFS `reflink=1` or
  btrfs) and grant this plan a directory on it for the disposable target
  warm cache, so the B2 copy can be `cp --reflink`. The 1 TiB `ci-cache` LV
  on the array still holds the registry/uv warm caches and redis persistence
  if any.
- **`console-factory-build-cache` (`livespec-dev-tooling-3u3gm2`)**: its
  sccache shape (item 2 in its charter) becomes a CONSUMER of the host
  service this plan runs; one service, two consumers. Its baked-registry
  shape (item 1) stands.
- **`otel-collector` repository**: a pod-reachable OTLP/HTTP endpoint on the
  CI host (today `127.0.0.1:4319` is loopback-only) — see 003.
