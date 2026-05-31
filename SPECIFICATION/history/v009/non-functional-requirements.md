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

The lefthook configuration MUST mirror livespec's three-stage pre-commit ordering (`00-lint-autofix-staged`, `01-commit-pairs-source-and-test`, `02-check-pre-commit`), commit-msg gates (`00-no-commit-on-master`, `01-red-green-replay`), and pre-push gate (`check-pre-push` with zero-`.py` subsetting).

## Commit and merge discipline

Every commit on `master` MUST carry a valid Conventional Commits subject prefix; `release-please` reads the prefix to compute the next semver bump. Direct commits to `master` are forbidden (enforced by the `00-no-commit-on-master` commit-msg hook); changes flow via feature branches and pull requests. Merge strategy MUST be rebase-merge so each commit's subject prefix lands intact on `master`.

## Self-application

The library MUST apply its own checks to itself per `constraints.md` §"Self-application". `just check` in this repo MUST exercise every shared check this library ships, against this repo's own source tree, as part of the standard local + CI safety net.
