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

Every `## Scenario:` heading in `SPECIFICATION/scenarios.md` MUST have its own entry in `tests/heading-coverage.json`. Scenarios are tracked granularly — one entry per scenario — and several scenarios MAY map to the same test (many-to-one is expected). Each mapped test MUST sit at the **integration tier or above**: a consumer-style check-runner test that imports a check from `livespec_dev_tooling.checks.*` and runs it against a fixture mini-project under `tmp_path` with deliberately-injected violations, asserting that the expected diagnostic fires — never a unit-tier helper test, since a scenario describes consumer-observable behavior. A scenario entry is compliant when EITHER (a) its test node-id path component begins with an integration-tier prefix declared in this repo's `pyproject.toml` `[tool.livespec_dev_tooling].scenario_tiers` allowlist, OR (b) the resolved test carries an explicit `pytest.mark.integration` (or stronger) marker. A `TODO` entry is permitted during transition provided its `reason` explicitly acknowledges this tier requirement. The library enforces this invariant on itself via its own `heading_coverage` check (self-application per `constraints.md` §"Self-application").

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

## Enforcement-suite invocation

The enforcement-suite invocation surface is `just <target>`. Lefthook hooks and CI workflows MUST delegate to `just <target>`; direct tool invocations (`ruff check ...`, `pytest ...`, `python3 ...`) inside `run:` blocks are forbidden. Once `no_direct_tool_invocation` migrates from livespec-core, the gate enforces this mechanically.

## Hooks and CI

The lefthook configuration MUST mirror livespec's pre-commit ordering (`00-install-worktree-pack`, `01-lint-autofix-staged`, `02-commit-pairs-source-and-test`, `03-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push ordering (`00-install-worktree-pack` then `01-check-pre-push`), per livespec `contracts.md` section "Pre-commit step ordering". The `00-install-worktree-pack` command delegates to `just install-worktree-pack`, which materializes the canonical worktree-discipline pack this repository ships into the checkout's gitignored `dev-tooling/` from the package the checkout resolves, so every later gate member that reads the pack finds it present and current whether the worktree was created by `just worktree-create`, by a raw `git worktree add`, or before a pin bump; the installer MUST be idempotent, MUST write only files the repository ignores, and MUST NOT relax the byte-identity verifier, which still asserts the installed bytes after the install. No hook command that reads the pack MAY precede it.

Codex support for this repository is REQUIRED at the contributor-workflow layer. `AGENTS.md` is the Codex-facing source of truth for repository mutation discipline, and the repository hooks remain the mechanical enforcement surface. This repo does not currently need project-local `.agents/skills/` livespec adapters because it owns shared enforcement-suite code rather than a user-facing `/livespec:*` Driver surface. If a future Codex adapter is added here, it MUST stay thin over governed core prose/wrappers or this library's stable `python -m livespec_dev_tooling.checks.<slug>` CLIs, MUST NOT copy Claude-specific skill bodies, and MUST be manually verified under Codex before it is claimed as supported. Agent-loop observability work, including `livespec-dev-tooling-e60`, MUST treat Codex as a distinct runtime with tokens-primary evidence instead of inferring Codex behavior or cost from Claude Code spans.

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

**Tiers.** The pool MUST provide a warm dependency cache for every package manager the routed repositories' lockfiles name (today uv and cargo, the latter covering the crate registry and git dependencies), realized either as a host-SERVED cache a job reads over the node network (a caching registry proxy or a RAM-resident store), or as a host-side tree that is SEEDED into each job's ephemeral work volume as that volume is provisioned, before the volume is bound to any pod, so that the job's first step already finds it there. Because per-job start writes are the pool's measured disk knee (about six simultaneous job starts saturate the array), a host-served realization MUST be preferred over a per-start copy wherever the package manager can consume one, and a copied realization MUST NOT ship without its per-start bytes measured against the pool's start-burst budget. The pool MUST provide a shared compilation cache for Rust (sccache or an equivalent compiler-invocation cache) served from the host and reachable from every job pod and from every fabro factory sandbox, so that one host service has two consumers. The pool MAY provide a per-repository warm target-directory cache through the copy mechanism, but MUST NOT ship it while the pod work-volume tier lives on the array, and MUST decide whether to ship it on faster media by measurement against the sccache-only shape on the routed Rust repository's full matrix, recording the decision in the plan store.

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
