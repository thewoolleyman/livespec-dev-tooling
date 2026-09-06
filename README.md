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

The published Actions and reusable workflows use the GitHub Actions Node.js 24
runtime. Self-hosted consumers therefore need Actions Runner 2.327.1 or newer;
GitHub-hosted runners already satisfy this requirement.

(The composite Actions and reusable workflows are authored in Phase G.5.)

## CLI end-to-end test harness

`livespec_dev_tooling.testing.cli_e2e` is the single canonical
implementation of the fleet's *top-of-pyramid*, user-surface
end-to-end test (per `livespec`'s
`SPECIFICATION/contracts.md` §"CLI end-to-end harness contract"). Its
sole interaction surface is the `claude` CLI binary itself — it installs
a plugin via the CLI's plugin surface and exercises each skill as a
slash command, exactly as a real end user does. It is a sibling to (not
a superset of) the wrapper-chain E2E tier; both coexist in CI.

The harness ships five components behind one importable entry point:
a **driver** (`claude -p` subprocess invocations, multi-turn via
`--continue` / `--resume`), **structural skill discovery** (walks
`<installed-plugin>/skills/*/SKILL.md`, reads the slash prefix from
`plugin.json` `name`), a **per-skill fixtures loader**
(`tests/e2e-cli/fixtures/<skill>/{prompt.md,expected_files.txt}`), a
**fail-closed time-bomb coverage gate** (`discovered − fixtured −
exempt == ∅`), and a **step orchestrator**.

### Consumer import path

A consumer repo bump-pins this library (as above) and wires the entry
point into its own pytest collection:

```python
# tests/e2e-cli/test_cli_e2e.py  (in the consumer repo)
from pathlib import Path

import pytest
from livespec_dev_tooling.testing.cli_e2e import (
    HarnessConfig,
    test_workflow_full_round_trip as _run_harness,
)

# Alias the import: the canonical entry point is named
# `test_workflow_full_round_trip`, and importing that bare `test_*` name
# directly would make pytest try to collect it with a missing fixture.

def test_cli_e2e(*, tmp_path: Path) -> None:
    config = HarnessConfig(
        impl_plugin_id="livespec-impl-git-jsonl",
        marketplace="thewoolleyman/livespec",
        enabled_plugins=("livespec@livespec", "livespec-impl-git-jsonl@..."),
        plugin_install_dirs=(...,),                       # installed plugin roots
        fixtures_root=Path("tests/e2e-cli/fixtures"),
        install_command="/plugin install livespec@livespec",
    )
    _run_harness(
        config=config,
        home=tmp_path / "home",
        project_root=tmp_path / "project",
        # mock tier (default): pass a deterministic injected runner.
        # real tier (LIVESPEC_E2E_HARNESS=real): omit; the real `claude`
        # binary is used (requires ANTHROPIC_API_KEY; NOT in `just check`).
        injected_runner=my_runner,
    )
```

### Mock vs. real tier — `LIVESPEC_E2E_HARNESS`

The one mocked boundary is the `claude -p` subprocess itself (the
`CliRunner` seam) — everything else (discovery, fixtures, the coverage
gate, orchestration) always runs for real. Tier selection rides the
SAME fleet-wide `LIVESPEC_E2E_HARNESS=mock|real` selector the
wrapper-chain tier uses:

- `mock` (default) — the caller supplies a deterministic injected
  `CliRunner`; `claude` is never invoked, so the tier runs in
  `just check` with no API cost.
- `real` — `RealCliRunner` shells out to the real `claude` binary;
  requires `ANTHROPIC_API_KEY` and is NOT part of `just check`.

This library self-tests the harness in isolation against a tiny
single-skill fixture-plugin (`tests/livespec_dev_tooling/testing/
fixtures/single_skill_plugin/`) with a fake runner — proving discovery,
the coverage gate, and a fixture round-trip without any LLM/API access.

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

## Worktree-discipline pack — `worktree_discipline.pack`

Every governed repo must carry the canonical worktree-discipline pack, which
is what puts `just worktree-create` in `just --list` so sessions find the
sanctioned tool instead of falling back to a raw `git worktree add` inside the
clone. `just bootstrap` materializes it; the pack files are
gitignored-and-installed, never tracked.

`.livespec.jsonc` declares the policy:

```jsonc
{
  // "required" — the DEFAULT, and what an absent key means — makes
  // `just check` fail when the canonical pack is not installed and imported
  // by the root justfile. "optional" is the sanctioned, reviewable opt-out.
  "worktree_discipline": { "pack": "required" },
}
```

**An absent key means `required`.** Commit the block above so the obligation is
readable in config rather than discovered by tripping the verifier; the central
`worktree-pack-wired` fleet row reports the missing line, and
`just install-worktree-pack` logs it with the exact text to commit. The
installer does **not** write it for you: `.livespec.jsonc` is tracked, and an
installer that edits a tracked file leaves every checkout dirty on every
`bootstrap`, commit and push (livespec-dev-tooling-7ix8). It writes only files
the repository ignores.

`check-primary-checkout-commit-refuse-hook-installed` enforces it and reports
four distinct states: `worktree_pack_absent` (required, nothing installed),
`worktree_pack_file_missing` / `worktree_pack_body_mismatch` (partial or
drifted install), and `worktree_pack_not_imported` (bytes correct, but the
root justfile does not `import?` the fragments — so the recipes are invisible
to `just --list`). Wiring a repo means four `.gitignore` entries, both
`import?` lines, and the `install-worktree-pack` recipe.

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

## Observability

The livespec fleet dogfoods its own telemetry. CI runs, Red→Green commit-gate cycles, the beads+fabro dispatcher, sandbox runs, and harness sub-agents are published to a shared Honeycomb environment:

- **[livespec fleet — all activity](https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/krThv8DvcwS)** — the cross-repo activity board (Honeycomb, `livespec` environment).

## More

- [`livespec`](https://github.com/thewoolleyman/livespec) — the
  parent plugin governing this library's specification.
- [`livespec-orchestrator-beads-fabro`](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro)
  — the implementation plugin currently tracking this library's
  work-items in a per-repo beads/Dolt **tenant database** on the shared
  dolt-server (tenant `livespec-dev-tooling`); its client config is
  committed at `.beads/config.yaml`. The pre-cutover plaintext
  `work-items.jsonl` / `memos.jsonl` snapshot is frozen read-only under
  [`archive/`](archive/README.md).
