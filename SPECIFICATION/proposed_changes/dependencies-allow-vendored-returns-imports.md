---
topic: dependencies-allow-vendored-returns-imports
author: claude:expedited-incident-response-flag
created_at: 2026-11-06T08:56:59Z
---

## Proposal: The library declares the vendored returns tree's third-party imports

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Replace the zero-runtime-dependency rule in `constraints.md` §"Dependencies" with a rule that the library declares exactly the third-party packages its vendored `returns` tree imports outside `returns/contrib/` (`typing-extensions` and `anyio`), each with a lower bound only, and that a released wheel installed alone into a fresh environment imports every shipped check module. The old rule, as written, made every clean install of a released wheel fail on import.

### Motivation

Work item livespec-dev-tooling-dpbpfx: a released wheel of this library, installed into a clean environment, fails on `import livespec_dev_tooling.checks._red_green_replay_revert` with `ModuleNotFoundError: No module named 'typing_extensions'`. The vendored `returns` tree imports `typing_extensions` at module scope in 25 modules outside `returns/contrib/`, and imports `anyio` in `returns/primitives/asserts.py` (function-local, inside `assert_equal`, which `returns/interfaces/*.py` import at module scope). Neither package is vendored, and the current rule forbids declaring them, so the wheel only imports in an environment that happens to carry both already.

The purpose of the old rule was that a consumer pays no transitive pin cost for adopting this library. Two lower-bounded, ubiquitous packages keep that cost near zero, while the old rule as written made every clean install of a released wheel fail.

Vendoring `typing_extensions` instead was considered and rejected: the library's pytest plugin puts `livespec_dev_tooling/_vendor/` on `sys.path` inside the consumer's own pytest process, where a vendored copy would shadow the consumer's own version of the package.

This proposal changes the specification text only. The packaging change (`pyproject.toml`, `uv.lock`) and the test that asserts the rule against the packaging config (`tests/consumer/test_zero_runtime_dependencies.py`) follow in a separate change under the same work item.

### Proposed Changes

In `SPECIFICATION/constraints.md`, section `## Dependencies`, replace the first sentence of the first paragraph:

> The library MUST declare NO runtime dependencies (no `[project].dependencies` entries) in `pyproject.toml`.

with:

> The library MUST declare, under `[project].dependencies` in `pyproject.toml`, exactly the third-party packages that its vendored `returns` tree imports outside `returns/contrib/`, and no other runtime dependency. That set is `typing-extensions` and `anyio`. Each MUST be declared with a lower bound only, never an upper bound or an exact pin, so a consumer's resolver is constrained as little as possible. A released wheel installed into a fresh environment with no other package added MUST import every shipped check module without error. The vendored packages themselves (`returns`, `structlog`) MUST still resolve from `livespec_dev_tooling/_vendor/` and MUST NOT be declared.

The rest of that paragraph and of the section MUST stay unchanged: the sentences saying that every check shells out to project-local tools via `subprocess.run` with fixed argv lists, naming the current tool set, and saying that tool versions are pinned by each consuming repo, and the second paragraph's rule that dev dependencies under `[dependency-groups].dev` MUST mirror livespec's pins.

The H2 heading set of `constraints.md` does not change, so `tests/heading-coverage.json` needs no entry added or removed.
