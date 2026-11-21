---
topic: check-no-shadow-ledger-body
author: claude-opus-5-5 (bqnzcm plan seat)
created_at: 2026-11-15T18:34:10Z
---

## Proposal: pyright's Node.js release is pinned in lockstep with the nodejs-wheel-binaries dev pin

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Extend §"Toolchain pins" so the Node.js release that pyright resolves through its nodeenv fallback is a pinned toolchain input: any gate that spawns pyright MUST set PYRIGHT_PYTHON_NODE_VERSION to exactly the version of the nodejs-wheel-binaries dev pin in pyproject.toml, and the two MUST move together.

### Motivation

Incident livespec-dev-tooling-igjtqq (P0, 2026-11-15): check-no-shadow-ledger-body-typechecks failed in CI because pyright's nodeenv fallback, with no Node version pinned, installed the newest Node release (27.0.0-alpha) and crashed. The fix (livespec-dev-tooling#4793, master 7d607f4f, released in v1.213.0) makes the gate set PYRIGHT_PYTHON_NODE_VERSION=24.19.0 in lockstep with the nodejs-wheel-binaries==24.19.0 dev pin (livespec_dev_tooling/checks/no_shadow_ledger_body_typechecks.py, pyproject.toml). The filing classifier placed this at the spec-change tier, linked topic check-no-shadow-ledger-body, and recorded it as the incident's deferred spec-revise debt. §"Toolchain pins" today names only mise-pinned binaries and pyproject-pinned Python packages, so an unpinned runtime that a pinned tool downloads at run time is not covered.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Toolchain pins", append after the existing paragraph:

```diff
 ## Toolchain pins
 
 Non-Python binaries (uv, just, lefthook) pin via `.mise.toml`; Python and Python packages pin via `pyproject.toml`'s `[project.requires-python]` and `[dependency-groups].dev`. Pinned versions MUST match livespec's `.mise.toml` and `pyproject.toml` exactly; drift surfaces as a propose-change-worthy event.
+
+A runtime that a pinned tool downloads for itself at run time is a pinned toolchain input too. Every gate that spawns pyright MUST set `PYRIGHT_PYTHON_NODE_VERSION` to exactly the version of the `nodejs-wheel-binaries` entry in `pyproject.toml`'s `[dependency-groups].dev`, so pyright's nodeenv fallback MUST NOT resolve an unpinned or pre-release Node.js. The two values MUST change together in one commit; a bump of either alone is drift.
```
