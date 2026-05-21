# livespec-dev-tooling

Shared enforcement-suite library for livespec-governed projects.

Distributes the canonical ruff/pyright/coverage gates, AST checks,
CI-alignment checks, and red-green-replay discipline as a Python
package plus composite GitHub Actions and reusable workflows.

Consumed by [`livespec`](https://github.com/thewoolleyman/livespec),
every `livespec-impl-*` plugin, and any future livespec-governed
sibling library or application.

## Status

**Phase G.2 (initial scaffold).** Empty `livespec_dev_tooling/` package
and an empty `SPECIFICATION/` tree. Subsequent phases of epic
`li-fgqgnk` (tracked in `livespec`'s own work-items store) populate
the spec, migrate the 39 enforcement-suite scripts from
`livespec/dev-tooling/checks/`, and wire the composite Actions
plus reusable workflows.

## Consumption

Once Phase G.5 cuts `v0.1.0`, consumers add this library two ways:

### As a Python package (uv git source)

```toml
[dependency-groups]
dev = [
    "livespec-dev-tooling",
    # ... your other dev deps
]

[tool.uv.sources]
livespec-dev-tooling = { git = "https://github.com/thewoolleyman/livespec-dev-tooling.git", tag = "v0.1.0" }
```

Invoke any check via:

```
uv run python -m livespec_dev_tooling.checks.<slug>
```

### As composite Actions / reusable workflows in CI

```yaml
jobs:
  setup:
    uses: thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@v0.1.0
    with:
      checks: '["check-lint", "check-format", "check-types", "check-coverage"]'
```

Or, for a single composite action:

```yaml
- uses: thewoolleyman/livespec-dev-tooling/.github/actions/setup@v0.1.0
- uses: thewoolleyman/livespec-dev-tooling/.github/actions/run-check@v0.1.0
  with:
    check-name: check-lint
```

(The composite Actions and reusable workflows are authored in Phase G.5.)

## Standards

The same standards `livespec` enforces on itself, dialed up:

- **Linting** — all 27 ruff categories (pycodestyle, pyflakes, isort,
  bugbear, pyupgrade, simplify, mccabe complexity, pep8-naming,
  ruff-specific, pylint, pathlib, tryceratops, boolean-trap, pie,
  self, logging, logging-format, tidy-imports, eradicate,
  unused-arguments, raise, pytest-style, refurb, slots, isc, print,
  bandit) — pinned via `pyproject.toml` `[tool.ruff.lint].select`.
- **Type-checking** — `pyright` strict + seven strict-plus
  diagnostics (`reportUnusedCallResult`, `reportImplicitOverride`,
  `reportUninitializedInstanceVariable`,
  `reportUnnecessaryTypeIgnoreComment`, `reportUnnecessaryCast`,
  `reportUnnecessaryIsInstance`, `reportImplicitStringConcatenation`).
- **Coverage** — 100% line + branch gate (`pyproject.toml`
  `[tool.coverage.report].fail_under = 100`).
- **Architecture** — `import-linter` contracts (added once the
  package gains multi-layer structure in Phase G.4).
- **Structural discipline** — once Phase G.4 migrates the checks
  themselves, this library enforces on itself: LLOC limits (200
  hard / 250 soft per file), supervisor discipline, no-write-outside-io,
  schema-dataclass-pairing, claude-md-coverage, heading-coverage,
  exhaustive `match` arms, keyword-only function args + `match`
  destructures, no inheritance (Protocols only), newtype domain
  primitives, `__all__` declared on every module, no-direct-tool-
  invocation in lefthook/CI, mirror-paired tests, red-green-replay
  trailer discipline, commit-pairs-source-and-test, and more.

## Commands

```
just bootstrap   # uv sync + lefthook install (first-time setup)
just check       # full enforcement aggregate
just fmt         # ruff format (mutating)
just lint-fix    # ruff check --fix (mutating)
```

## Repo layout

| Path | Purpose |
|---|---|
| `livespec_dev_tooling/` | Python package (the library itself) |
| `livespec_dev_tooling/checks/` | Per-check modules (`python -m livespec_dev_tooling.checks.<slug>`) — populated in Phase G.4 |
| `tests/` | pytest suite — mirrors the package one-to-one |
| `SPECIFICATION/` | This library's own livespec specification (seeded in Phase G.3) |
| `.github/workflows/` | CI (`ci.yml`) and release automation (`release-please.yml`); composite Actions + reusable workflows land in Phase G.5 |
| `pyproject.toml`, `justfile`, `lefthook.yml`, `.mise.toml`, `.python-version`, `.livespec.jsonc` | Toolchain configuration |

## Provenance and coordination

This library is **hand-authored** (not generated from copier). Per
`livespec/SPECIFICATION/contracts.md` §"Shared content sync — copier
template", copier's scope is impl-plugin scaffolds only; the
sibling-library scaffold was YAGNI'd until a second library variant
appears. When that happens, a future propose-change cycle MAY extract
this scaffold's common shape into a `templates/library/` template.

Cross-repo coordination uses pin-and-bump per
`livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination —
pin-and-bump": the `compat` block in `.livespec.jsonc` declares the
supported `livespec` semver range and the currently-pinned release
tag. Bump-pin PRs against each upstream release are the explicit
migration path.

## More

- [`livespec`](https://github.com/thewoolleyman/livespec) — the
  parent plugin governing this library's specification.
- [`livespec-impl-plaintext`](https://github.com/thewoolleyman/livespec-impl-plaintext)
  — the JSONL-backed implementation plugin currently tracking this
  library's work-items.
