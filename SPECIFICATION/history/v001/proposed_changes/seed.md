---
topic: seed
author: livespec-seed
---

## Proposal: seed

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/README.md

### Summary

Initial seed of the specification from user-provided intent.

### Motivation

livespec-dev-tooling is the shared enforcement-suite library for every livespec-governed project. It ships the canonical ruff/pyright/coverage gates, AST checks, CI-alignment checks, and red-green-replay discipline as (a) a versioned Python package invocable as `python -m livespec_dev_tooling.checks.<slug>` and (b) a set of GitHub composite Actions plus reusable workflows. Consumers are livespec itself, every livespec-impl-* plugin, and any future livespec-governed sibling library or application. The library's CLI surface is semver-stable, has no runtime dependency on livespec, performs no network I/O, and targets Python 3.10+.

### Proposed Changes

livespec-dev-tooling is the shared enforcement-suite library for every livespec-governed project. It ships the canonical ruff/pyright/coverage gates, AST checks, CI-alignment checks, and red-green-replay discipline as (a) a versioned Python package invocable as `python -m livespec_dev_tooling.checks.<slug>` and (b) a set of GitHub composite Actions plus reusable workflows. Consumers are livespec itself, every livespec-impl-* plugin, and any future livespec-governed sibling library or application. The library's CLI surface is semver-stable, has no runtime dependency on livespec, performs no network I/O, and targets Python 3.10+.
