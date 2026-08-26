"""Workflow checks invocable via `python -m livespec_dev_tooling.workflow_checks.<slug>`.

Per `SPECIFICATION/contracts.md` section "Shared check inventory" →
"Workflow checks", these are shared, project-agnostic checks invoked by
a specific workflow step rather than by the per-commit `just check`
aggregate. They live here (NOT in `livespec_dev_tooling/checks/`) so the
canonical-set derivation (`canonical_checks` walks `checks/*.py`)
auto-excludes them, and they are NOT subject to the wiring-completeness
invariant and NOT members of the canonical aggregate.

Two kinds are defined, and the list is open to further kinds admitted by
amendment:

- Revise-workflow checks, invoked by the `/livespec:revise` pre-step.
  `no_stale_revise_branches` is the member; that pre-step is mandatory
  and fails hard on any stale branch.
- Release-workflow checks, invoked by a consumer's release-gating step.
  `release_bump_classification` is the member; it has NO mandated
  caller, because adopting any workflow check is per-consumer opt-in.

The invocation form `python -m livespec_dev_tooling.workflow_checks.<slug>`
is an enumerated element of the semver-stable surface per
`SPECIFICATION/contracts.md` section "Semver discipline". That
enumeration is what sanctions the consumer invocation; it does NOT make
these checks canonical, members of the `just check` aggregate, or
subject to the wiring-completeness invariant.

Diagnostics flow through the vendored `structlog` (JSON to stderr) —
`print` and `sys.*.write` are banned here.
"""

__all__: list[str] = []
