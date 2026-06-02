"""Revise-workflow checks invocable via `python -m livespec_dev_tooling.workflow_checks.<slug>`.

Per `SPECIFICATION/contracts.md` §"Shared check inventory" →
"Revise-workflow checks", these are shared, project-agnostic checks
invoked by a specific workflow step — the `/livespec:revise` pre-step —
rather than by the per-commit `just check` aggregate. They live here
(NOT under `livespec_dev_tooling/checks/`) so the canonical-set
derivation (`canonical_checks` walks `checks/*.py`) auto-excludes them
and they are NOT subject to the wiring-completeness invariant and NOT
members of the canonical aggregate.

`no_stale_revise_branches` is the first such check.
"""

__all__: list[str] = []
