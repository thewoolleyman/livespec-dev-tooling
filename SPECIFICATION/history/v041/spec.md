# livespec-dev-tooling — shared enforcement-suite library for livespec-governed projects

## Project intent

livespec-dev-tooling is the canonical home for the shared enforcement-suite checks that every livespec-governed project applies to itself. It exists because livespec's contract surface (per `livespec/SPECIFICATION/contracts.md` §"Shared code sync — livespec-dev-tooling", added in v070) partitions livespec's shared content into two parallel channels along the static-vs-executable axis: static scaffolds flow via the `copier` template at `livespec/templates/impl-plugin/`; executable enforcement-suite code flows via THIS library. The library MUST publish a Python package consumable via `uv` git source and a set of GitHub composite Actions plus reusable workflows; consumers MUST use both surfaces in concert (the Python package for local `just check` invocations; the composite Actions and reusable workflows for CI).


Throughout this spec, the token "v1" refers to the library's first MAJOR release line (semver `1.x.x`). Pre-1.0 `0.x` releases are bootstrap territory and do not satisfy any rule scoped to "v1"; "v1" rules become binding at the `1.0.0` cutover. Rules without a "v1" qualifier are unconditional and bind every release.

## Architecture

### Two consumption surfaces

The library exposes two parallel surfaces that consumers MUST use together. Each surface is semver-stable; the implementation that backs each surface is not.

- **Python package** at `livespec_dev_tooling/checks/<slug>.py`. Each module is invocable as `python -m livespec_dev_tooling.checks.<slug>` and MUST exit `0` on pass or non-zero on fail (with structured stderr describing the failure). Consumers add the library to their `pyproject.toml` `[dependency-groups].dev` via `[tool.uv.sources]` declaring a `git = "..."` plus `tag = "..."`. Internal module structure (function signatures, helper modules under `livespec_dev_tooling/`) is implementation detail and MAY change between any two versions; the package's `__all__`-declared public surface is the `python -m` invocation set, NOT individual symbols.

- **Composite Actions and reusable workflows** at `.github/actions/<name>/action.yml` and `.github/workflows/reusable-<name>.yml`. Consumers invoke them via `uses: thewoolleyman/livespec-dev-tooling/.github/actions/<name>@vX.Y.Z` and `uses: thewoolleyman/livespec-dev-tooling/.github/workflows/<name>.yml@vX.Y.Z`. Each Action's input/output contract MUST be codified in `contracts.md`.

The composite-Actions-and-reusable-workflows surface includes two functional categories. The **CI-orchestration category** ships reusable workflows and Actions that consumers wire into their per-repo `ci.yml` to execute the shared check suite (e.g., `reusable-check-matrix.yml`). The **cross-repo coordination category** ships reusable workflows that implement the pin-and-bump mechanism declared in `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" — release-dispatch fan-out, autodiscovery-driven bump-pin pull requests, vendored-library re-bump, and periodic pin-freshness sweeps — plus the independent read-only release-train park backstop (`reusable-release-park.yml`), which guards the release train FEEDING that mechanism and participates in no pin rewrite. Each category's full inventory and wire contract is pinned in `contracts.md` §"Reusable workflows wire contract" and §"Cross-repo coordination automation surface" respectively.

GitHub App installation rate limits are shared across every token minted for the same installation, so the cross-repo coordination surface MUST defer quota-intensive release and fleet-conformance entry points until both REST core and GraphQL budgets meet caller-declared minima. The budget gate MUST probe with a minimum-scope token and MUST mint the downstream token only after the gate passes, preserving the caller's requested owner and repository scope. The wire contract, timing bounds, and failure taxonomy live in `contracts.md` §"Composite Actions wire contract".

### Shared-vs-`livespec`-private partition

Not every check in `livespec/dev-tooling/checks/` ships in this library. Checks whose intent and CLI surface are stable across every livespec-governed project (style gates, coverage-pairing gates, AST gates, CI-alignment gates, red-green-replay gates) MUST migrate; checks whose intent is specific to `livespec` itself (e.g., checks asserting properties of the `livespec/templates/impl-plugin/` scaffold, checks asserting schema/dataclass pairing in `livespec`'s own package layout) MUST remain `livespec`-private. The canonical partition list lives in `contracts.md` §"Shared check inventory".

### Governance

This library dogfoods livespec at the LIBRARY scale (distinct from the plugin scale via livespec-core itself, and the impl-plugin scale via livespec-impl-git-jsonl). Its own `SPECIFICATION/` tree is the live spec; its work-items + memos are tracked by the active `livespec-impl-*` plugin per `.livespec.jsonc`. Pin-and-bump against livespec applies identically to this library as it does to any `livespec-impl-*` consumer per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" (generalized in livespec v070 to cover sibling libraries).

## Definition of Done

A livespec-dev-tooling change MUST satisfy this DoD before merge:

- The change flows through the propose-change / revise loop against this library's own `SPECIFICATION/`; no out-of-band edits to ratified spec content.
- Tests for any new check are paired with the implementation per the standard 1:1 mirror discipline at `tests/livespec_dev_tooling/checks/test_<slug>.py`.
- `just check` is green: ruff lint and format, pyright strict + 7 strict-plus diagnostics, pytest with 100% line + branch coverage, plus every structural check this library applies to itself once those checks have migrated from livespec-core.
- For any change that adds, renames, or removes a check module, the `## ` heading inventory in `contracts.md` §"Shared check inventory" MUST be co-edited atomically.
- The doctor static phase passes against the working spec; the LLM-driven phase passes against any revise pass that lands new spec content.

## Non-goals

- **PyPI publishing.** The library is consumed exclusively via `uv` git source in v1; PyPI publishing is a future optional flip that does NOT belong in v1's scope.
- **Runtime dependency on livespec.** The library is consumed by livespec, not the reverse; introducing a runtime dependency on livespec would create a circular dependency between the two repos.
- **Network I/O from any check.** Every check MUST be deterministic against its input file tree; reaching out to a remote service from a check is forbidden.
- **Hosting checks that are intrinsically `livespec`-specific.** The shared-vs-`livespec`-private partition is enforced per `contracts.md` §"Shared check inventory"; livespec-specific checks live in livespec-core and stay there.
- **A `templates/library/` extraction in v1.** The library is hand-authored per livespec epic `li-fgqgnk` Phase G.2's YAGNI; if a second sibling library appears, a follow-up cycle extracts the shared scaffold into a `templates/library/` copier template.
