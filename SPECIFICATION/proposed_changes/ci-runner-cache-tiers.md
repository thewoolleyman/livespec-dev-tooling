---
topic: ci-runner-cache-tiers
author: claude-fable-5-1
created_at: 2026-09-04T01:17:36Z
spec_commitments:
  impl_followups:
    - id_hint: warm-cargo-registry
      description: |
        Extend the warm-cache populator with a cargo registry + git warm cache per routed Rust repository's lockfile, add the copy and CARGO_HOME to the hook pod template's postStart, and emit the cache.warm-copy span for the new tier.
    - id_hint: sccache-host-service
      description: |
        Run a redis-backed sccache backend on the CI host with a read-only ACL user for pods and a writer user for the populator; set RUSTC_WRAPPER, CARGO_INCREMENTAL=0, and the read-only endpoint in the hook pod template; populate it from the populator's per-profile builds; expose the same endpoint to fabro sandboxes over the docker bridge.
    - id_hint: target-warm-cache-measured
      description: |
        Measure the per-repository target warm cache (a multi-GB per-job copy) against the sccache-only shape on the console matrix ONLY once the pod work-volume tier is on media whose measured start-burst headroom absorbs it (the NVMe); on the array it is rejected by the start-burst evidence (livespec-381e). Record the decision to ship it or to rely on sccache.
    - id_hint: cache-pod-spans
      description: |
        Emit the cache.warm-copy and cache.job-summary spans from the hook pod template's postStart and preStop hooks to the github-ci dataset through a pod-reachable keyless OTLP endpoint on the host, including the canary sampling and kill-switch tagging.
    - id_hint: cache-host-gauges
      description: |
        Add the livespec.ci_cache.* gauges to the CI host's heartbeat timer path, the populator's per-generation manifest they read from, and the Honeycomb triggers (stale generation, populate failing, hit floor, copy cost, redis memory) with runbooks.
    - id_hint: cache-negative-tests
      description: |
        Extend the pool's isolation suite with the three cache negative tests (warm mount unwritable from a job, redis SET refused with pod credentials, no writer credential in a pod) on the existing timer.
    - id_hint: factory-sccache-stats
      description: |
        Attach build.cache.sccache.* and build.cache.registry.hit to the fabro sandbox cargo shim's spans, and have the dispatcher receiver allowlist admit build.cache.* (cross-repo: livespec-orchestrator-beads-fabro).
    - id_hint: populator-resource-guardrails
      description: |
        Give the warm-cache populator a core cap and low CPU priority for its Rust builds, and size redis maxmemory with an LRU policy against the churn-slot cap's job-memory budget.
    - id_hint: keyed-tier-preload-proof
      description: |
        Prove or refute on the host that a NODE_OPTIONS preload set by the hook pod template redirects actions/cache to a local cache server without a forked runner; record the result and, if proven, the offered-not-required keyed tier's shape.
---

## Proposal: Runner-pool build cache tiers are transparent, trust-tiered by construction, and fleet-wide

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a section "Runner-pool build cache tiers" to non-functional-requirements.md, beside "Adaptive JIT runner admission budget", stating what the self-hosted runner pool this repository provisions under ci-runner/k3s/ owes every routed repository in the way of build caching: transparency (no per-repository workflow change), locality (host disk or host RAM), trust tiering enforced by construction rather than by any per-job signal, one trusted writer, a fleet-wide kill switch, resource guardrails on the populator, the storage-placement property for the large tier, and the posture toward a keyed actions/cache emulation. Rust is the primary consumer.

### Motivation

Plan ci-runner-cache-tiers (epic livespec-dev-tooling-efqeip, research notes 001-003). The maintainer's requirements, stated 2026-09-04: caching applies to every repository routed to the pool, is transparent to each repository's Actions configuration, lives on local disk or RAM on the host, and Rust builds are the primary consumer; the shape must be as fast and concurrent as possible and usable by the fabro factory. Measured basis: the console matrix cold on the pool was 883 s against 427 s hosted-with-cache because ten concurrent jobs each rebuild the same dependency graph (livespec-dev-tooling-9mp); the July podman-lane realization proved a 30x per-job speedup and met the 370 s acceptance together with prebuilt Rust tooling; tier 1 (uv) on the k3s lane measured 7.9 s to 0.5 s with zero workflow changes. The trust constraint is inherited from the fleet host requirements (livespec non-functional-requirements §"Self-hosted CI runner host requirements") and from the July design investigation: no signal a pod can see at creation time says whether the job is trusted, so the design must need no such decision. This section states pool infrastructure this repository owns; the fleet-level host requirements in the livespec repository are unchanged and are not targeted here.

### Proposed Changes

Insert a new top-level section `## Runner-pool build cache tiers` immediately after `## Adaptive JIT runner admission budget`, with the following normative content.

**Scope.** The self-hosted runner pool provisioned from `ci-runner/k3s/` MUST offer build caching to every repository routed to it as POOL infrastructure. A routed repository MUST receive the caching with zero changes to its own workflow files, and a routed repository MUST NOT be required to carry `actions/cache` steps, cache keys, or cache-restore logic to benefit. A cache MUST live on the host's local disk or in the host's RAM; a cache that requires a network round trip off the host does not satisfy this section.

**Tiers.** The pool MUST provide a warm dependency cache for every package manager the routed repositories' lockfiles name (today uv and cargo, the latter covering the crate registry and git dependencies), realized either as a host-SERVED cache a job reads over the node network (a caching registry proxy or a RAM-resident store), or as a read-only host-side tree that every job pod mounts read-only and copies into its own ephemeral work volume before the first step runs. Because per-job start writes are the pool's measured disk knee (about six simultaneous job starts saturate the array), a host-served realization MUST be preferred over a per-start copy wherever the package manager can consume one, and a copied realization MUST NOT ship without its per-start bytes measured against the pool's start-burst budget. The pool MUST provide a shared compilation cache for Rust (sccache or an equivalent compiler-invocation cache) served from the host and reachable from every job pod and from every fabro factory sandbox, so that one host service has two consumers. The pool MAY provide a per-repository warm target-directory cache through the copy mechanism, but MUST NOT ship it while the pod work-volume tier lives on the array, and MUST decide whether to ship it on faster media by measurement against the sccache-only shape on the routed Rust repository's full matrix, recording the decision in the plan store.

**Trust by construction.** A job MUST NOT be able to write any shared cache: the warm trees are mounted read-only and a job works on its private copy; the compilation cache MUST be reachable from a job only through a credential or endpoint that permits reads and refuses writes, enforced server-side, and a job's own compilation output MUST NOT be written back to any shared cache. The pool MUST NOT derive a per-job trust decision from any value a workflow can influence (workflow env, job labels, container env, the runner's process env). Exactly one trusted writer, the populator, MAY write the shared caches, and it MUST build only the default branch of each routed repository. Per-repository namespacing MUST prevent an object populated for one repository from being served to another, except for the compilation cache, whose entries are content-addressed and MAY be shared across repositories.

**Fail-soft and kill switch.** A cache fault MUST NOT fail a job: a missing, stale, or unreadable cache degrades that job to cold behavior. The pool MUST carry one fleet-wide kill switch, settable without a deploy of any routed repository, that disables every tier for every job; the same switch MUST drive the canary sampling required by §"Runner-pool cache telemetry".

**Populator guardrails.** The populator's Rust builds run on the node the jobs use; the populator MUST be capped in CPU parallelism, scheduled at a lower CPU and I/O priority than jobs, and MUST NOT start a build while the pool's admitted-job count is above a configured threshold; its duration and per-repository outcome MUST be recorded per generation. A RAM-resident compilation-cache backend MUST have a fixed memory ceiling with an eviction policy, and that ceiling MUST be sized against the pool's concurrency cap so cache memory and job memory do not compete for the same headroom.

**Storage placement.** Every host-side cache tree MUST live under the pool's label-addressed cache tier (the `ci-cache` role), MUST NOT assume a physical medium, and MUST be movable between media by data copy and relabel exactly as the pool's other storage tiers are. RAM-resident caches (the compilation-cache backend) hold only regenerable data and MUST be restorable by one populator run after a host restart. A cache MUST NOT depend on copy-on-write or reflink support from the host filesystem.

**Keyed cache posture.** A local emulation of GitHub's keyed `actions/cache` service is NOT required for conformance with this section and MUST NOT be the mechanism by which the transparency requirement is met. The pool MUST NOT run a forked or binary-patched forge runner to provide one. The pool MAY offer such an emulation only through a mechanism that leaves the stock runner untouched (a job-container-side redirect of the cache endpoint), only after that mechanism is proven on the pool with a routed job, and a routed repository that keeps `actions/cache` steps MUST continue to work unchanged whether or not the emulation is offered.

**Acceptance.** The section's acceptance is the routed Rust repository's full merge-gating matrix completing on the pool at or below its GitHub-hosted warm-cache baseline, a second routed repository showing cache hits with zero workflow changes, and the negative tests of §"Runner-pool cache telemetry" green.

## Proposal: Runner-pool cache telemetry: every tier emits use, cost, and health to the fleet observability surface

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a section "Runner-pool cache telemetry" after "Runner-pool build cache tiers" requiring that every cache tier the pool offers emit whether it was used, what it cost, and what it saved, per job, to the fleet's shared Honeycomb environment, in the fleet's existing build-telemetry attribute scheme and dataset, plus host-side health gauges on the existing heartbeat path with dead-man and value triggers, a pool-owned cold canary, negative tests on the isolation timer, and the receiver-allowlist obligation for factory spans. It also states the failure contract per emitter class.

### Motivation

Maintainer direction 2026-09-04: all important cache metrics, whether the cache is used and the timings it gives, must be emitted to Honeycomb. Today the tier-1 copy is fail-soft with no signal and the populator logs to an unread Job log, which is the shape the CI-runner heartbeat's own history warns about (an emitter that failed twelve times an hour for eight days unnoticed, livespec-s43svm.20). Fleet practice this section reuses, verified 2026-09-04: the livespec Honeycomb environment and github-ci dataset carrying ci.run and build.* spans; the console's build-telemetry attribute scheme, which already defines optional build.cache.tier and build.cache.hit attributes for exactly this purpose; the CI host heartbeat timer posting host.name-stamped gauges to the host collector, with ungrouped single-host dead-man triggers and MAX/MIN value triggers; the factory's keyless host receiver routing by service.name, whose fail-closed attribute allowlist silently drops unlisted attributes (livespec-orchestrator-beads-fabro plan otel-receiver-attr-verification). Honeycomb's guidance: cache state belongs on the wide event of the unit of work as one boolean per cacheable operation, so BubbleUp can split fast from slow by cache state. Research note 003 in plan ci-runner-cache-tiers carries the attribute list and trigger shapes.

### Proposed Changes

Insert a new top-level section `## Runner-pool cache telemetry` immediately after `## Runner-pool build cache tiers`, with the following normative content.

**Emission is mandatory.** Every cache tier the pool offers MUST emit, to the fleet observability surface (the shared Honeycomb environment the fleet's CI telemetry already uses), whether the tier was used by a job, what the tier cost that job, and the tier's health on the host. A tier with no emitted signal MUST NOT be considered shipped.

**Per-job spans.** For every job, the pool MUST emit from its own lifecycle hooks, not from any workflow step, one span per tier recording the copy outcome (hit or miss, generation identity and age, bytes and milliseconds copied, copy method, error text if any) and one span per job recording compilation-cache use (enabled, hits, misses, errors, hit ratio, backend, read-only mode). These spans MUST land in the same dataset as the fleet's CI run spans, MUST carry the fleet's build-telemetry scheme attributes (`build.env`, `repo`, `git.commit.sha`, `git.branch`, the triggering event, `host.name`), and MUST use the scheme's `build.cache.*` attribute namespace so one query shape covers CI and factory. Per-job cache attributes MUST be expressed as one attribute per cacheable operation (a hit boolean or a hit ratio per tier), never as a single aggregate that hides which tier missed.

**Factory parity.** The fabro sandbox image's build-phase spans MUST carry the same compilation-cache attributes, and every `build.cache.*` attribute MUST be admitted by the factory receiver's forwarded-attribute allowlist before factory emission is relied upon; the verification is a dispatch whose spans show the attributes populated.

**Host gauges and triggers.** The CI host MUST emit, on its existing fixed-cadence liveness path and stamped with `host.name`, the current generation age and size per tier, the populator's last duration and per-repository success and failure counts and toolchain version, the compilation cache's hits, misses, memory used, memory ceiling, and evictions, and the kill-switch state. The fleet MUST carry a dead-man trigger that fires on the absence of these gauges from the host, and value triggers for a generation older than twice the populate interval, a repository failing to populate in two consecutive windows, a per-repository compilation-cache hit ratio below its floor over a trailing day excluding canary and kill-switch jobs, a per-job copy cost above its ceiling, and compilation-cache memory pressure. Every trigger description MUST name the emitter path, the receiver path, the owning work item, and a runbook, as the pool's existing triggers do.

**Cold canary.** The pool MUST run a fixed, configurable fraction of jobs cold by construction, selected deterministically by the pool and tagged as canary on every cache span, so that warm-versus-cold timing for the same repository, phase, host, and contention is a standing query rather than a remembered benchmark. The canary MUST be tagged distinctly from an operator-set kill switch.

**Failure contract.** Pod-lifecycle emitters MUST be best-effort and MUST NOT fail or delay a job beyond the copy itself; their loss is visible as a gap in the data and as the canary query. Host-side emitters MUST be fail-closed and covered by the dead-man trigger. No emitter MAY carry a credential, a cache key's contents, or a writer endpoint.

**Negative tests.** The pool's isolation suite MUST assert, on its existing timer, that a job cannot write the warm-cache mount, that a compilation-cache write with a job's credentials is refused, and that no writer credential is present in a job pod.

**Archive evidence.** A plan that ships a cache tier MUST record, before it archives, the matrix wall-clock acceptance from run spans, two consecutive weeks of the canary gap holding, the hit-floor trigger not having fired outside a toolchain bump, the negative tests green, a second routed repository's hit spans, and the factory attribute verification.

## Proposal: Scenarios for the runner-pool cache tiers and their telemetry

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add six Gherkin scenarios to scenarios.md covering the load-bearing behaviors of the two new non-functional sections: a routed job reads a warm cache and cannot write it; a routed job's compilation-cache writes are refused; a cache fault degrades a job to cold without failing it; a canary job runs cold and is tagged; a stale generation fires the trigger; a fabro sandbox hits the shared compilation cache and its span carries the attributes. Heading coverage for the two new sections MUST be linked when the proposal is revised in.

### Motivation

The authoring discipline requires that load-bearing behavior be stated as a clause and a scenario, never prose alone. These scenarios are the behaviors the isolation timer, the Honeycomb triggers, and the archive-evidence gate check; plan ci-runner-cache-tiers research note 003 lists them as the negative tests and the acceptance evidence.

### Proposed Changes

Append the following scenarios to `scenarios.md`, each keyword line as its own paragraph per the file's convention, and link the headings `## Runner-pool build cache tiers` and `## Runner-pool cache telemetry` in `tests/heading-coverage.json` to the isolation-suite and telemetry tests that realize them (a `TODO` test id with a reason is acceptable at revise time and MUST be replaced when the first child lands).

`## Scenario: a routed job reads the warm cache and cannot write it`

Given the populator has published a current generation of the cargo and uv warm caches on the host

And a job pod for a routed repository starts on the pool with no change to that repository's workflow files

When the job container's postStart makes the current generation available to the job (by copy, or by pointing the package manager at the host-served cache)

Then the job's dependency sync MUST resolve from the copy without contacting the package index

And a write attempt against the warm-cache mount from inside the job MUST fail

And a `cache.warm-copy` span with `build.cache.hit` true MUST be emitted for each tier.

`## Scenario: a job's compilation-cache writes are refused`

Given the host compilation cache is reachable from a job pod through its read-only endpoint

When the job compiles a crate that is not in the cache

Then the crate MUST compile locally in the job

And the resulting object MUST NOT appear in the shared cache

And a write issued with the pod's credentials MUST be refused by the backend.

`## Scenario: a cache fault degrades a job to cold and never fails it`

Given the warm-cache tree is absent or unreadable on the node

When a job pod starts

Then the job MUST run to its own outcome with cold caches

And a `cache.warm-copy` span with `build.cache.hit` false and a non-empty `build.cache.error` MUST be emitted.

`## Scenario: a canary job runs cold and is tagged`

Given the pool's canary fraction is one job in N

When a job is selected as the canary by the pool's deterministic rule

Then every cache tier MUST be skipped for that job

And every cache span for that job MUST carry `build.cache.kill_switch` equal to `canary`

And the job's timings MUST be queryable against non-canary jobs of the same repository and phase.

`## Scenario: a stale warm-cache generation fires the trigger`

Given the populator has not published a generation for longer than twice its schedule interval

When the host's liveness path emits the generation-age gauge

Then the stale-generation value trigger MUST fire with a runbook naming the populator.

`## Scenario: a fabro sandbox hits the shared compilation cache`

Given the factory sandbox image sets the compiler wrapper and the host compilation-cache endpoint over the docker bridge

And the factory receiver's allowlist admits `build.cache.*`

When a console dispatch compiles dependency crates the populator already built

Then those crates MUST be served from the shared cache

And the dispatch's `build.cargo-*` spans MUST carry `build.cache.sccache.hit_ratio` greater than zero.
