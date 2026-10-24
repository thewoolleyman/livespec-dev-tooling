# livespec-dev-tooling — non-functional requirements

This file enumerates the non-functional requirements binding this library's contributors. Anything visible at the user-facing CLI or Actions surface belongs in `spec.md`, `contracts.md`, or `constraints.md` instead.

## Boundary

`non-functional-requirements.md` covers concerns of the form "how this library is built, tested, and maintained":

- User-facing intent and architecture MUST stay in `spec.md`.
- The CLI surface, composite-Action contracts, and reusable-workflow contracts MUST stay in `contracts.md`.
- Constraints whose violation a consumer of this library could observe (runtime version, no-network-I/O, semver discipline, CLI shape) MUST stay in `constraints.md`.
- Acceptance scenarios consumers care about MUST stay in `scenarios.md`.
- Everything else — Test-Driven Development discipline, linter rule set, type-checker rule set, coverage gate, hook configuration, contributor workflow — lives in THIS file.

## Test-Driven Development discipline

The library MUST follow the same Red → Green → Refactor cycle livespec applies to itself per `livespec/SPECIFICATION/non-functional-requirements.md` §"Test-Driven Development discipline":

- Tests are written FIRST. A `feat:` or `fix:` commit MUST be preceded by a Red commit containing a failing test, then a Green commit containing the implementation that turns it green. Refactor commits are separate, never touch the test, and MUST keep the suite green.
- The Red → Green commit pair is enforced by the `red_green_replay` check at commit-msg time (once the gate migrates from livespec-core).
- Every source file MUST have a paired test at the mirror path under `tests/`; the pairing is enforced by `commit_pairs_source_and_test` at pre-commit time and by `per_file_coverage`'s 100% per-file gate at `just check`.

## Testing approach

- **Pyramid layers.** Outside-in tests at the top of the pyramid exercise each check module via `subprocess.run([sys.executable, "-m", "livespec_dev_tooling.checks.<slug>", ...])` against fixture trees in `tests/fixtures/`. Inner-layer unit tests cover pure helpers and validators. Property-based tests (`hypothesis`) cover pure modules that have semantic invariants (parsers, validators, formatters); the `pbt_coverage_pure_modules` check enforces presence once migrated.
- **Coverage gate.** 100% line AND branch on every first-party file, enforced by `pytest --cov` with `[tool.coverage.report].fail_under = 100`. Exclusions are minimal and documented in `pyproject.toml` `[tool.coverage.report].exclude_also`.
- **Import-Linter.** Architecture contracts MUST be declared in `pyproject.toml` `[tool.importlinter]` once the package gains multi-layer structure (parse / validate / io / commands).

### Scenario-tier coverage

Every `## Scenario:` heading in `SPECIFICATION/scenarios.md` MUST have its own entry in `tests/heading-coverage.json`. Scenarios are tracked granularly — one entry per scenario — and several scenarios MAY map to the same test (many-to-one is expected). Each mapped test MUST sit at the **integration tier or above**: a consumer-style check-runner test that imports a check from `livespec_dev_tooling.checks.*` and runs it against a fixture mini-project under `tmp_path` with deliberately-injected violations, asserting that the expected diagnostic fires — never a unit-tier helper test, since a scenario describes consumer-observable behavior. A scenario entry is compliant when EITHER (a) its test node-id path component begins with an integration-tier prefix declared in this repo's `pyproject.toml` `[tool.livespec_dev_tooling].scenario_tiers` allowlist, OR (b) the resolved test carries an explicit `pytest.mark.integration` (or stronger) marker.

A `TODO` entry is permitted ONLY as a transitional debt, and the transition MUST mechanically converge:

- Every `TODO` row MUST appear in the repository's heading-coverage debt register (`tests/heading-coverage-debt.json`, keyed by `(spec_root, spec_file, heading)` with the owning `work_item` and `first_seen` date). An unregistered `TODO` MUST fail the authoring-time armed tier, including one for a genuinely new heading. Existing registered debt MUST only shrink when resolved or removed; a commit that resolves a row to a real test MUST remove its register entry. The register MUST be generated mechanically, never authored by hand.
- A new register key MAY be admitted as spec-first debt ONLY when the same authored change introduces its exact H2 heading into the governed live specification, that heading and its coverage key are both absent from the comparable pre-change `HEAD` specification and coverage registry, the new coverage row declares `test: "TODO"` with a nonempty `work_item` and an acknowledgment that a real test at the required tier is owed, and mechanical regeneration supplies the matching owner and a `first_seen` date. The exception MUST NOT admit a pre-existing heading, real-test-to-TODO regression, orphan or dangling key, registry-only addition, or missing/mismatched owner or acknowledgment. Removing any existing H2 heading in the same specification file in that change MUST disqualify new debt in that file: replacement headings require real coverage, so renaming cannot reset debt.
- New-heading eligibility MUST be established from repository data against `HEAD` during authoring. An unavailable or unreadable comparison MUST report an evidence failure and refuse new-heading admission; it MUST NOT establish eligibility. This does not change first-adoption baseline behavior. After commit, an admitted row MUST be treated as ordinary registered debt at pre-push and CI, with no temporary environment override. Once recorded, `first_seen` MUST NOT move later, enforced in the authoring tier by comparison with `HEAD`; generator regeneration MUST preserve existing dates, add only genuinely new rows, and keep ownership synchronized with the live coverage row. After commit, an admitted row's `first_seen` MUST NOT be later than the committer date of the earliest commit whose coverage registry carries that key as TODO; pre-push and CI MUST reject a later date using repository history, and unavailable evidence MUST refuse validation rather than establish eligibility. This repository-data check does not introduce a wall-clock-dependent authoring verdict. Existing schema, reason, scope, stale-entry, liveness and age checks MUST continue to apply.
- The `reason` MUST acknowledge that a real test at the required tier is owed and MUST name nothing else. A `reason` asserting that the heading is not testable, is enforced elsewhere, or is prose without behavior MUST be rejected by `heading_coverage`. There is no non-testable category: a heading a repository believes has no behavior is a specification-structure defect to be fixed in the specification, never a coverage exemption.
- Every `TODO` MUST name a `work_item` that the configured tracker resolves as live; a closed or nonexistent owner MUST fail the release tier (as shipped in 1.59.0).
- A `TODO` older than the repository's configured age bound (default 30 days from first-seen) MUST fail the release tier. Liveness and age are evaluated ONLY at the release tier, so no per-commit verdict depends on mutable external state.
- An empty register MUST permit the same narrowly defined spec-first admission. Reaching zero MUST NOT retire scoped authorship, ownership or the reason acknowledgment needed for future ratification; all other new TODO rows MUST still fail. No free-text reason grants an exemption from writing a real test.

The library enforces this invariant on itself via its own `heading_coverage` check (self-application per `constraints.md` §"Self-application").

## Linter rule set

The 27 ruff categories from livespec are wired in `pyproject.toml` `[tool.ruff.lint].select`:

- v011 baseline (11 categories): `E`, `F`, `I`, `B`, `UP`, `SIM`, `C90`, `N`, `RUF`, `PL`, `PTH`.
- v012 additions (16 categories): `TRY`, `FBT`, `PIE`, `SLF`, `LOG`, `G`, `TID`, `ERA`, `ARG`, `RSE`, `PT`, `FURB`, `SLOT`, `ISC`, `T20`, `S`.

`ISC001` is the only ignored rule (conflicts with the formatter). Pylint sub-rule thresholds match livespec exactly: `max-args = 6`, `max-positional-args = 6`, `max-branches = 10`, `max-statements = 30`. Relative imports are banned via `flake8-tidy-imports.ban-relative-imports = "all"`. `abc.ABC`, `abc.ABCMeta`, `abc.abstractmethod`, `pickle`, `marshal`, and `shelve` are banned via `flake8-tidy-imports.banned-api` for the same reasons documented in livespec.

## Typechecker rule set

`pyright` runs in `strict` mode with the seven strict-plus diagnostics elevated to `error`:

- `reportUnusedCallResult`
- `reportImplicitOverride`
- `reportUninitializedInstanceVariable`
- `reportUnnecessaryTypeIgnoreComment`
- `reportUnnecessaryCast`
- `reportUnnecessaryIsInstance`
- `reportImplicitStringConcatenation`

`include` MUST cover `livespec_dev_tooling/` and `tests/`. `exclude` MUST cover `__pycache__/`.

## Code coverage thresholds

`fail_under = 100` line + branch. `exclude_also` MUST be minimal and limited to structurally-unreachable patterns matching livespec's exact list: `if TYPE_CHECKING:`, `raise NotImplementedError`, `raise ImportError`, `@overload`, `if __name__ == .__main__.:`, `sys.path.insert`, `case _:`. No other exclusions are permitted without a propose-change cycle. The `sys.path.insert` entry covers vendored-path guards of the form `if str(X) not in sys.path: sys.path.insert(...)` that are structurally dead when tests run via the project's `pythonpath` config in `pyproject.toml`.

## Comment discipline

Comments MUST explain the WHY (non-obvious constraints, hidden invariants, references to spec sections), not the WHAT (well-named identifiers already do that). The `ERA` ruff rule bans commented-out code; LLM-author scaffolding artifacts MUST be deleted before commit.

## Keyword-only arguments

Every function definition under `livespec_dev_tooling/` MUST use the `*` separator to make every parameter keyword-only, except dunder methods and third-party-SDK callbacks. Dataclasses MUST use `dataclass(kw_only=True)`. `match` destructures of project-owned dataclasses MUST use the keyword form (`case Foo(x=x):`).

## Structural pattern matching

Every `match` statement over a closed sum type MUST terminate with `case _: assert_never(<subject>)` so pyright's exhaustiveness check fires. Once `assert_never_exhaustiveness` migrates from livespec-core, the gate enforces this mechanically.

## Toolchain pins

Non-Python binaries (uv, just, lefthook) pin via `.mise.toml`; Python and Python packages pin via `pyproject.toml`'s `[project.requires-python]` and `[dependency-groups].dev`. Pinned versions MUST match livespec's `.mise.toml` and `pyproject.toml` exactly; drift surfaces as a propose-change-worthy event.

## Sandbox image gate toolchain

The `python-rust` Fabro sandbox image this repository builds, and every image layer built atop it (`python-rust-agent`, `python-rust-fuzz`), MUST carry `jq` on `PATH`.

More generally, a non-Python tool that a fleet consumer's gate member invokes, and that the consumer pins in its `.mise.toml`, MUST be present on `PATH` in the sandbox image that consumer's CI container pins. A delegated gate Job runs in exactly that image and deliberately runs no `mise install`: `ci-runner/k3s/phase2/gates/render-gate-job.sh` resolves the Job's image from the consumer's own `.github/workflows/ci.yml`. A tool the image does not carry is therefore absent from the gate.

A tool missing from that image MUST be provisioned in the image. It MUST NOT be worked around by narrowing the gate on the delegated path, consistent with livespec's ratified *The set* clause (livespec v229, `non-functional-requirements.md` §"Enforcement-suite invocation", **Delegated gate execution**), under which a tool on a host's path is a host-supplied condition that never leaves a check unarmed.

## Enforcement-suite invocation

The enforcement-suite invocation surface is `just <target>`. Lefthook hooks and CI workflows MUST delegate to `just <target>`; direct tool invocations (`ruff check ...`, `pytest ...`, `python3 ...`) inside `run:` blocks are forbidden. Once `no_direct_tool_invocation` migrates from livespec-core, the gate enforces this mechanically.

## Hooks and CI

The lefthook configuration MUST mirror livespec's pre-commit ordering (`00-install-worktree-pack`, `01-lint-autofix-staged`, `02-commit-pairs-source-and-test`, `03-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push ordering (`00-install-worktree-pack` then `01-check-pre-push`), per livespec `contracts.md` section "Pre-commit step ordering". The `00-install-worktree-pack` command delegates to `just install-worktree-pack`, which materializes the canonical worktree-discipline pack this repository ships into the checkout's gitignored `dev-tooling/` from the package the checkout resolves, so every later gate member that reads the pack finds it present and current whether the worktree was created by `just worktree-create`, by a raw `git worktree add`, or before a pin bump; the installer MUST be idempotent, MUST write only files the repository ignores, and MUST NOT relax the byte-identity verifier, which still asserts the installed bytes after the install. No hook command that reads the pack MAY precede it.

Codex support for this repository is REQUIRED at the contributor-workflow layer. `AGENTS.md` is the Codex-facing source of truth for repository mutation discipline, and the repository hooks remain the mechanical enforcement surface. This repo does not currently need project-local `.agents/skills/` livespec adapters because it owns shared enforcement-suite code rather than a user-facing `/livespec:*` Driver surface. If a future Codex adapter is added here, it MUST stay thin over governed core prose/wrappers or this library's stable `python -m livespec_dev_tooling.checks.<slug>` CLIs, MUST NOT copy Claude-specific skill bodies, and MUST be manually verified under Codex before it is claimed as supported. Agent-loop observability work, including `livespec-dev-tooling-e60`, MUST treat Codex as a distinct runtime with tokens-primary evidence instead of inferring Codex behavior or cost from Claude Code spans.

## Local gate concurrency limit

A host MAY set a local-gate slot limit N. The limit bounds the test runs that fleet gates execute on that host, so that concurrent sessions queue for the host instead of contending for it.

When a host's limit is set to N, at most N pytest sessions started from a fleet repository's checkout or worktree MUST run at once across all repositories and worktrees on that host, and every further such session MUST wait for a slot instead of starting. The limit MUST govern the pytest sessions run by the pre-commit check aggregate, the commit-msg replay gate, a local pre-push `just check`, and a hand-run `just check` alike.

A pytest session waiting for a slot MUST print a line naming the limit and that it is waiting, and MUST repeat that line at least once a minute while it waits. The wait MUST NOT be a busy loop: a wait of several minutes MUST add no measurable CPU load.

Waiting MUST NOT produce a verdict: a session that waited MUST run its tests once a slot frees and report their own result. A session killed while waiting MUST hold no slot. A session that holds a slot and dies, by any cause including SIGKILL, MUST free that slot without any cleanup step.

A pytest session started by another pytest session that already holds a slot MUST run without taking a second slot, so that a test suite which spawns pytest in a child process cannot deadlock against its own parent.

On a host with no slot limit set — a factory sandbox, a delegated gate pod, or any host never provisioned with one — pytest sessions MUST start exactly as they would without this section.

A host's limit MUST be provisioned through a committed converge, never set by hand, and removing that one committed setting MUST return the host to no limit.

The limit is a STOPGAP for gates that still run on a shared host. Once the fleet's heavy gates run delegated, the limit SHOULD be removed.

## Commit and merge discipline

Every commit on `master` MUST carry a valid Conventional Commits subject prefix; `release-please` reads the prefix to compute the next semver bump. Direct commits to `master` are forbidden (enforced by the `00-no-commit-on-master` commit-msg hook); changes flow via feature branches and pull requests. Merge strategy MUST be rebase-merge so each commit's subject prefix lands intact on `master`.

## Self-application

The library MUST apply its own checks to itself per `constraints.md` §"Self-application". `just check` in this repo MUST exercise every shared check this library ships, against this repo's own source tree, as part of the standard local + CI safety net.

## Adaptive JIT runner admission budget

The fleet JIT runner supervisor MUST govern installation-token and JIT-config
minting through one durable, installation-wide admission controller. Its
single-writer state and accounting MUST survive concurrent service instances
and service-manager restarts, so startup, reconciliation, recovery, and
steady-state replacement share the same demand, capacity, circuit, and retry
state.

Demand MUST be event-driven or an equivalently immediate deduplicating rescan:
a completed runner or newly observed queued job may trigger a replacement
admission without an unconditional per-runner delay. The controller MUST
deduplicate runner demand and record bounded queue state. A fixed positive
minimum interval between all runner admissions is prohibited; rate protection
comes from the installation-wide budget and from an actual GitHub response,
not from serializing healthy replenishment.

The controller MUST account for the GitHub App installation's REST point
budget. At startup it MUST immediately run a tight admission loop over current
deduplicated demand and admit every demand item permitted by the repository
desired-admission formula, remaining physical host capacity, and the remaining
450-point startup budget. It MUST take no unconditional sleep between those
permitted admissions and MUST NOT spend more than 450 of GitHub's documented
900 REST points per minute: at most about 45 complete mint pairs where the
installation-token POST and JIT-config POST consume approximately five points
each, or ten points per pair. After the initial batch it MUST admit only
budget-accounted refill work. Unknown,
corrupt, or unsafe persisted state and invalid configured bounds MUST fail
closed before a mint request is emitted.

Only an actual primary/secondary limit response (`403` or `429`) or valid
authoritative `Retry-After` or reset-time guidance MAY open the shared circuit
and backoff. When both valid guidance forms are present, the later boundary
wins. Missing, malformed, or contradictory guidance MUST use a conservative
finite fallback and be recorded; it MUST NOT cause an immediate retry.
Authentication and authorization failures are terminal, retryable failures use
a finite per-item budget with capped backoff and independently sampled bounded
jitter, and exhaustion MUST record an actionable terminal disposition without
restarting the supervisor.

Each repository's logical ceiling MUST be BOUNDED to a small multiple of that
repository's fair share of host-wide capacity — large enough that a repository
can borrow unused capacity beyond its guaranteed share, and never so large that
a backlog is materialized as pending admission objects the host's control plane
must keep reconciling: queued work beyond a bounded multiple of the admission
cap MUST wait at the forge, where it costs the host nothing, rather than exist
as pending objects on the host. The multiple, and any floor that keeps a
small-share repository from draining a lone matrix one job at a time, are pool
facts recorded with the pool's admission derivation, never here.
Maintainer-directed 2026-09-06. The physical host-wide cap remains exactly 482 active
runners; no configuration or recovery path may derive or admit 964 runners.
Repositories MAY fairly borrow unused capacity, and the desired admission for
each repository MUST be `min(queued jobs, doubled repository logical ceiling,
fair share of remaining host-wide capacity)`. A shared record with bounded
retention MUST expose per-repository logical demand/admission, fleet physical
occupancy, point-budget decisions, circuit and retry events, and recovery
without tokens or other secrets. Healthy registered runners remain available
and queued demand remains pending while the circuit is open.

## Runner-pool build cache tiers

**Scope.** The self-hosted runner pool provisioned from `ci-runner/k3s/` MUST offer build caching to every repository routed to it as POOL infrastructure. A routed repository MUST receive the caching with zero changes to its own workflow files, and a routed repository MUST NOT be required to carry `actions/cache` steps, cache keys, or cache-restore logic to benefit. A cache MUST live on the host's local disk or in the host's RAM; a cache that requires a network round trip off the host does not satisfy this section.

**Tiers.** The pool MUST provide a warm dependency cache for every package manager the routed repositories' lockfiles name (today uv and cargo, the latter covering the crate registry and git dependencies), realized either as a host-SERVED cache a job reads over the node network (a caching registry proxy or a RAM-resident store), or as a host-side tree that is SEEDED into each job's ephemeral work volume as that volume is provisioned, before the volume is bound to any pod, so that the job's first step already finds it there. Because every byte and file a seed adds to a job start is overhead on any medium, a host-served realization MUST be preferred over a seeded tree wherever the package manager can consume one, and a seeded tree MUST NOT ship unbounded: its per-start cost MUST be capped by one byte budget and one file budget stated in exactly one committed place that governs both the populator's refusal and the node's lifecycle sweep's judgement; the populator MUST refuse to publish a generation over either budget, leaving the previous generation live; and the sweep MUST report, as lifecycle findings with gauges, a live generation over budget and a seed whose measured bytes or duration exceed their budgets. A per-start byte copy of a cache MUST NOT ship in any tier. The pool's start-burst limit is that budget, not a hardware knee: the figure this clause once cited — about six simultaneous job starts saturating the array — was a 2026-09-02 measurement of a storage array the host no longer has; it is measurement history held in livespec's plan record (plan `ci-runner-pod-lifecycle-reliability`, research note 005), not a premise of this clause. The pool MUST provide a shared compilation cache for Rust (sccache or an equivalent compiler-invocation cache) served from the host and reachable from every job pod and from every fabro factory sandbox, so that one host service has two consumers. The pool MAY provide a per-repository warm target-directory cache only as a SEEDED tree — a host-side generation the volume provisioner seeds into each work volume exactly as it seeds a SEEDED dependency tree, under the reflink rule of **Storage placement**, consistent with the byte-copy prohibition above. Such a tree MUST be key-scoped: each key names one compile shape whose compile phase measurably stays cold with the compilation cache warm (a sanitizer-instrumented fuzz build is the shipped example), and it MUST be built only by the populator under **Populator guardrails**, rebuilt only when the consuming repository's default-branch commit or that key's toolchain changes. A key MUST NOT ship until the plan store records, for the consuming job, its measured before/after against the compilation-cache-only shape, the generation's size and file count, and why that headroom is worth the generation's build and seed cost. The pool MUST NOT provide a general dev-profile or test-profile key; the plan store record of that decision is what a future proposal MUST supersede to reintroduce one.

**Trust by construction.** A job MUST NOT be able to write any shared cache: a path a job can reach MUST NOT resolve to a shared inode of a warm tree — a job works on a private copy whose every inode is its own volume's, the shared tree MUST be reachable from no job pod, and only the populator writes it; the compilation cache MUST be reachable from a job only through a credential or endpoint that permits reads and refuses writes, enforced server-side, and a job's own compilation output MUST NOT be written back to any shared cache. The pool MUST NOT derive a per-job trust decision from any value a workflow can influence (workflow env, job labels, container env, the runner's process env). Exactly one trusted writer, the populator, MAY write the shared caches, and it MUST build only the default branch of each routed repository. Per-repository namespacing MUST prevent an object populated for one repository from being served to another, except for the compilation cache, whose entries are content-addressed and MAY be shared across repositories.

**Fail-soft and kill switch.** A cache fault MUST NOT fail a job: a missing, stale, or unreadable cache degrades that job to cold behavior. The pool MUST carry one fleet-wide kill switch, settable without a deploy of any routed repository, that disables every tier for every job; the same switch MUST drive the canary sampling required by §"Runner-pool cache telemetry".

**Populator guardrails.** The populator's Rust builds run on the node the jobs use; the populator MUST be capped in CPU parallelism, scheduled at a lower CPU and I/O priority than jobs, and MUST NOT start a build while the pool's admitted-job count is above a configured threshold; its duration and per-repository outcome MUST be recorded per generation. A RAM-resident compilation-cache backend MUST have a fixed memory ceiling with an eviction policy, and that ceiling MUST be sized against the pool's concurrency cap so cache memory and job memory do not compete for the same headroom.

**Storage placement.** Every host-side cache tree MUST live under one of the pool's label-addressed storage tiers, MUST NOT assume a physical medium, and MUST be movable between media by data copy and relabel exactly as the pool's other storage tiers are: a host-served cache's store MUST live under the cache tier (the `ci-cache` role); a seeded warm tree MUST live on the tier that holds the work volumes it is seeded into (the `ci-workvols` role), because a seed that costs no data bytes is legal only within one filesystem. RAM-resident caches (the compilation-cache backend) hold only regenerable data and MUST be restorable by one populator run after a host restart. A seeded warm tree MAY depend on copy-on-write (reflink) support from the tier's filesystem, and MUST when that is what makes the seed private per volume; the storage layout MUST then decide that tier's filesystem type once, by role, so the dependence is a property of the role and not of any medium. Every other cache MUST NOT depend on copy-on-write or reflink support. Where a seed's filesystem dependence is unmet, the job MUST get no seed (cold) rather than a byte copy.

**Keyed cache posture.** A local emulation of GitHub's keyed `actions/cache` service is NOT required for conformance with this section and MUST NOT be the mechanism by which the transparency requirement is met. The pool MUST NOT run a forked or binary-patched forge runner to provide one. The pool MAY offer such an emulation only through a mechanism that leaves the stock runner untouched (a job-container-side redirect of the cache endpoint), only after that mechanism is proven on the pool with a routed job, and a routed repository that keeps `actions/cache` steps MUST continue to work unchanged whether or not the emulation is offered.

**Acceptance.** The section's acceptance is the routed Rust repository's full merge-gating matrix completing on the pool at or below its GitHub-hosted warm-cache baseline, a second routed repository showing cache hits with zero workflow changes, and the negative tests of §"Runner-pool cache telemetry" green.

## Runner-pool cache telemetry

**Emission is mandatory.** Every cache tier the pool offers MUST emit, to the fleet observability surface (the shared Honeycomb environment the fleet's CI telemetry already uses), whether the tier was used by a job, what the tier cost that job, and the tier's health on the host. A tier with no emitted signal MUST NOT be considered shipped.

**Per-job spans.** For every job, the pool MUST emit from its own lifecycle hooks, not from any workflow step, one span per tier recording the copy outcome (hit or miss, generation identity and age, bytes and milliseconds copied, copy method, error text if any) and one span per job recording compilation-cache use (enabled, hits, misses, errors, hit ratio, backend, read-only mode). These spans MUST land in the same dataset as the fleet's CI run spans, MUST carry the fleet's build-telemetry scheme attributes (`build.env`, `repo`, `git.commit.sha`, `git.branch`, the triggering event, `host.name`), and MUST use the scheme's `build.cache.*` attribute namespace so one query shape covers CI and factory. Per-job cache attributes MUST be expressed as one attribute per cacheable operation (a hit boolean or a hit ratio per tier), never as a single aggregate that hides which tier missed.

**Factory parity.** The fabro sandbox image's build-phase spans MUST carry the same compilation-cache attributes, and every `build.cache.*` attribute MUST be admitted by the factory receiver's forwarded-attribute allowlist before factory emission is relied upon; the verification is a dispatch whose spans show the attributes populated.

**Host gauges and triggers.** The CI host MUST emit, on its existing fixed-cadence liveness path and stamped with `host.name`, the current generation age and size per tier, the populator's last duration and per-repository success and failure counts and toolchain version, the compilation cache's hits, misses, memory used, memory ceiling, and evictions, and the kill-switch state. The fleet MUST carry a dead-man trigger that fires on the absence of these gauges from the host, and value triggers for a generation older than twice the populate interval, a repository failing to populate in two consecutive windows, a per-repository compilation-cache hit ratio below its floor over a trailing day excluding canary and kill-switch jobs, a per-job copy cost above its ceiling, and compilation-cache memory pressure. Every trigger description MUST name the emitter path, the receiver path, the owning work item, and a runbook, as the pool's existing triggers do.

**Cold canary.** The pool MUST run a fixed, configurable fraction of jobs cold by construction, selected deterministically by the pool and tagged as canary on every cache span, so that warm-versus-cold timing for the same repository, phase, host, and contention is a standing query rather than a remembered benchmark. The canary MUST be tagged distinctly from an operator-set kill switch.

**Failure contract.** Pod-lifecycle emitters MUST be best-effort and MUST NOT fail or delay a job beyond the copy itself; their loss is visible as a gap in the data and as the canary query. Host-side emitters MUST be fail-closed and covered by the dead-man trigger. No emitter MAY carry a credential, a cache key's contents, or a writer endpoint.

**Negative tests.** The pool's isolation suite MUST assert, on its existing timer, from inside a routed job, that no inode under the job's warm-cache seed has a link outside that seed, that the job can still create an entry beside the seed, and — where the seed is a reflink copy, the generation it was seeded from is still retained, and the job image can read extent flags — that a seeded file's extents are shared with the generation, so a byte copy is caught too; and that a compilation-cache write with a job's credentials is refused, and that no writer credential is present in a job pod.

**Archive evidence.** A plan that ships a cache tier MUST record, before it archives, the matrix wall-clock acceptance from run spans, two consecutive weeks of the canary gap holding, the hit-floor trigger not having fired outside a toolchain bump, the negative tests green, a second routed repository's hit spans, and the factory attribute verification.

## Runner-pool node telemetry

**Scope.** This section governs the load and utilization telemetry of every node of the self-hosted CI runner pool's k3s cluster — the server, every CI agent, and every factory-only agent — whatever its `cluster_role` or factory posture. It is the node-level companion of §"Runner-pool cache telemetry", and it emits to the same fleet observability surface.

**Kubelet usage for every node.** Every node the cluster's API server lists MUST have its kubelet's node-level CPU usage, memory working set and available memory, filesystem usage and capacity, and network traffic emitted to the fleet observability surface, attributed by `k8s.node.name`. Every node MUST also report its Ready, MemoryPressure, DiskPressure and PIDPressure condition gauges and its allocatable CPU and memory. The set of nodes scraped MUST be discovered from the API server, so a node that joins the cluster is reported with no per-node configuration edit; a configuration that names one node's kubelet MUST NOT be the mechanism.

**Pod attribution.** Every pod's CPU and memory usage MUST carry the node it runs on and its namespace, the factory namespace included, and every container's CPU and memory requests and limits MUST carry the node it is scheduled on, so that requests and limits are readable against that node's allocatable. On a row describing a node, a pod or a container, `host.name` MUST name the node the row is about, never the host of the collector that read it.

**Host metrics on every node.** Every pool node MUST run a host collector that emits CPU utilization by state, load average, memory usage, per-mount filesystem usage, and disk and network I/O, stamped with `host.name` equal to the node's name. CPU saturation MUST be read from the idle share of CPU utilization, never from load average alone.

**Converged, never hand-installed.** Every pool node's collector — its configuration (read from the merged branch of `thewoolleyman/otel-collector`), its unit, its pinned binary and its ingest-key environment entry — MUST be converged by `ansible/ci-pool.yml`, so the node-provisioning stage of §"Runner-pool node rebuild recipe" returns a rebuilt node reporting, and the drift report `just ansible-drift ansible/ci-pool.yml` MUST report a node whose collector differs from the merged configuration. A hand-run installer MUST NOT be the deployment path.

**Board and triggers.** The fleet MUST carry, as code under `ci-runner/observability/boards/` and `ci-runner/observability/triggers/` converged by their `apply-*.sh`, one board showing per node the CPU, memory, filesystem and network usage, the four condition gauges, requests and limits against allocatable, and pod usage by node and namespace; and value triggers for a node whose CPU idle share stays at or below 10% for 15 minutes, a node reporting MemoryPressure, and a node whose memory working set exceeds 90% of its capacity. Each node MUST also carry a dead-man trigger, ungrouped and filtered to that one node, that fires when its kubelet usage stops arriving, because a grouped query cannot fire on a silent subject. Every trigger description MUST name the emitter path, the receiver path, the owning work item and a runbook, as the pool's existing triggers do.

**Failure contract.** No node-telemetry emitter MAY run inside a CI job pod or hand a credential to one. The collector reading every kubelet MUST hold only a read-only cluster identity, never the admin kubeconfig.

## Runner-pool node rebuild recipe

**Scope.** This section states this repository's obligation, as the repository that provisions the fleet's self-hosted CI runner pool, under livespec `SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner host requirements" clause "A host carrying fleet CI MUST be rebuildable from bare metal by a committed procedure". The property is that specification's; the recipe, its profiles, and its rehearsal obligation are this repository's.

**One procedure, staged.** `ci-runner/k3s/` MUST carry ONE procedure that takes a pool node from powered-on hardware with empty storage to a pool member taking jobs, and every stage of it MUST be a committed, executable artifact in this tree. The procedure MUST begin with a bare-metal stage under `ci-runner/k3s/phase0-bare-metal/` that produces the node's storage layout — storage-controller configuration where the node has one, partitioning, volume management, and the role-labeled storage tiers of §"Runner-pool build cache tiers" **Storage placement** with their filesystems — and installs the base operating system, and that stage MUST precede the pinned k3s install and the node-provisioning stage, whose preconditions (an installed operating system; an installed k3s and its admin kubeconfig) the bare-metal stage MUST establish. The node-provisioning stage MUST be the committed Ansible playbook `ansible/ci-pool.yml`, applied from the control node `vps` by `just ansible-apply ansible/ci-pool.yml` against the node's entry in `ansible/inventory/legacy.yml` (whose `cluster_role` selects the server-only and agent-only roles), and the drift report `just ansible-drift ansible/ci-pool.yml` MUST be run and read before that apply; the stage MUST NOT be a shell runbook executed on the node. The bare-metal stages and the pinned k3s install remain committed shell because they run before k3s exists, so the provisioning layer has no converged node to reach until they have run. The documented rebuild sequence MUST name the bare-metal stage as its first step, so that a rebuild done exactly as written starts from empty storage and not from a prepared disk, and MUST name the playbook apply as its node-provisioning step, so that a rebuild done exactly as written lands every node-local facility through the layer the automation applies.

**One profile per node.** Every node-specific value the procedure needs — the storage devices and controller layout, the placement of each role-labeled tier, the network interface and address the node's runtime binds, the node's cluster role (server or agent) and the address of the cluster it joins, the node's admission capacity, and its factory posture — MUST be read from a per-node profile committed beside the procedure, and the procedure MUST NOT embed a value that belongs to one node. A second pool node MUST be a second profile consumed by the same procedure and MUST NOT be a second procedure or a hand-edited copy of the first.

**Factory posture from the profile, surviving registration.** A pool node's factory posture — the `ci-runner.io/factory` node label that the factory's sandbox scheduling selects on — MUST be read from that node's committed profile (its `FACTORY_NODE` value) and MUST NOT be set or removed by hand. The control-plane datastore MAY be rebuilt empty at a control-plane boot, in which case every node re-registers, so the label MUST be re-established at node registration or by a mechanism that runs unattended at control-plane boot, with no playbook applied and no command run on any host. Once a node is Ready again it MUST carry `ci-runner.io/factory=true` exactly when its profile declares `FACTORY_NODE=true`. A reconcile that runs only when a playbook is applied MAY also correct the label, but it MUST NOT be the only mechanism that sets it.

**Re-runnable, and destructive only on consent.** The procedure MUST be re-runnable against a node already in its profile's declared state, changing nothing. Every step that destroys existing storage MUST refuse to run against a populated volume unless that invocation carries the operator's explicit destruction consent, and the refusal MUST name the volume it refused.

**Rehearsed before trusted.** A node's rebuild procedure MUST be rehearsed — executed from empty storage through to the node executing a job — before it is relied on for that node, and again after any change to the procedure or to that node's profile; the rehearsal's outcome MUST be recorded in the plan store or on the owning ledger item, naming the procedure revision and the profile it ran with. A procedure not rehearsed since it last changed MUST be treated as unproven, and a step that a rehearsal cannot reproduce MUST be treated as a defect in the procedure, never as an accepted gap, and MUST be scripted before the node is treated as conforming.

**Facts in the host record, the procedure here.** The per-host information repository for a node MUST carry the node's hardware facts and its profile's values and MUST NOT carry the procedure or any copy of it; this tree MUST NOT carry a host's hardware facts beyond what its profile consumes. A backup-and-restore artifact for a node MAY be kept beside the procedure for data recovery and MUST NOT be documented or used as the way the node's configuration is reproduced.

## Consent-gated pool-node disruption

**Scope.** This section covers deliberately disrupting a runner-pool node, such as rebooting the control-plane node or taking an agent node's k3s agent down to exercise node loss. That is a host action, and this section states how this repository performs it. Rebuilding a node from empty storage is governed by §"Runner-pool node rebuild recipe", not by this section.

**Committed and consent-gated.** Every deliberate disruption of a pool node MUST be performed by a committed playbook applied from the control node `vps` with `just ansible-apply`, and MUST NOT be performed by a command run by hand on any host. Such a playbook MUST act only on the single host named by an explicit confirmation variable equal to that host's inventory name. It MUST change nothing when the confirmation is absent or names another host.

**A node-loss drill refuses the hosts it must not disturb.** A playbook that takes a node's k3s agent down to exercise node loss MUST refuse the control-plane node and every Fabro factory host. It MUST identify those hosts from inventory, not from host names spelled in the play.

**It waits for CI, never for its subject.** Before it takes the agent down, a node-loss drill MUST wait until the node carries no CI runner pod and no gate Job pod, or until the runner pool reads idle. It MUST NOT cordon, drain, evict or delete any pod, because a workload left on the node is what the drill exists to observe.

**It restores and verifies.** A node-loss drill MUST restore the node after its configured hold. It MUST fail unless the node returns Ready with its taints, its factory label and its admission capacity unchanged, and it MUST report the UTC times at which the API first showed the node NotReady and Ready again.

## Fabro factory host provisioning

**Scope.** This section states this repository's obligation as the repository that provisions the fleet's Fabro factory hosts: the hosts that run a Fabro server and the sandbox containers its runs execute in. The play is `ansible/fabro-hosts.yml`; per-host values live in `ansible/inventory/host_vars/<host>.yml`, which is generated from the owning role's `HOST_VARS.md`.

**One play, applied after a drift read.** Every Fabro factory service this repository provisions on a host — its Fabro server instances and the controls that bound their sandbox containers — MUST be installed by a role that `ansible/fabro-hosts.yml` includes for that host, with every host-specific value read from that host's host_vars and never embedded in the role. A change to those services MUST be applied from the control node `vps` by `just ansible-apply ansible/fabro-hosts.yml`, and `just ansible-drift ansible/fabro-hosts.yml` MUST be run and read before that apply. A Fabro server instance or sandbox control installed on a factory host by hand MUST be treated as drift to be expressed in the play, never as an accepted exception.

**One instance per mapping.** Each Fabro server instance on a host MUST be exactly one mapping in that host's `fabro_server_instances`, and the `fabro_server` role MUST install exactly one instance per invocation. The role MUST refuse, before changing anything on the host, an instance list in which two instances share a `unit_name`, a `home_dir` or a `port`. An instance MAY name its own Fabro binary (`binary_path`) and its own `HOME` (`home_env`). When an instance omits either axis, the role MUST render that instance's unit exactly as it renders it without the axis existing, so that adding an optional axis never changes an instance that does not use it.

**Sandbox resource envelope.** A factory host MAY bound its Fabro sandbox containers inside one systemd slice by setting the Docker daemon's default `cgroup-parent`, with the slice's limits read from role variables. A role that edits `/etc/docker/daemon.json` MUST preserve every key it does not own. A converge MUST NOT restart `dockerd`: a setting that takes effect only on a daemon restart MUST be recorded as pending and applied only by an operator-selected restart, performed inside a window in which the host's Fabro servers carry no active runs.

**Documented beside the values.** The owning role's `HOST_VARS.md` MUST document every per-host variable the role reads, with its default where it has one. An interim control MUST also carry its operator procedure, its rollback and the condition under which it is retired.

## Fabro factory registry

**Scope.** This section states how this repository publishes, on each host
where the Dispatcher runs natively, which Fabro server instance answers to each
logical factory name. The Dispatcher reads that publication to resolve a
factory entry that declares `"registry": true` (livespec-orchestrator-beads-fabro
`contracts.md` §"Factory addresses resolved from a host registry"). A
Dispatcher running inside a factory sandbox or a cluster gate Job reads no such
file, and the file is not rendered there.

**Declared once, in the inventory.** The inventory MAY declare
`fabro_factory_registry`, and when it does it MUST declare it only in
`ansible/inventory/group_vars/dev_hosts.yml`: a
mapping from each logical factory name to an object carrying `host`, the
inventory name of the host that serves it, `unit_name`, the `unit_name` of one
mapping in that host's `fabro_server_instances`, and optionally `docker_host`, a
string spelled as the Docker CLI's `DOCKER_HOST`. A factory name SHOULD name the
Fabro server instance it addresses and SHOULD stay the same for that instance's
whole life.

**Rendered on the dispatching hosts.** On every host in the `dev_hosts` group,
`ansible/fabro-hosts.yml` MUST render `/etc/livespec/fabro-factories.json` as a
JSON object holding exactly one entry per `fabro_factory_registry` name: an
object whose `server` is `https://` followed by the named instance's
`canonical_host`, and which carries `docker_host` exactly when the mapping
declares it. When the inventory declares no `fabro_factory_registry`, the file
MUST hold the empty object. The file MUST be owned by root and MUST be
world-readable. A converge that runs the rendering on a host MUST leave that
host's file holding exactly the derived content, removing any entry the
inventory no longer declares. A run narrowed by `--limit` or `--tags` so that
it does not run the rendering on a host MUST leave that host's file
unchanged.

**Refused before writing.** Every run that runs the rendering on any host MUST
first validate every `fabro_factory_registry` entry, and MUST refuse, before it
writes the registry on any host, an entry whose name is not a string non-empty
after surrounding whitespace is removed, whose `host` is not an inventory host,
whose `unit_name` matches no mapping in that host's `fabro_server_instances`,
whose matched instance has no `canonical_host` non-empty after surrounding
whitespace is removed, or whose `docker_host` is present but is not a string
non-empty after surrounding whitespace is removed, naming the factory and the
reason. These are the same emptiness rules the Dispatcher applies when it reads
the file.

**Machines are bound only in the inventory.** Moving a factory name from one
instance to another MUST be a change to `fabro_factory_registry` or to host_vars
followed by this converge; no play, role or committed factory entry names the
machine.

## Docker engine install guard

**Scope.** This section governs the Docker engine install guard: the executable `/usr/local/libexec/docker-engine-guard` and the role steps that drive it. The guard installs the Docker engine on a factory host that already runs k3s and Tailscale, without risking that host's network access. A *run* is one attempt to install and commit the engine. Durable state lives under `/var/lib/docker-engine-guard`; runtime state lives under `/run/docker-engine-guard`, which is tmpfs and is cleared by a reboot. The *guarded units* are `docker.service`, `docker.socket` and `containerd.service`. The *start permission* is the file `/run/docker-engine-guard/allow-start`, and the *commit marker* is the file `/var/lib/docker-engine-guard/confirmed`. The guarded transition exists to install the engine once: after a run has committed, every later converge on that host takes the post-commit path. The guarded transition applies only to a host whose Docker packages and state, if any, were recorded by this guard's own runs; foreign Docker MUST be refused, never adopted.

**Start condition.** Each guarded unit MUST carry a guard drop-in whose conditions are exactly two OR'd `ConditionPathExists=|` lines, one naming the start permission and one naming the commit marker, so that no guarded unit can start unless a run holds the start permission or a run has committed. The guard MUST read each guarded unit's effective conditions from the service manager through `busctl` (the D-Bus `Conditions` property), and that check MUST pass only when exactly those two OR path conditions are present. The guard MUST accept its own drop-ins and the fleet's `sandbox_storage` drop-ins for `docker.service` and `containerd.service`, and MUST refuse any other drop-in on a guarded unit.

**One run at a time, under one lock.** Every guard operation MUST first ensure that `/run/docker-engine-guard` exists with mode `0700`, owned by root. It MUST then take an exclusive lock on `/run/docker-engine-guard/lock`, opening that file with `O_CREAT` and close-on-exec and never unlinking or replacing it. An operation MUST wait at most 60 seconds for the lock, and MUST exit non-zero without acting when the wait expires. At most one run MUST be a host's current reservation.

`reserve <run>` MUST create a reservation only when all of the following hold under the lock:

- the commit marker is absent;
- there is no current reservation, or the current reservation's run is `rolled-back`;
- every guard unit other than the reserving invocation's own unit is `inactive` with no queued job, where the guard units are `docker-engine-guard-start.service`, `docker-engine-guard-observe.service`, every dead-man timer and its service, and every other `docker-engine-guard-*.service`;
- no account has `docker` as its primary group or as a supplementary group.

A guard unit in the `failed` state is not `inactive`, and the refusal MUST name it. A refused `reserve` MUST print the holding run's id, its phase and its deadline, and MUST change nothing. The guard MUST NOT attach to, roll back or take over another run, except through an operator's `recover` that names that run. Every operation on a run MUST refuse when that run is not the current reservation.

**Phases.** Each run MUST record exactly one phase. The guard MUST write the phase durably (write, fsync, rename, then fsync the directory), and the phase MUST move only forward and only under the lock. The install path's phases are `reserved`, `publishing`, `published`, `armed`, `started`, `observing`, `observed`, `committed` and `confirmed`. The rollback path's phases are `rolling-back`, followed by one of the two outcomes `rolled-back` and `rollback-partial`; `rollback-partial` MAY later become `rolled-back` (through a later firing or `verify`), and `rolled-back` is final. The rollback path MUST be reachable from every install-path phase, including `committed` and `confirmed`, of a run the commit marker does not name, and MUST NOT be reachable from a run the commit marker names. The commit marker decides whether a run is committed, not the phase: a run whose marker is absent is uncommitted whatever its phase reads, including a recorded `committed`.

**Dispatch table.** Every operation on the current run MUST read the commit marker and decide by the following table, in one lock acquisition. "Deadline passed" means that the recorded boot id differs from the current boot id, or that the monotonic deadline has passed.

| operation | marker names the run | marker absent | marker names another run, or is unreadable |
| --- | --- | --- | --- |
| `publish` | refuse | allowed from `reserved` or `publishing` | refuse |
| `arm` | refuse | allowed from `published` | refuse |
| `start` | refuse | allowed from `armed`, deadline not passed | refuse |
| `observe` | refuse | allowed from `started`, deadline not passed | refuse |
| `confirm` | finish | allowed from `observed`, deadline not passed: commit, then finish | refuse |
| `rollback` | no-op, exit 0 | allowed from every install-path phase, and from `rolling-back` and `rollback-partial`; a no-op on `rolled-back` | refuse and report |
| `recover` | finish | resume `publish` from `publishing`; roll back from any other uncommitted phase | refuse and report |
| `verify` | refuse | allowed from `rollback-partial` and `rolled-back` | refuse |
| `reconfigure` | allowed from `confirmed` | refuse | refuse |

**Deadline.** `arm` MUST record the run's deadline as the current boot id plus a `CLOCK_MONOTONIC` instant N seconds ahead, where N covers the `start`, `observe` and `confirm` budgets plus a margin. `arm` MAY also record a wall-clock time, for reports only. Every operation that checks the deadline MUST treat a deadline recorded under a different boot id as passed.

**Publish.** The controller MUST write a run's inputs (the owned `daemon.json` keys, the drop-ins and the probe parameters) only into that run's `inputs/` directory, and only `publish` MUST install them into place. `publish` MUST move the run to `publishing` before its first package step, and MUST move it to `published` once the package step and the post-install condition check have passed. `publish` MUST take the host snapshot exactly once, before the first package step, and store it in the run's `before/` directory. A `publish` resumed from `publishing` MUST keep that first snapshot. The snapshot MUST hold the output of `iptables-save` and `ip6tables-save` per table without counters, the FORWARD policy of each address family, and the five watched forwarding and bridge-netfilter sysctls.

**Arm and the dead-man.** The package install creates the `docker` group, so `arm` MUST repeat the docker-group check: it MUST refuse, and trigger rollback, when any account is in the group. `arm` MUST arm the run's dead-man as the transient timer `docker-engine-deadman-<run>` through `systemd-run` with `--collect`, with `--on-active` equal to the interval remaining to the deadline (recomputed from the monotonic clock at arming), with `--on-unit-inactive=60`, with `AccuracySec=1s`, and with a service `TimeoutStartSec=900` whose command is `rollback <run>`. `arm` MUST succeed when that timer unit already exists, and a retried `arm` MUST keep the deadline first recorded for the run. The dead-man therefore fires at the deadline, and again 60 seconds after each rollback it runs, until `confirm` or a rollback outcome stops it.

**Start.** `start` MUST run only as the fixed unit `docker-engine-guard-start.service`. It MUST refuse when the run's dead-man timer unit is not active. It MUST move the run to `started` before it creates the start permission, so that a duplicate or delayed `start` refuses. It then starts `containerd.service` and then `docker.service`, each with a bounded wait.

**Observe and the challenge.** `observe` MUST run only as the fixed unit `docker-engine-guard-observe.service`, so that the service manager refuses a second observer. It MUST move the run from `started` to `observing` under the lock before its first sample. It MUST stop sampling when a lock-held check finds the run no longer `observing`, and it MUST NOT hold the lock while a Docker API request is outstanding. It samples the host every 15 seconds over the observation window, and records each sample in the run's evidence record. That record carries the run id, the boot id, the configuration digest, and the window's start and end.

On a failed sample, `observe` MUST record the failure in the evidence record, start `rollback <run>` as its own transient unit without waiting for it, and exit. On a passing window, `observe` MUST remove the canary and write a challenge under `/run/docker-engine-guard` that carries the run id, the boot id and a fresh nonce, and then move the run to `observed`. Each passing window's nonce MUST differ from every earlier one.

**Commit.** `confirm` MUST commit only from `observed`, and only with passing evidence, an unexpired deadline, and a challenge that was issued on the current boot, is younger than 120 seconds and carries the matching nonce. A `confirm` that carries an expired or already-used challenge MUST refuse. To commit, `confirm` writes `confirmed.tmp` holding the run id and the canonical digest of the role-owned daemon keys, fsyncs it, renames it to the commit marker, and fsyncs the directory. The run is committed the moment the rename returns. A failed directory fsync after the rename MUST be recorded as a durability warning and MUST leave the run committed.

After committing, `confirm` MUST perform the post-commit steps:

- set `committed`;
- remove the start permission;
- enable and start the three guarded units;
- stop the dead-man timer;
- move the run to `confirmed`.

A `confirm` for a run the commit marker already names MUST repeat those steps idempotently, without a challenge. After the post-commit steps, `confirm` MUST validate that the three guarded units are enabled and running, that the commit marker is present (after the commit it is the only path the guarded units' start condition can satisfy), and that the owned daemon keys match the marker's digest.

**After the commit.** `reserve` refuses while the commit marker exists, so the guarded transition never runs again on that host. A converge on a committed host MUST validate the owned daemon keys by their digest, the drop-ins and the units. It MUST apply a needed change only through `reconfigure`, which writes the owned daemon keys and records a pending drained restart as §"Fabro factory host provisioning" requires, and which MUST NOT remove or rewrite the commit marker. A converge that needs no change MUST reserve nothing. `verify <run>` MUST re-evaluate the rollback postcondition set read-only, and MUST rewrite `rollback-partial` as `rolled-back` only when every postcondition holds.

**Rollback.** `rollback` on a run not already on the rollback path MUST record `rolling-back` before any other step; a later firing on `rolling-back` or `rollback-partial` MUST keep the recorded phase until it writes its outcome. From the first `rolling-back` on, `start` and `confirm` refuse for that run. It MUST stop `docker-engine-guard-observe.service` and `docker-engine-guard-start.service`, with SIGKILL after 10 seconds, and wait for both to be inactive before it revokes the start permission. The rollback driver then runs its phases in this order:

1. stop `docker.socket` before `docker.service`;
2. cancel the queued jobs of the three guarded units;
3. restore each address family's FORWARD policy;
4. kill by cgroup, and stop, the guarded units and `fabro-sandbox.slice`;
5. disable the three guarded units;
6. remove Docker's firewall footprint;
7. delete the bridge interfaces;
8. compare the sysctls with the snapshot;
9. run the final check, which reads every postcondition together after every stop phase.

The *postconditions* are:

- no start permission;
- no socket, process, queued job or pending start for the guarded units;
- each FORWARD policy as snapshotted;
- no Docker rule;
- no `docker0`;
- each watched sysctl as snapshotted.

The driver MUST run each phase as a child process under `timeout -k 10` with that phase's budget, and the phase budgets MUST sum to 600 seconds. Before entering a phase, the driver MUST durably record an attempt for it. A phase whose recorded attempts reach three without a recorded success MUST be skipped. A phase that fails, times out or is skipped MUST NOT prevent any later phase from running. The final check MUST clear the success record of every phase whose postcondition it finds failing.

The driver MUST write `rolled-back` only when every postcondition holds; otherwise it MUST write `rollback-partial`, naming each failed postcondition. It exits 0 either way. With a `rolled-back` outcome, the driver MUST stop its own dead-man timer with `systemctl stop`. With a `rollback-partial` outcome, a later firing MUST re-run only the phases whose postcondition fails and whose recorded attempts are under three. Once every failing phase has exhausted its attempts, the driver MUST stop its own dead-man timer, and the run waits for an operator's repair followed by `verify`.

**Host actions.** Every external command the guard runs MUST go through one runner with an explicit timeout. Firewall changes MUST use only the `iptables-nft` commands.

- **Footprint.** Docker's firewall footprint MUST be exactly the rules that are present now and absent from the snapshot and that reference `docker0`, `172.17.0.0/16`, or a chain absent from the snapshot whose name starts with `DOCKER`. Every rule and chain the snapshot contains MUST be excluded from the footprint.
- **Footprint removal.** Removal MUST issue `iptables -D` and `ip6tables -D` with each rule's full specification, then flush and delete the selected chains. It MUST re-read and repeat, for at most three passes, and MUST report every residual Docker rule.
- **FORWARD restore.** FORWARD restore MUST issue one `-P FORWARD` per address family, with the policy recorded in the snapshot.
- **Job cancellation.** Job cancellation MUST issue `systemctl cancel` with the job ids of the queued jobs whose unit is a guarded unit, and never a bare `systemctl cancel`.
- **Cgroup kill.** The cgroup kill MUST issue `systemctl kill --kill-whom=all --signal=SIGKILL` for `docker.service`, `containerd.service` and `fabro-sandbox.slice`, followed by a bounded `systemctl stop` of those units and `docker.socket`. No kill or stop MUST target any other unit, so `k3s-agent.service` and its containerd are never touched.
- **Disable.** The disable action MUST disable the three guarded units.
- **Interfaces.** The interface action MUST delete `docker0` and every veth whose master is `docker0`.
- **Sysctls.** The sysctl action MUST compare the five watched forwarding and bridge-netfilter values with the snapshot and report each difference.
- **Postcondition read.** The postcondition read MUST report the state of the permission, sockets, processes, queued jobs, FORWARD policies, Docker rules, `docker0` and sysctls as one record.

**Package fence.** The package step MUST refuse:

- when the simulated transaction installs a package or version outside the committed allowlist, removes a package, or upgrades an installed package;
- when an installed version the audit relied on has changed since the audit;
- when a downloaded `.deb`'s SHA256 differs from the archive index, or its maintainer scripts differ from the committed digests;
- when a host apt hook file or dpkg configuration file differs from its committed digest.

The package step MUST run `dpkg -i` on exactly the audited `.deb` files, with `DPKG_FRONTEND_LOCKED=1` in its environment. It MUST require the post-install `dpkg-query` difference to equal the audited additions. Before it issues `dpkg -i`, the package step MUST write the `dpkg --audit` output it read, after recovering any guard run's leftover packages, into the run's directory as that run's pre-install audit record, and it MUST issue `dpkg -i` only when that output is empty. A package that `dpkg --audit` names is a guard run's leftover when it is in a guard run's recorded intended set, or when the most recent pre-install audit record any guard run wrote on the host is empty and dpkg's own log (`/var/log/dpkg.log`) records no `install`, `upgrade`, `remove`, `purge` or `configure` action since that record was written on a package outside every recorded intended set. The second arm is what makes a trigger handler that the guard's own `dpkg -i` activated (man-db, libc-bin and systemd are the measured ones) the guard's to finish, while a package touched by any other transaction stays somebody else's. Recovery of an interrupted install MUST first re-unpack each `half-installed` package that is a guard run's leftover, by running `dpkg --unpack` with `DPKG_FRONTEND_LOCKED=1` naming exactly the audited `.deb` of this run whose package name, version and architecture equal the half-installed package's. It MUST refuse naming the package when no audited `.deb` of this run has that name, version and architecture. It MUST then run `dpkg --configure` only on `unpacked` or `half-configured` packages that are a guard run's leftover, and it MUST NOT run `dpkg --configure` on a package while that package is `half-installed`. It MUST complete interrupted triggers with `dpkg --triggers-only`, restricted to `triggers-awaited` or `triggers-pending` packages that are a guard run's leftover, so that neither a rollback from `publishing` nor a kill during `dpkg -i` strands a later run. The package step MUST NOT issue `dpkg --configure -a`. The package step MUST NOT issue `dpkg --unpack` on any file that is not one of this run's audited `.deb` files. The package step MUST refuse when `dpkg --audit` names a package that is no guard run's leftover, and it MUST NOT report the audited additions installed while `dpkg --audit` names any package.

**Preflight.** Before `reserve`, the preflight MUST refuse in each of these cases:

- `172.17.0.0/16` overlaps an address on any interface, a route in any routing table, the tailnet range, or the cluster's pod or service CIDR;
- any account has `docker` as its primary group or is a member of it;
- any effective k3s resync interval exceeds five minutes.

The guard MUST read each effective resync interval from `/etc/rancher/k3s/config.yaml` and its drop-ins, and record each with its source. The resync window is the largest of those intervals plus two minutes.

**Probes.** Each sample of the observation window MUST run these probes:

- **Services.** The services probe requires `k3s-agent`, `tailscaled` and every unit in `docker_engine_must_stay_running` to be active.
- **Node Ready.** The Node Ready probe reads the node's own status through `get --raw /api/v1/nodes/<node>/status`, using the node-status credential.
- **DNS.** The DNS probe requires every CoreDNS backend to be on another node. That placement is read through the k3s server at the preflight and again at the end of the window, and a same-node result is reported as not counting toward confirmation. The probe sends its query to the kube-dns service address from the pod network namespace, and parses the reply without a resolver file.
- **API.** The API probe completes a TLS handshake to the Kubernetes API service ClusterIP from the pod network namespace.
- **HTTPS.** The HTTPS probe connects from the pod network namespace to an address resolved on the host, sends SNI explicitly, and issues a HEAD to an Ubuntu archive mirror.
- **Sysctls.** The sysctl probe requires the five watched values to equal the snapshot.
- **k3s witness.** The preflight records the containerd PID of `k3s-agent.service` and the paths `/run/containerd/s` and `/run/containerd/runc/k8s.io`. A sample fails when that PID has changed or either path is missing.
- **Containers and networks.** The canary's cgroup is resolved through `systemctl show -p ControlGroup fabro-sandbox.slice`. A sample fails when any container other than the canary exists, or when any Docker network other than `bridge`, `host` and `none` exists.
- **Interfaces.** A sample fails when any interface other than `docker0`, the canary's one veth pair, and a veth whose master is a bridge recorded in the snapshot has appeared since the snapshot. A veth whose master is `docker0` or any other interface absent from the snapshot fails the sample unless it is the canary's.
- **Firewall.** A sample's firewall comparison covers the built-in chain policies of both families, the rules of `INPUT`, `FORWARD`, `OUTPUT`, `PREROUTING` and `POSTROUTING`, and the contents of `ts-*` chains. It skips the contents of `KUBE-*` and `FLANNEL-*` chains.

A failed probe MUST be re-run once immediately, and MUST count as failed only when it fails twice. Every probe failure MUST be recorded with the probe's name and its error.

**Bounds.** Every guard operation MUST run only as its own transient `Type=oneshot` unit, never as a bare child of a controller's session. Each unit's `TimeoutStartSec` is the operation's budget, with a control-group kill and SIGKILL 30 seconds after it. The budgets are:

| operation | budget |
| --- | --- |
| `reserve` | 60 s |
| `publish` | 1800 s, install included |
| `arm` | 60 s |
| `start` | 180 s |
| `observe` | the window plus 300 s |
| `confirm` | 120 s |
| `rollback` | 900 s |
| `verify` | 120 s |
| `reconfigure` | 120 s |
| `recover` | 1800 s |

`start` and `observe` use their fixed unit names; every other operation uses a per-invocation unit name. `recover` MUST perform its work through the same locked helper as the other operations, running the operation it delegates to within its own unit rather than as a nested unit, so its own budget bounds the whole recovery. The recovery bound — one in-flight operation's budget plus 30 seconds, plus the dead-man's 60-second interval, plus one rollback budget — is claimed for killed, hung or crashing processes, not for kernel or storage failure.

## Host provisioning tree

**Scope.** The `ansible/` tree is this repository's committed provisioning model for the fleet's legacy Ubuntu hosts: the inventory that declares them, the playbooks that select them, and the roles that install onto them. A host reaches its converged state only through a play whose `hosts:` selects it, applied from the control node by the committed drift and apply commands, from committed source. There is deliberately no checkout on a target. The obligations below keep that model whole.

**Every inventory host is reachable by a playbook.** Every host declared in the provisioning inventory (`ansible/inventory/*.yml`) MUST be selected by the `hosts:` of at least one play in a committed playbook under `ansible/`, with inventory group membership and Ansible host patterns resolved, so that both the drift report and the apply reach it. A declared host that no play selects is a defect in the provisioning tree, never an accepted state: the inventory declares it managed while nothing manages it, and no committed command can see its drift.

**A replaced installer is retired.** A role that declares it replaces a shell installer, by a `# Replaces` claim in one of its files whose path, on the same or the next comment line, names a path in this repository, MUST NOT coexist with that installer: every path the claim names MUST NOT exist in the tree once the role lands, and the commit that deletes it MUST cite the pre-deletion commit in its body. A claim whose path is led by another repository's name (for example `vps-info services/…` or `fabro-hosts services/…`) is outside this obligation, since that repository owns its own tree. A role that replaces only part of an installer that remains in the tree MUST say so in prose rather than in the claim form, so that an installer which legitimately survives for its other half is never the subject of a retirement claim.

**Enforced in the aggregate.** Both obligations MUST be asserted by this repository's `just check` aggregate, as `check-ansible-inventory-hosts-covered` and `check-ansible-replaced-installers-retired`. They are repo-private checks, outside the canonical fleet-universal slug set, because this repository alone owns the provisioning tree. Each MUST fail the aggregate on any violation. A run that inspects nothing, with no inventory host or no in-repository replacement claim, MUST report itself as vacuous rather than as a pass.

## Dev host Fabro client builds

**Scope.** This section states how this repository places, on each host the `ansible/dev-host.yml` play selects through `dev_hosts`, the Fabro CLIENT builds that a Dispatcher running natively there invokes through a committed `dispatcher.factories.<name>.bin`. A factory reached through the host PATH client enters this section only when a repository commits a `bin` for it that names a declared `path`, and the PATH client itself enters it only through `fabro_client_path_client` below. It does not govern a Fabro SERVER binary, which §"Fabro factory host provisioning" governs through the `fabro_server` role. (On a host where the PATH client is a symbolic link to a server instance's `binary_path`, the exclusions below are what keep the two roles from writing one file.) On `vps` the dev host is also the Ansible control node; the control-node and host wording below stays correct for a dev host that is not.

**Declared once, in the inventory.** The inventory MAY declare `fabro_client_builds`, and when it does it MUST declare it only in `ansible/inventory/group_vars/dev_hosts.yml`: a list of objects, each carrying `path`, the absolute path on the dev host where the build is placed; `source`, an absolute control-node path holding the build an operator has staged; and `sha256`, the build's digest as 64 hexadecimal digits, compared case-insensitively. A declared `path` is written only by the play; the `source` tree is what an operator stages and the play reads.

**Committed bins name a declared path.** Every `dispatcher.factories.<name>.bin` this repository commits in its root `.livespec.jsonc` MUST equal the `path` of one `fabro_client_builds` entry, and this repository's `just check` aggregate MUST assert it as `check-dev-host-fabro-client-bins-declared`. When this repository commits no `bin`, that check MUST report itself as vacuous rather than as a pass. That check is a repo-private check, outside the canonical fleet-universal slug set, because it reads this repository's own `.livespec.jsonc` against its own inventory. This section does not admit a `bin` key into the factory registry; work-item livespec-dev-tooling-ulct7a owns that admission and the rule that a registry-declared `bin` names a declared `path`. The same rule for every other fleet repository's committed `bin` is documented in the role's `HOST_VARS.md`, not enforced here.

**Refused before writing.** The role MUST first validate every `fabro_client_builds` entry, and before it writes anything on the host for any entry it MUST refuse the role's converge on that host, naming each refused entry and the reason, when any entry is one of these:

- an entry missing `path`, `source` or `sha256`;
- a `path` or `source` that is not absolute;
- a `sha256` that is not 64 hexadecimal digits;
- a `path` that DENOTES THE SAME FILE on the host as another entry's `path`;
- a `path` at which something already exists on the host that is not a regular file, a symbolic link included;
- a `path` an ancestor of which exists on the host and, after symbolic links are resolved, is not a directory;
- a `path` that DENOTES THE SAME FILE on the host as the `binary_path`, explicit or defaulted (the default being the one the `fabro_server` role applies for that host, resolved per host rather than restated), of any `fabro_server_instances` mapping declared for that host;
- a `path` whose `<path>.incoming` DENOTES THE SAME FILE on the host as any entry's `path` or as any such `binary_path`;
- when the dev host is the control node, a `source` that DENOTES THE SAME FILE as its own `path` or as any entry's `path`;
- a `source` that is absent or hashes, on the control node, to anything but `sha256`.

Two names DENOTE THE SAME FILE when they are equal after every symbolic link in both, final component included, is resolved, or when both exist and are on the same device with the same inode.

**Staged by the dev-host play, never by hand.** A role that `ansible/dev-host.yml` includes MUST install each declared build at its `path` with mode 0755, owned by the user a role variable names and that user's primary group, the variable documented with its default in the role's `HOST_VARS.md`. Every missing ancestor directory of a `path` MUST be created, mode 0755, owned by that same user and group; an existing parent directory is left as found. When the file at `path` already hashes to `sha256` the role MUST leave its contents untouched and MUST still ensure its mode and owner, so a converge with unchanged inventory on an undrifted host changes nothing. When no regular file is at `path`, or it hashes to anything but `sha256`, the role MUST place the build atomically, by writing it to `<path>.incoming` in the same directory, setting that file's mode and owner as above, verifying that it hashes to `sha256`, and only then renaming it into place, and a converge MAY overwrite or remove a `<path>.incoming` left by an earlier interrupted converge, removing it first when it is not a regular file, so a Dispatcher already executing the old build keeps a whole file; the outgoing build is not retained, and a rollback is a change to the entry's `source` and `sha256`. A build at a declared `path` MUST NOT be replaced by a hand copy: changing it is a change to the inventory followed by the play. Apart from a declared entry's own `<path>.incoming`, the role MUST NOT remove a file on the host, so a build at a `path` that the inventory no longer declares stays in place, because a Dispatcher in another fleet repository may still name it in a committed `bin`; the role keeps no record of earlier inventories and does not report such a file.

**Documented beside the values.** The role's `HOST_VARS.md` MUST document `fabro_client_builds`, each key of an entry and the owner variable, and MUST name which committed `bin` values in the fleet are expected to point at each declared `path`. It MUST also state why rollback here is a change to the inventory rather than a retained copy, as the `fabro_server` role keeps; that a declared `path` is never a server instance's `binary_path`, and is best kept out of a server instance's binary directory altogether, where the `fabro_server` role stages and retains its own builds; and that a dev host whose login differs from the default sets the owner variable in its host variables.

**The PATH client.** The inventory MAY declare `fabro_client_path_client`, and when it does it MUST declare it only in `ansible/inventory/group_vars/dev_hosts.yml`, beside `fabro_client_builds`. It is an object carrying `link`, the absolute path on the dev host of the Fabro client the host PATH resolves, and `target`, which MUST equal the `path` of one `fabro_client_builds` entry. When the key is absent the role MUST NOT create, change or remove anything at any PATH client location.

When the key is present, the role MUST refuse its converge on that host before writing anything on the host for any entry or for `link`, naming the reason, when any of these holds:

- `link` or `target` is missing or not absolute;
- `target` equals no entry's `path`;
- what the host holds AT `link`, read without following a symbolic link, is neither a symbolic link nor absent (so a dangling symbolic link counts as a symbolic link);
- `link` is a symbolic link whose target, after every symbolic link is resolved, is a directory;
- an ancestor of `link` exists on the host and, after symbolic links are resolved, is not a directory;
- `link`, with every symbolic link in its ancestors resolved and its final component left unresolved, equals any entry's `path`, any entry's `<path>.incoming`, or the `binary_path`, explicit or defaulted, of any `fabro_server_instances` mapping declared for that host, each compared after the same resolution;
- anything that is not a symbolic link exists at `<link>.incoming`, read without following; or `<link>.incoming`, resolved the same way, equals any entry's `path`, any entry's `<path>.incoming`, or any such `binary_path`.

A symbolic link that an earlier interrupted converge left at `<link>.incoming` MAY be replaced.

Otherwise the role MUST make `link` a symbolic link whose literal target, as `readlink` prints it, is `target`. It MUST do so only after every declared build is in place, so the PATH client never names a build the converge has not yet installed. The link MUST be owned by the role's owner user and that user's primary group, and every missing ancestor directory of `link` MUST be created as it is for a declared `path`. When `link` is already a symbolic link whose literal target is `target`, the role MUST leave it in place and MUST still ensure its owner and group, so a converge with unchanged inventory on an undrifted host changes nothing. When `link` is absent, or a symbolic link whose literal target is anything else, the role MUST replace it atomically. It does so by creating the new symbolic link at `<link>.incoming` and renaming it onto `link`, so that the symbolic link at `link` itself is replaced; the rename MUST NOT descend into a directory that an existing link at `link` names. The role MUST NOT write through an existing symbolic link at `link`, so the file the old link pointed at is left exactly as found; on vps that file is a live server's binary.

The role's `HOST_VARS.md` MUST document the key, both of its fields and these refusals, and MUST state that moving the PATH client between client families is a change to `target` followed by the play. Its paragraph that today declares the PATH client out of scope, and routes moving it through the `fabro_server` role, MUST be replaced accordingly.

## Dev host disk retention

**Scope.** This section states the standing disk retention on the maintainer's dev host, the host the `ansible/dev-host.yml` play selects through `dev_hosts`. That host is also the Ansible control node, and its root filesystem holds every governed checkout, their `tmp/gate-runs` directories, the uv cache and the docker store its factory and gate work leave behind.

**Provisioned, not hand-installed.** The retention MUST run at least daily from a systemd timer that a role included by `ansible/dev-host.yml` installs, as §"Host provisioning tree" requires for every service on an inventory host. Its script MUST be committed in that role, and its retention period MUST be a role variable documented in the role's `HOST_VARS.md`.

**What one run reclaims, and what it leaves.**

- It MUST remove dangling docker images and MUST leave every tagged image and every image a container uses in place.
- It MUST prune the uv cache. When the prune cannot remove a path, the run MUST log that path and continue with its remaining steps, never abort.
- It MUST remove a gate-run directory under a governed checkout's `tmp/gate-runs` only when that run is TERMINAL — it carries a recorded exit code, or its recorded process is no longer alive — and is older than the retention period. It MUST leave a gate run whose recorded process is alive in place, whatever its age.
- Each run MUST log what it removed and the root filesystem's free space before and after.

Cargo build targets are deliberately outside this section: the large ones belong to the fabro repository's owner, whose retention rule governs them.

## Fleet manifest adopter profiles

livespec-dev-tooling's manifest parser and its fleet-conformance sweep are the reader of the `adopters` array of livespec core's `.livespec-fleet-manifest.jsonc`, whose meaning livespec core's specification owns (its non-functional-requirements.md, "Profiles and the declarative manifest"). This section states only what that reader accepts and evaluates.

- An adopter entry's `profile` MUST be either a non-empty list whose every element is one of the layers `baseline`, `fleet-infra`, `orchestrator-plugin` and `app`, or exactly the one-element list `["instruction-only"]`. `instruction-only` replaces the `baseline` floor and MUST NOT be combined with any layer.
- An adopter entry's `posture` MUST be one of `released`, `pinned` and `none`.
- The parser MUST reject the whole manifest with the `malformed-adopter` reason when any adopter entry violates either rule above. That includes a profile list naming `instruction-only` beside another value.
- The sweep MUST hold a `released` adopter whose profile is `["instruction-only"]` to the adopter plugin-currency row and to no other row. A committed `.claude/settings.json` declaring `livespecPluginCurrencySuccessor` with a non-empty `mechanism` and `documentedIn` satisfies that row.
- The sweep MUST report an adopter whose `posture` is not `released` as posture-excluded and MUST NOT fail on it.
- The member parser MUST read a `fleet` member entry by its `repo` and `class` alone and MUST NOT read a profile from it, so a `profile` written on a `fleet` member entry has no effect.
